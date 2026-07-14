"""Smoke tests for the reusable Python client (no server required)."""

from __future__ import annotations

from subfly import SubtitleCue, build_ws_url
from subfly.client import SubtitleCue as Cue


def test_build_ws_url():
    assert build_ws_url("http://host:8765", "/v1/ws/abc") == "ws://host:8765/v1/ws/abc"
    assert build_ws_url("https://host", "/v1/live", {"token": "x"}).startswith("wss://host/v1/live")


def test_subtitle_cue_from_message():
    cue = SubtitleCue.from_message(
        {"start": 1.5, "end": 3.0, "text": " hello ", "language": "en", "session_id": "s"}
    )
    assert cue.start == 1.5
    assert cue.text == "hello"
    assert Cue is SubtitleCue
