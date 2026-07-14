"""Smoke tests for the reusable Python client (no server required)."""

from __future__ import annotations

from subfly import SubFlyClient, SubtitleCue, build_ws_url
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


def test_connect_live_pcm_includes_vocabulary_hint_when_present(monkeypatch):
    captured = {}

    class FakeWS:
        def __init__(self, url, on_message=None, on_close=None, timeout=20.0):
            captured["url"] = url

        def connect(self):
            pass

    import subfly.client as client_module

    monkeypatch.setattr(client_module, "WebSocketClient", FakeWS)

    c = SubFlyClient("http://host:8765")
    c.connect_live_pcm(
        on_message=lambda m: None,
        vocabulary_hint="Dune. Characters: Paul Atreides, Chani.",
    )

    assert "vocabulary_hint=Dune" in captured["url"]


def test_connect_live_pcm_omits_vocabulary_hint_when_empty(monkeypatch):
    captured = {}

    class FakeWS:
        def __init__(self, url, on_message=None, on_close=None, timeout=20.0):
            captured["url"] = url

        def connect(self):
            pass

    import subfly.client as client_module

    monkeypatch.setattr(client_module, "WebSocketClient", FakeWS)

    c = SubFlyClient("http://host:8765")
    c.connect_live_pcm(on_message=lambda m: None)

    assert "vocabulary_hint" not in captured["url"]
