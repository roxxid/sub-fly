"""Async tests for the PCM live-capture session path (no GPU/model required)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.engine import TranscriptSegment, WhisperEngine
from app.session import SessionManager


def make_manager(chunk_seconds: float = 1.0) -> SessionManager:
    settings = Settings(chunk_seconds=chunk_seconds, sample_rate=16000)
    engine = MagicMock(spec=WhisperEngine)
    engine.transcribe_numpy.return_value = [TranscriptSegment(start=0.0, end=1.0, text="hi")]
    return SessionManager(settings, engine)


def silence_chunk(seconds: float, sample_rate: int = 16000) -> bytes:
    n = int(seconds * sample_rate)
    return (np.zeros(n, dtype=np.int16)).tobytes()


@pytest.mark.asyncio
async def test_pcm_session_advances_offset_without_drift():
    mgr = make_manager(chunk_seconds=1.0)
    state = await mgr.start_pcm_session(language="en", start_seconds=10.0)
    assert state.playback_position == 10.0
    assert getattr(state, "pcm_offset") == 10.0

    await mgr.ingest_pcm(state.session_id, silence_chunk(1.0))
    assert getattr(state, "pcm_offset") == 11.0

    # Client keeps reporting a matching clock — no resync should occur.
    state.playback_position = 11.0
    await mgr.ingest_pcm(state.session_id, silence_chunk(1.0))
    assert getattr(state, "pcm_offset") == 12.0


@pytest.mark.asyncio
async def test_pcm_session_resyncs_after_seek():
    mgr = make_manager(chunk_seconds=1.0)
    state = await mgr.start_pcm_session(language="en", start_seconds=0.0)

    await mgr.ingest_pcm(state.session_id, silence_chunk(1.0))
    assert getattr(state, "pcm_offset") == 1.0

    # User seeks far ahead; client reports the jump via a position update.
    await mgr.seek(state.session_id, 120.0)
    assert state.playback_position == 120.0

    await mgr.ingest_pcm(state.session_id, silence_chunk(1.0))
    # Offset should snap to the reported position instead of drifting from 1.0.
    assert getattr(state, "pcm_offset") == 121.0


@pytest.mark.asyncio
async def test_pcm_session_ignores_audio_while_paused():
    mgr = make_manager(chunk_seconds=1.0)
    state = await mgr.start_pcm_session(language="en")
    await mgr.set_paused(state.session_id, True)
    await mgr.ingest_pcm(state.session_id, silence_chunk(1.0))
    assert getattr(state, "pcm_offset") == 0.0


@pytest.mark.asyncio
async def test_vocabulary_hint_is_passed_to_engine_as_hotwords():
    mgr = make_manager(chunk_seconds=1.0)
    state = await mgr.start_pcm_session(
        language="en", vocabulary_hint="Star Trek. Characters: Spock, Uhura."
    )
    assert state.vocabulary_hint == "Star Trek. Characters: Spock, Uhura."

    await mgr.ingest_pcm(state.session_id, silence_chunk(1.0))

    mgr.engine.transcribe_numpy.assert_called_once()
    _, kwargs = mgr.engine.transcribe_numpy.call_args
    assert kwargs["hotwords"] == "Star Trek. Characters: Spock, Uhura."


@pytest.mark.asyncio
async def test_vocabulary_hint_defaults_to_none_when_empty():
    mgr = make_manager(chunk_seconds=1.0)
    state = await mgr.start_pcm_session(language="en")
    assert state.vocabulary_hint == ""

    await mgr.ingest_pcm(state.session_id, silence_chunk(1.0))

    _, kwargs = mgr.engine.transcribe_numpy.call_args
    assert kwargs["hotwords"] is None


@pytest.mark.asyncio
async def test_vocabulary_hint_is_sanitized_and_capped():
    mgr = make_manager(chunk_seconds=1.0)
    messy = "  lots\n\tof   whitespace  " + ("x" * 1000)
    state = await mgr.start_pcm_session(language="en", vocabulary_hint=messy)
    assert "\n" not in state.vocabulary_hint
    assert "\t" not in state.vocabulary_hint
    assert len(state.vocabulary_hint) <= 600


@pytest.mark.asyncio
async def test_set_vocabulary_hint_updates_mid_session():
    mgr = make_manager(chunk_seconds=1.0)
    state = await mgr.start_pcm_session(language="en")

    await mgr.set_vocabulary_hint(state.session_id, "Dune. Characters: Paul Atreides, Chani.")
    assert state.vocabulary_hint == "Dune. Characters: Paul Atreides, Chani."

    await mgr.ingest_pcm(state.session_id, silence_chunk(1.0))
    _, kwargs = mgr.engine.transcribe_numpy.call_args
    assert kwargs["hotwords"] == "Dune. Characters: Paul Atreides, Chani."
