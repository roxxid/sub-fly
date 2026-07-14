# -*- coding: utf-8 -*-
"""Playback watcher that starts/stops SubFly sessions."""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

import xbmc
import xbmcaddon
import xbmcgui

from client import SubFlyClient
from overlay import SubtitleOverlay


class SubFlyPlayer(xbmc.Player):
    def __init__(self, monitor: "SubFlyMonitor") -> None:
        super().__init__()
        self.monitor = monitor

    def onAVStarted(self) -> None:
        self.monitor.on_playback_started()

    def onPlayBackStopped(self) -> None:
        self.monitor.on_playback_ended()

    def onPlayBackEnded(self) -> None:
        self.monitor.on_playback_ended()

    def onPlayBackPaused(self) -> None:
        self.monitor.on_playback_paused(True)

    def onPlayBackResumed(self) -> None:
        self.monitor.on_playback_paused(False)

    def onPlayBackSeek(self, time_ms: int, seek_offset_ms: int) -> None:
        self.monitor.on_playback_seek(time_ms / 1000.0)


class SubFlyMonitor(xbmc.Monitor):
    def __init__(self, addon: xbmcaddon.Addon) -> None:
        super().__init__()
        self.addon = addon
        self.player = SubFlyPlayer(self)
        self.overlay = SubtitleOverlay()
        self.client: Optional[SubFlyClient] = None
        self._session_lock = threading.Lock()
        self._active = False
        self._last_path: Optional[str] = None
        self._cues: list[dict[str, Any]] = []
        self._cue_lock = threading.Lock()
        self._notify = True

    # --- settings helpers -------------------------------------------------
    def _enabled(self) -> bool:
        return self.addon.getSettingBool("enabled")

    def _base_url(self) -> str:
        return (self.addon.getSettingString("service_url") or "http://192.168.1.10:8765").rstrip("/")

    def _token(self) -> str:
        return self.addon.getSettingString("api_token") or ""

    def _language(self) -> str:
        return self.addon.getSettingString("language") or "en"

    def _notify_errors(self) -> bool:
        return self.addon.getSettingBool("notify_errors")

    # --- main loop --------------------------------------------------------
    def run(self) -> None:
        last_pos_send = 0.0
        while not self.abortRequested():
            if self._enabled() and self.player.isPlayingVideo() and self._active:
                try:
                    pos = float(self.player.getTime())
                except Exception:
                    pos = 0.0
                self._display_due_cues(pos)
                now = time.time()
                if self.client and now - last_pos_send >= 1.0:
                    try:
                        self.client.send_position(pos)
                    except Exception:
                        pass
                    last_pos_send = now
            self.overlay.tick()
            self.waitForAbort(0.2)
        self._teardown_session()
        self.overlay.close()

    # --- playback events --------------------------------------------------
    def on_playback_started(self) -> None:
        if not self._enabled():
            return
        if not self.player.isPlayingVideo():
            return
        try:
            path = self.player.getPlayingFile()
        except Exception:
            path = ""
        if not path:
            return
        # Avoid restarting on the same file if already active
        with self._session_lock:
            if self._active and self._last_path == path:
                return
            self._teardown_session_unlocked()
            self._start_session_unlocked(path)

    def on_playback_ended(self) -> None:
        self._teardown_session()

    def on_playback_paused(self, paused: bool) -> None:
        if self.client and self._active:
            try:
                self.client.send_pause(paused)
            except Exception:
                pass

    def on_playback_seek(self, position: float) -> None:
        with self._cue_lock:
            self._cues = [c for c in self._cues if c["end"] > position]
        self.overlay.clear()
        if self.client and self._active:
            try:
                self.client.send_seek(position)
            except Exception:
                pass

    def onSettingsChanged(self) -> None:
        xbmc.log("[SubFly] settings changed", xbmc.LOGINFO)
        # If disabled mid-playback, tear down
        if not self._enabled():
            self._teardown_session()

    # --- session lifecycle ------------------------------------------------
    def _start_session_unlocked(self, path: str) -> None:
        url = self._base_url()
        token = self._token()
        language = self._language()
        try:
            start = float(self.player.getTime())
        except Exception:
            start = 0.0

        client = SubFlyClient(url, token)
        try:
            health = client.health()
            if not health.get("ok"):
                raise RuntimeError("service unhealthy")
            info = client.start_session(path, start_seconds=start, language=language)
            sid = info["session_id"]
            client.connect_session_ws(sid, on_message=self._on_ws_message, on_close=self._on_ws_close)
        except Exception as exc:
            xbmc.log(f"[SubFly] failed to start session: {exc}", xbmc.LOGERROR)
            if self._notify_errors():
                xbmcgui.Dialog().notification(
                    "SubFly",
                    f"Cannot reach service: {exc}",
                    xbmcgui.NOTIFICATION_ERROR,
                    5000,
                )
            return

        self.client = client
        self._active = True
        self._last_path = path
        with self._cue_lock:
            self._cues = []
        xbmc.log(f"[SubFly] session started for {path}", xbmc.LOGINFO)
        if self.addon.getSettingBool("notify_start"):
            xbmcgui.Dialog().notification(
                "SubFly",
                "Live subtitles connected",
                xbmcgui.NOTIFICATION_INFO,
                2500,
            )

    def _teardown_session(self) -> None:
        with self._session_lock:
            self._teardown_session_unlocked()

    def _teardown_session_unlocked(self) -> None:
        self._active = False
        self._last_path = None
        with self._cue_lock:
            self._cues = []
        self.overlay.clear()
        if self.client:
            try:
                self.client.close_ws()
            except Exception:
                pass
            try:
                self.client.stop_session()
            except Exception:
                pass
            self.client = None

    # --- subtitle handling ------------------------------------------------
    def _on_ws_message(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        typ = data.get("type")
        if typ == "subtitle":
            cue = {
                "start": float(data.get("start", 0)),
                "end": float(data.get("end", 0)),
                "text": str(data.get("text", "")).strip(),
            }
            if cue["text"]:
                with self._cue_lock:
                    self._cues.append(cue)
                    # Keep buffer bounded
                    if len(self._cues) > 200:
                        self._cues = self._cues[-100:]
        elif typ == "error":
            msg = data.get("message", "unknown error")
            xbmc.log(f"[SubFly] server error: {msg}", xbmc.LOGERROR)
            if self._notify_errors():
                xbmcgui.Dialog().notification("SubFly", str(msg), xbmcgui.NOTIFICATION_ERROR, 5000)

    def _on_ws_close(self) -> None:
        xbmc.log("[SubFly] websocket closed", xbmc.LOGINFO)

    def _display_due_cues(self, position: float) -> None:
        """Show the cue that should be on screen at the current player time.

        Captions arrive slightly ahead of playback; we display by media timestamp.
        """
        lead = 0.15
        active_text = ""
        hold = 3.0
        with self._cue_lock:
            due = [c for c in self._cues if c["start"] - lead <= position <= c["end"] + 0.35]
            # Drop old cues
            self._cues = [c for c in self._cues if c["end"] + 1.0 >= position]
            if due:
                # Prefer the latest overlapping cue
                cue = due[-1]
                active_text = cue["text"]
                hold = max(1.5, cue["end"] - position + 0.5)
        if active_text:
            self.overlay.show(active_text, hold_seconds=hold)
