# -*- coding: utf-8 -*-
"""Unit tests for the stdlib client's HTTP/WS URL building (no server needed)."""

import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "service.subfly" / "resources" / "lib"
sys.path.insert(0, str(LIB))

from client import SubFlyClient  # noqa: E402
from wsclient import build_ws_url  # noqa: E402


def test_connect_live_builds_expected_url(monkeypatch):
    captured = {}

    class FakeWS:
        def __init__(self, url, on_message=None, on_close=None):
            captured["url"] = url

        def connect(self):
            captured["connected"] = True

    import client as client_module

    monkeypatch.setattr(client_module, "WebSocketClient", FakeWS)

    c = SubFlyClient("http://host:8765", token="secret")
    c.connect_live(on_message=lambda m: None, language="en", start_seconds=12.5)

    assert captured["connected"] is True
    assert captured["url"].startswith("ws://host:8765/v1/live?")
    assert "language=en" in captured["url"]
    assert "start_seconds=12.5" in captured["url"]
    assert "token=secret" in captured["url"]


def test_build_ws_url_scheme_mapping():
    assert build_ws_url("http://h:1", "/v1/live") == "ws://h:1/v1/live"
    assert build_ws_url("https://h", "/v1/live").startswith("wss://h/v1/live")
