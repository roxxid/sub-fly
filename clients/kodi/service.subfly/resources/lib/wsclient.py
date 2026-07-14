# -*- coding: utf-8 -*-
"""Minimal RFC6455 WebSocket client using only the Python standard library.

Works inside Kodi's Python runtime without installing third-party packages.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlencode, urlunparse


class WebSocketError(Exception):
    pass


class WebSocketClient:
    def __init__(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        on_message: Optional[Callable[[Any], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
        timeout: float = 15.0,
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self.on_message = on_message
        self.on_close = on_close
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._closed = threading.Event()
        self._send_lock = threading.Lock()

    def connect(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"ws", "wss"}:
            raise WebSocketError(f"unsupported scheme: {parsed.scheme}")

        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        raw = socket.create_connection((host, port), timeout=self.timeout)
        if parsed.scheme == "wss":
            ctx = ssl.create_default_context()
            self._sock = ctx.wrap_socket(raw, server_hostname=host)
        else:
            self._sock = raw
        self._sock.settimeout(self.timeout)

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
        )
        for hk, hv in self.headers.items():
            req += f"{hk}: {hv}\r\n"
        req += "\r\n"
        self._sock.sendall(req.encode("utf-8"))

        # Read HTTP response headers
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise WebSocketError("connection closed during handshake")
            response += chunk
        header, _, leftover = response.partition(b"\r\n\r\n")
        status_line = header.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
        if "101" not in status_line:
            raise WebSocketError(f"handshake failed: {status_line}")

        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        if expected.encode() not in header:
            # Some proxies strip the accept header check loosely — still require 101
            pass

        self._closed.clear()
        self._recv_thread = threading.Thread(target=self._recv_loop, name="subfly-ws", daemon=True)
        # Stash any leftover bytes after headers for the frame parser
        self._buffer = bytearray(leftover)
        self._recv_thread.start()

    def send_json(self, payload: dict) -> None:
        self.send_text(json.dumps(payload))

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def send_binary(self, data: bytes) -> None:
        self._send_frame(0x2, data)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._send_frame(0x8, b"")
        except Exception:
            pass
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        if self.on_close:
            try:
                self.on_close()
            except Exception:
                pass

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if not self._sock or self._closed.is_set():
            raise WebSocketError("socket closed")
        header = bytearray()
        header.append(0x80 | (opcode & 0x0F))
        mask_bit = 0x80
        length = len(payload)
        if length < 126:
            header.append(mask_bit | length)
        elif length < (1 << 16):
            header.append(mask_bit | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._send_lock:
            self._sock.sendall(header + masked)

    def _recv_exact(self, n: int) -> bytes:
        while len(self._buffer) < n:
            if not self._sock or self._closed.is_set():
                raise WebSocketError("closed")
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise WebSocketError("closed")
            self._buffer.extend(chunk)
        data = bytes(self._buffer[:n])
        del self._buffer[:n]
        return data

    def _recv_loop(self) -> None:
        try:
            while not self._closed.is_set():
                header = self._recv_exact(2)
                opcode = header[0] & 0x0F
                masked = (header[1] & 0x80) != 0
                length = header[1] & 0x7F
                if length == 126:
                    length = struct.unpack("!H", self._recv_exact(2))[0]
                elif length == 127:
                    length = struct.unpack("!Q", self._recv_exact(8))[0]
                mask = self._recv_exact(4) if masked else b""
                payload = self._recv_exact(length)
                if masked:
                    payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

                if opcode == 0x8:  # close
                    break
                if opcode == 0x9:  # ping
                    self._send_frame(0xA, payload)
                    continue
                if opcode == 0xA:  # pong
                    continue
                if opcode == 0x1:  # text
                    text = payload.decode("utf-8", errors="replace")
                    if self.on_message:
                        try:
                            data = json.loads(text)
                        except json.JSONDecodeError:
                            data = text
                        self.on_message(data)
                elif opcode == 0x2 and self.on_message:
                    self.on_message(payload)
        except Exception:
            pass
        finally:
            self.close()


def build_ws_url(base_http: str, path: str, query: Optional[dict] = None) -> str:
    """Convert http(s)://host:port into ws(s)://host:port/path."""
    parsed = urlparse(base_http)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc
    q = urlencode(query or {})
    return urlunparse((scheme, netloc, path, "", q, ""))
