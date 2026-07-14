# -*- coding: utf-8 -*-
"""Playback watcher that streams live audio to SubFly for ANY Kodi playback.

Default mode captures the audio Kodi is actually outputting (post-decode)
and streams it continuously to the server. Because capture happens after
decode, it works the same way regardless of source: local files, external
add-on libraries, live TV/PVR, plugin sources, or DRM content — anything
Kodi can play out loud, the server can turn into captions.

An optional "file_path" mode is kept for users who specifically want the
server to open a resolvable local/network file itself (a bit faster, no
local capture setup, but only works when the server can actually reach
the file).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

import xbmc
import xbmcaddon
import xbmcgui

from capture import AudioCapture, CaptureConfig
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
        self.capture: Optional[AudioCapture] = None
        self._session_lock = threading.Lock()
        self._active = False
        self._generation = 0
        self._cues: list[dict[str, Any]] = []
        self._cue_lock = threading.Lock()

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

    def _capture_mode(self) -> str:
        return self.addon.getSettingString("capture_mode") or "live_capture"

    def _capture_config(self) -> CaptureConfig:
        return CaptureConfig(
            ffmpeg_path=self.addon.getSettingString("ffmpeg_path") or "ffmpeg",
            backend=self.addon.getSettingString("audio_backend") or "pulse",
            device=self.addon.getSettingString("audio_device") or "",
            custom_input_args=self.addon.getSettingString("custom_input_args") or "",
        )

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
        # Any new playback start gets a fresh session, whatever the source.
        # (Path is best-effort metadata only — plugin/PVR sources often
        # can't report one, and that's fine: live capture doesn't need it.)
        try:
            path = self.player.getPlayingFile()
        except Exception:
            path = ""
        try:
            start = float(self.player.getTime())
        except Exception:
            start = 0.0

        with self._session_lock:
            self._generation += 1
            gen = self._generation
            self._teardown_session_unlocked()
            if self._capture_mode() == "file_path":
                self._start_file_session_unlocked(path, start, gen)
            else:
                self._start_live_capture_unlocked(path, start, gen)

    def on_playback_ended(self) -> None:
        with self._session_lock:
            self._generation += 1
            self._teardown_session_unlocked()

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
        if not self._enabled():
            with self._session_lock:
                self._generation += 1
                self._teardown_session_unlocked()

    # --- live capture mode (default; works for any source) ----------------
    def _start_live_capture_unlocked(self, path: str, start: float, gen: int) -> None:
        url = self._base_url()
        token = self._token()
        language = self._language()

        client = SubFlyClient(url, token)
        try:
            health = client.health()
            if not health.get("ok"):
                raise RuntimeError("service unhealthy")
            client.connect_live(
                on_message=self._on_ws_message,
                language=language,
                start_seconds=start,
                on_close=self._on_ws_close,
            )
        except Exception as exc:
            self._report_start_error(exc)
            return

        capture = AudioCapture(
            self._capture_config(),
            on_pcm=client.send_pcm,
            on_error=self._on_capture_error,
        )
        try:
            capture.start()
        except Exception as exc:
            client.close_ws()
            self._report_start_error(exc)
            return

        self.client = client
        self.capture = capture
        self._active = True
        with self._cue_lock:
            self._cues = []
        xbmc.log(f"[SubFly] live capture started (item: {path or 'unknown source'})", xbmc.LOGINFO)
        self._notify_connected()

    # --- file-path mode (opt-in fast path for resolvable local files) -----
    def _start_file_session_unlocked(self, path: str, start: float, gen: int) -> None:
        if not path:
            xbmc.log(
                "[SubFly] file_path mode needs a resolvable file but none was reported; "
                "switch capture_mode to live_capture for this source",
                xbmc.LOGWARNING,
            )
            if self._notify_errors():
                xbmcgui.Dialog().notification(
                    "SubFly",
                    "No file path for this source — switch to live capture mode",
                    xbmcgui.NOTIFICATION_WARNING,
                    5000,
                )
            return

        url = self._base_url()
        token = self._token()
        language = self._language()

        client = SubFlyClient(url, token)
        try:
            health = client.health()
            if not health.get("ok"):
                raise RuntimeError("service unhealthy")
            info = client.start_session(path, start_seconds=start, language=language)
            sid = info["session_id"]
            client.connect_session_ws(sid, on_message=self._on_ws_message, on_close=self._on_ws_close)
        except Exception as exc:
            self._report_start_error(exc)
            return

        self.client = client
        self._active = True
        with self._cue_lock:
            self._cues = []
        xbmc.log(f"[SubFly] file session started for {path}", xbmc.LOGINFO)
        self._notify_connected()

    def _report_start_error(self, exc: Exception) -> None:
        xbmc.log(f"[SubFly] failed to start session: {exc}", xbmc.LOGERROR)
        if self._notify_errors():
            xbmcgui.Dialog().notification(
                "SubFly",
                f"Cannot reach service: {exc}",
                xbmcgui.NOTIFICATION_ERROR,
                5000,
            )

    def _notify_connected(self) -> None:
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
        with self._cue_lock:
            self._cues = []
        self.overlay.clear()
        if self.capture:
            try:
                self.capture.stop()
            except Exception:
                pass
            self.capture = None
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
                    if len(self._cues) > 200:
                        self._cues = self._cues[-100:]
        elif typ == "error":
            msg = data.get("message", "unknown error")
            xbmc.log(f"[SubFly] server error: {msg}", xbmc.LOGERROR)
            if self._notify_errors():
                xbmcgui.Dialog().notification("SubFly", str(msg), xbmcgui.NOTIFICATION_ERROR, 5000)

    def _on_capture_error(self, message: str) -> None:
        xbmc.log(f"[SubFly] audio capture error: {message}", xbmc.LOGERROR)
        if self._notify_errors():
            xbmcgui.Dialog().notification(
                "SubFly",
                "Audio capture failed — check capture backend/device settings",
                xbmcgui.NOTIFICATION_ERROR,
                6000,
            )

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
            self._cues = [c for c in self._cues if c["end"] + 1.0 >= position]
            if due:
                cue = due[-1]
                active_text = cue["text"]
                hold = max(1.5, cue["end"] - position + 0.5)
        if active_text:
            self.overlay.show(active_text, hold_seconds=hold)
