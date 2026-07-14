# -*- coding: utf-8 -*-
"""HTTP + WebSocket client for the SubFly transcription service."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from wsclient import WebSocketClient, WebSocketError, build_ws_url


class SubFlyClient:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token or ""
        self._ws: Optional[WebSocketClient] = None
        self.session_id: Optional[str] = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["X-Api-Token"] = self.token
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/healthz")

    def start_session(
        self,
        media_path: str,
        start_seconds: float = 0.0,
        language: str = "en",
        vocabulary_hint: str = "",
    ) -> dict[str, Any]:
        body = {
            "media_path": media_path,
            "start_seconds": float(start_seconds),
            "language": language,
            "vocabulary_hint": vocabulary_hint,
        }
        data = self._request("POST", "/v1/sessions", body)
        self.session_id = data.get("session_id")
        return data

    def stop_session(self, session_id: Optional[str] = None) -> None:
        sid = session_id or self.session_id
        if not sid:
            return
        try:
            self._request("DELETE", f"/v1/sessions/{sid}")
        except Exception:
            pass
        self.session_id = None

    def connect_session_ws(
        self,
        session_id: str,
        on_message: Callable[[Any], None],
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        query = {"token": self.token} if self.token else None
        url = build_ws_url(self.base_url, f"/v1/ws/{session_id}", query)
        self._ws = WebSocketClient(url, on_message=on_message, on_close=on_close)
        self._ws.connect()

    def connect_live(
        self,
        on_message: Callable[[Any], None],
        *,
        language: str = "en",
        start_seconds: float = 0.0,
        vocabulary_hint: str = "",
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        """Open the source-agnostic continuous PCM stream (/v1/live).

        Use this instead of start_session()/connect_session_ws() when the
        server can't open the playing item itself (add-ons, live TV/PVR,
        DRM, anything not a plain resolvable file path). Push audio with
        send_pcm() for as long as something is playing.

        `vocabulary_hint` (title/cast/plot/genre — see hints.py) biases
        Whisper's decoding toward the specific proper nouns of whatever's
        playing; leave it empty if you have nothing useful to send.
        """
        query = {"language": language, "start_seconds": str(start_seconds)}
        if vocabulary_hint:
            query["vocabulary_hint"] = vocabulary_hint
        if self.token:
            query["token"] = self.token
        url = build_ws_url(self.base_url, "/v1/live", query)
        self._ws = WebSocketClient(url, on_message=on_message, on_close=on_close)
        self._ws.connect()

    def send_pcm(self, pcm: bytes) -> None:
        if self._ws:
            self._ws.send_binary(pcm)

    def send_position(self, position: float) -> None:
        if self._ws:
            self._ws.send_json({"type": "position", "position": float(position)})

    def send_pause(self, paused: bool) -> None:
        if self._ws:
            self._ws.send_json({"type": "pause", "paused": bool(paused)})

    def send_seek(self, position: float) -> None:
        if self._ws:
            self._ws.send_json({"type": "seek", "position": float(position)})

    def send_vocabulary_hint(self, text: str) -> None:
        if self._ws:
            self._ws.send_json({"type": "vocabulary_hint", "text": text})

    def close_ws(self) -> None:
        if self._ws:
            try:
                self._ws.send_json({"type": "stop"})
            except Exception:
                pass
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"SubFly HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"SubFly unreachable at {url}: {exc}") from exc
