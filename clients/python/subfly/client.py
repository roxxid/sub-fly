"""High-level SubFly HTTP + WebSocket client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .ws import WebSocketClient, build_ws_url


class SubFlyError(RuntimeError):
    pass


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str
    language: str = "en"
    session_id: str = ""

    @classmethod
    def from_message(cls, data: dict[str, Any]) -> "SubtitleCue":
        return cls(
            start=float(data.get("start", 0)),
            end=float(data.get("end", 0)),
            text=str(data.get("text", "")).strip(),
            language=str(data.get("language", "en")),
            session_id=str(data.get("session_id", "")),
        )


class SubFlyClient:
    """Reusable client for any app that can point at a SubFly server.

    Example:
        client = SubFlyClient("http://192.168.1.50:8765")
        session = client.start_session("/media/Movies/film.mkv", start_seconds=0)
        client.connect_session_ws(session["session_id"], on_message=print)
    """

    def __init__(self, base_url: str, token: str = "", timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token or ""
        self.timeout = timeout
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

    def info(self) -> dict[str, Any]:
        return self._request("GET", "/v1/info")

    def start_session(
        self,
        media_path: str,
        start_seconds: float = 0.0,
        language: str = "en",
    ) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/v1/sessions",
            {
                "media_path": media_path,
                "start_seconds": float(start_seconds),
                "language": language,
            },
        )
        self.session_id = data.get("session_id")
        return data

    def seek(self, position: float, session_id: Optional[str] = None) -> dict[str, Any]:
        sid = session_id or self.session_id
        if not sid:
            raise SubFlyError("no active session")
        return self._request("POST", f"/v1/sessions/{sid}/seek", {"position": float(position)})

    def pause(self, paused: bool = True, session_id: Optional[str] = None) -> dict[str, Any]:
        sid = session_id or self.session_id
        if not sid:
            raise SubFlyError("no active session")
        return self._request("POST", f"/v1/sessions/{sid}/pause", {"paused": bool(paused)})

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
        self._ws = WebSocketClient(
            url, on_message=on_message, on_close=on_close, timeout=self.timeout
        )
        self._ws.connect()

    def connect_live_pcm(
        self,
        on_message: Callable[[Any], None],
        *,
        language: str = "en",
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        """Open /v1/live and push raw 16 kHz mono s16le PCM via send_pcm()."""
        query: dict[str, str] = {"language": language}
        if self.token:
            query["token"] = self.token
        url = build_ws_url(self.base_url, "/v1/live", query)
        self._ws = WebSocketClient(
            url, on_message=on_message, on_close=on_close, timeout=self.timeout
        )
        self._ws.connect()

    def send_pcm(self, pcm_s16le: bytes) -> None:
        if not self._ws:
            raise SubFlyError("websocket not connected")
        self._ws.send_binary(pcm_s16le)

    def send_position(self, position: float) -> None:
        if self._ws:
            self._ws.send_json({"type": "position", "position": float(position)})

    def send_pause(self, paused: bool) -> None:
        if self._ws:
            self._ws.send_json({"type": "pause", "paused": bool(paused)})

    def send_seek(self, position: float) -> None:
        if self._ws:
            self._ws.send_json({"type": "seek", "position": float(position)})

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
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SubFlyError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SubFlyError(f"unreachable at {url}: {exc}") from exc
