"""Live transcription session that follows Kodi playback."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.audio import pcm_s16le_to_float32, stream_pcm_chunks
from app.config import Settings
from app.engine import TranscriptSegment, WhisperEngine
from app.pathmap import media_exists, rewrite_media_path

log = logging.getLogger("subfly.session")

# faster-whisper's `hotwords` (and `initial_prompt`/`prefix`) are limited to
# roughly 223 tokens internally; we cap well under that in characters so a
# client can't accidentally (or deliberately) send something that eats the
# whole prompt budget or measurably slows decoding.
MAX_VOCABULARY_HINT_CHARS = 600


def clean_vocabulary_hint(text: Optional[str]) -> str:
    """Sanitize a client-supplied vocabulary hint before it reaches Whisper."""
    if not text:
        return ""
    return " ".join(str(text).split())[:MAX_VOCABULARY_HINT_CHARS]


@dataclass
class SessionState:
    session_id: str
    media_path: str
    resolved_path: str
    started_at: float = field(default_factory=time.time)
    playback_position: float = 0.0
    paused: bool = False
    running: bool = False
    # Free-text hint (title/character names/plot/genre — whatever a client
    # can scrape from its media metadata) used as faster-whisper's
    # `hotwords`, to bias transcription toward the specific proper nouns of
    # whatever's actually playing. See PROTOCOL.md.
    vocabulary_hint: str = ""
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    outbound: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: Optional[asyncio.Task] = None


class SessionManager:
    def __init__(self, settings: Settings, engine: WhisperEngine) -> None:
        self.settings = settings
        self.engine = engine
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)

    async def start_url_session(
        self,
        media_path: str,
        *,
        start_seconds: float = 0.0,
        language: Optional[str] = None,
        vocabulary_hint: str = "",
    ) -> SessionState:
        resolved = rewrite_media_path(media_path, self.settings.path_map_pairs())
        if not media_exists(resolved):
            raise FileNotFoundError(f"media not found after path map: {resolved}")

        session_id = str(uuid.uuid4())
        state = SessionState(
            session_id=session_id,
            media_path=media_path,
            resolved_path=resolved,
            playback_position=start_seconds,
            vocabulary_hint=clean_vocabulary_hint(vocabulary_hint),
        )
        self._sessions[session_id] = state
        state.running = True
        state.task = asyncio.create_task(
            self._run_url_pipeline(state, language=language),
            name=f"subfly-session-{session_id}",
        )
        await state.outbound.put(
            {
                "type": "session_started",
                "session_id": session_id,
                "media_path": media_path,
                "resolved_path": resolved,
                "start_seconds": start_seconds,
            }
        )
        return state

    async def start_pcm_session(
        self,
        *,
        language: Optional[str] = None,
        start_seconds: float = 0.0,
        vocabulary_hint: str = "",
    ) -> SessionState:
        """Start a session fed by raw PCM pushed from the client.

        This mode never opens a file on the server: it works for ANY
        playback the client can capture audio from (local files, external
        libraries, add-ons/plugins, live TV/PVR, DRM content post-decode,
        anything). The client streams continuously for as long as
        something is playing.
        """
        session_id = str(uuid.uuid4())
        state = SessionState(
            session_id=session_id,
            media_path="pcm://live",
            resolved_path="pcm://live",
            playback_position=max(0.0, start_seconds),
            vocabulary_hint=clean_vocabulary_hint(vocabulary_hint),
        )
        self._sessions[session_id] = state
        state.running = True
        await state.outbound.put(
            {
                "type": "session_started",
                "session_id": session_id,
                "mode": "pcm",
            }
        )
        setattr(state, "language", language or self.settings.language)
        setattr(state, "pcm_buffer", bytearray())
        # pcm_offset is the playback-clock timestamp we expect the *next*
        # chunk to start at. It advances by chunk_seconds after each chunk
        # and re-anchors to the client-reported position whenever they
        # drift apart (seek, pause/resume gap, live-TV channel change...).
        setattr(state, "pcm_offset", max(0.0, start_seconds))
        return state

    async def seek(self, session_id: str, position: float) -> None:
        state = self._sessions.get(session_id)
        if not state:
            return
        state.playback_position = max(0.0, position)
        # Restart URL pipeline from new position
        if state.media_path != "pcm://live":
            state.cancel.set()
            if state.task and not state.task.done():
                state.task.cancel()
                try:
                    await state.task
                except (asyncio.CancelledError, Exception):
                    pass
            state.cancel = asyncio.Event()
            state.task = asyncio.create_task(
                self._run_url_pipeline(state, language=None),
                name=f"subfly-session-{session_id}",
            )
            await state.outbound.put(
                {"type": "seeked", "session_id": session_id, "position": position}
            )

    async def set_vocabulary_hint(self, session_id: str, hint: str) -> None:
        """Update the hotwords hint mid-session.

        Useful when a client's metadata for the current item wasn't ready
        yet at session start, or when it changes (e.g. a new episode of a
        TV show starts without a full stop/start of the session).
        """
        state = self._sessions.get(session_id)
        if not state:
            return
        state.vocabulary_hint = clean_vocabulary_hint(hint)

    async def set_paused(self, session_id: str, paused: bool) -> None:
        state = self._sessions.get(session_id)
        if not state:
            return
        state.paused = paused
        await state.outbound.put(
            {"type": "paused" if paused else "resumed", "session_id": session_id}
        )

    async def stop(self, session_id: str) -> None:
        state = self._sessions.pop(session_id, None)
        if not state:
            return
        state.running = False
        state.cancel.set()
        if state.task and not state.task.done():
            state.task.cancel()
            try:
                await state.task
            except (asyncio.CancelledError, Exception):
                pass
        await state.outbound.put({"type": "session_stopped", "session_id": session_id})

    async def ingest_pcm(self, session_id: str, pcm: bytes, timestamp: float | None = None) -> None:
        state = self._sessions.get(session_id)
        if not state or state.media_path != "pcm://live":
            return
        if state.paused:
            return

        if timestamp is not None:
            state.playback_position = timestamp

        buf: bytearray = getattr(state, "pcm_buffer")
        buf.extend(pcm)
        chunk_bytes = int(
            self.settings.sample_rate * self.settings.chunk_seconds * 2
        )  # mono s16le
        language = getattr(state, "language", self.settings.language)
        offset = getattr(state, "pcm_offset", 0.0)
        resync_threshold = self.settings.chunk_seconds * 1.5

        while len(buf) >= chunk_bytes:
            # If the client's reported playback clock has drifted away from
            # our running offset (seek, live-TV jump, resume after a long
            # pause), snap to it instead of accumulating error forever.
            if abs(state.playback_position - offset) > resync_threshold:
                offset = state.playback_position

            chunk = bytes(buf[:chunk_bytes])
            del buf[:chunk_bytes]
            audio = pcm_s16le_to_float32(chunk)
            segments = await asyncio.to_thread(
                self.engine.transcribe_numpy,
                audio,
                time_offset=offset,
                language=language,
                hotwords=state.vocabulary_hint or None,
            )
            for seg in segments:
                await self._emit_subtitle(state, seg)
            offset += self.settings.chunk_seconds
            setattr(state, "pcm_offset", offset)

    async def _run_url_pipeline(
        self,
        state: SessionState,
        *,
        language: Optional[str],
    ) -> None:
        lang = language or self.settings.language
        start = state.playback_position
        try:
            async for chunk_start, pcm in stream_pcm_chunks(
                state.resolved_path,
                sample_rate=self.settings.sample_rate,
                start_seconds=start,
                chunk_seconds=self.settings.chunk_seconds,
            ):
                if state.cancel.is_set() or not state.running:
                    break
                while state.paused and not state.cancel.is_set():
                    await asyncio.sleep(0.1)
                if state.cancel.is_set():
                    break

                # Stay roughly ahead of reported playback, but not infinitely.
                # If Kodi position lags, wait briefly so captions stay in sync.
                lead = chunk_start - state.playback_position
                if lead > self.settings.chunk_seconds * 2:
                    await asyncio.sleep(min(lead - self.settings.chunk_seconds, 2.0))

                audio = pcm_s16le_to_float32(pcm)
                if audio.size < int(self.settings.sample_rate * self.settings.min_audio_seconds):
                    continue

                segments = await asyncio.to_thread(
                    self.engine.transcribe_numpy,
                    audio,
                    time_offset=chunk_start,
                    language=lang,
                    hotwords=state.vocabulary_hint or None,
                )
                for seg in segments:
                    if state.cancel.is_set():
                        break
                    await self._emit_subtitle(state, seg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("session %s failed: %s", state.session_id, exc)
            await state.outbound.put(
                {
                    "type": "error",
                    "session_id": state.session_id,
                    "message": str(exc),
                }
            )
        finally:
            state.running = False
            await state.outbound.put(
                {"type": "pipeline_done", "session_id": state.session_id}
            )

    async def _emit_subtitle(self, state: SessionState, seg: TranscriptSegment) -> None:
        payload: dict[str, Any] = {
            "type": "subtitle",
            "session_id": state.session_id,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text,
            "language": self.settings.language,
        }
        await state.outbound.put(payload)
