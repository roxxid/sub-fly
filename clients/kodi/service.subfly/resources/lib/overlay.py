# -*- coding: utf-8 -*-
"""On-screen live subtitle overlay for Kodi."""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

import xbmcgui


class SubtitleOverlay:
    """Fullscreen transparent dialog that shows one live caption line."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._window: Optional[xbmcgui.WindowDialog] = None
        self._label: Optional[xbmcgui.ControlLabel] = None
        self._bg: Optional[xbmcgui.ControlImage] = None
        self._visible = False
        self._hide_at = 0.0
        self._current = ""

    def show(self, text: str, hold_seconds: float = 3.5) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            self._ensure_window()
            assert self._label is not None
            self._current = text
            # Wrap long lines roughly for 1080p overlay width
            display = self._wrap(text, 72)
            self._label.setLabel(display)
            if not self._visible:
                self._window.show()
                self._visible = True
            self._hide_at = time.time() + max(1.0, hold_seconds)

    def tick(self) -> None:
        """Call periodically from the main loop to auto-hide stale captions."""
        with self._lock:
            if self._visible and time.time() >= self._hide_at:
                self._hide_unlocked()

    def clear(self) -> None:
        with self._lock:
            self._hide_unlocked()

    def close(self) -> None:
        with self._lock:
            self._hide_unlocked()
            if self._window is not None:
                try:
                    self._window.close()
                except Exception:
                    pass
            self._window = None
            self._label = None
            self._bg = None

    def _hide_unlocked(self) -> None:
        if self._label is not None:
            self._label.setLabel("")
        if self._window is not None and self._visible:
            try:
                self._window.close()
            except Exception:
                pass
            # Recreate on next show — WindowDialog close is simplest for Kodi
            self._window = None
            self._label = None
            self._bg = None
            self._visible = False
        self._current = ""

    def _ensure_window(self) -> None:
        if self._window is not None:
            return

        win = xbmcgui.WindowDialog()
        media = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "black.png",
        )
        # Semi-transparent black bar near bottom of 1920x1080 canvas
        bg = xbmcgui.ControlImage(
            120,
            900,
            1680,
            120,
            media,
            colorDiffuse="B0000000",
        )
        label = xbmcgui.ControlLabel(
            140,
            910,
            1640,
            100,
            "",
            font="font14",
            textColor="FFFFFFFF",
            alignment=0x00000002 | 0x00000004,  # center x + center y
        )
        win.addControl(bg)
        win.addControl(label)
        self._window = win
        self._bg = bg
        self._label = label

    @staticmethod
    def _wrap(text: str, width: int) -> str:
        words = text.split()
        if not words:
            return text
        lines: list[str] = []
        cur = words[0]
        for w in words[1:]:
            if len(cur) + 1 + len(w) <= width:
                cur = f"{cur} {w}"
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return "\n".join(lines[:3])
