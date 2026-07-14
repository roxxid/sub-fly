"""faster-whisper engine wrapper for Tesla T4 / CUDA."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from app.config import Settings

log = logging.getLogger("subfly.engine")


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


class WhisperEngine:
    """Thread-safe Whisper transcription engine."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._lock = threading.Lock()

    def load(self) -> None:
        from faster_whisper import WhisperModel

        log.info(
            "loading Whisper model=%s device=%s compute=%s",
            self.settings.model_size,
            self.settings.device,
            self.settings.compute_type,
        )
        self._model = WhisperModel(
            self.settings.model_size,
            device=self.settings.device,
            compute_type=self.settings.compute_type,
            download_root=self.settings.download_root,
        )
        log.info("Whisper model ready")

    @property
    def ready(self) -> bool:
        return self._model is not None

    def transcribe_numpy(
        self,
        audio,
        *,
        time_offset: float = 0.0,
        language: Optional[str] = None,
        hotwords: Optional[str] = None,
    ) -> list[TranscriptSegment]:
        if self._model is None:
            raise RuntimeError("model not loaded")

        lang = language or self.settings.language
        with self._lock:
            segments, _info = self._model.transcribe(
                audio,
                language=lang,
                beam_size=self.settings.beam_size,
                vad_filter=self.settings.vad_filter,
                word_timestamps=self.settings.word_timestamps,
                condition_on_previous_text=False,
                without_timestamps=False,
                # Biases decoding toward specific vocabulary (character/place
                # names, in-universe terms) for whatever's currently playing,
                # instead of relying only on Whisper's general-purpose
                # training-data statistics. See SessionState.vocabulary_hint
                # and PROTOCOL.md for where this comes from.
                hotwords=hotwords or None,
            )
            results: list[TranscriptSegment] = []
            for seg in segments:
                text = (seg.text or "").strip()
                if not text:
                    continue
                results.append(
                    TranscriptSegment(
                        start=float(seg.start) + time_offset,
                        end=float(seg.end) + time_offset,
                        text=text,
                    )
                )
            return results
