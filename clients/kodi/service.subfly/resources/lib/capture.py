# -*- coding: utf-8 -*-
"""System audio loopback capture, independent of what Kodi is playing.

Instead of asking the server to open "the file" (which fails for external
add-ons, live TV/PVR, plugin sources, and DRM content), this captures the
actual audio Kodi is *outputting* on the local machine and streams it
continuously. Since capture happens after decode, it works for anything
Kodi can play out loud.

This module has no xbmc/Kodi imports so it can be unit tested and reused
outside Kodi if needed.
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Optional

# Sensible per-platform defaults. Users can override every field in
# settings; these just make first-run setup less painful on common builds.
BACKEND_PRESETS: dict[str, dict[str, str]] = {
    "pulse": {"format": "pulse", "default_device": "default.monitor"},
    "alsa": {"format": "alsa", "default_device": "hw:Loopback,1,0"},
    "dshow": {"format": "dshow", "default_device": "audio=virtual-audio-capturer"},
    "avfoundation": {"format": "avfoundation", "default_device": ":BlackHole 2ch"},
}


@dataclass
class CaptureConfig:
    ffmpeg_path: str = "ffmpeg"
    backend: str = "pulse"  # pulse | alsa | dshow | avfoundation | custom
    device: str = ""  # overrides the backend's default_device when set
    sample_rate: int = 16000
    channels: int = 1
    custom_input_args: str = ""  # used verbatim when backend == "custom"

    def resolved_device(self) -> str:
        if self.device:
            return self.device
        preset = BACKEND_PRESETS.get(self.backend)
        return preset["default_device"] if preset else ""


def build_capture_command(config: CaptureConfig) -> list[str]:
    """Build the ffmpeg command that captures loopback audio to stdout PCM."""
    if config.backend == "custom":
        if not config.custom_input_args.strip():
            raise ValueError("custom backend requires custom_input_args")
        input_args = config.custom_input_args.strip().split()
    else:
        preset = BACKEND_PRESETS.get(config.backend)
        if not preset:
            raise ValueError(f"unknown capture backend: {config.backend}")
        input_args = ["-f", preset["format"], "-i", config.resolved_device()]

    return [
        config.ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        *input_args,
        "-vn",
        "-ac",
        str(config.channels),
        "-ar",
        str(config.sample_rate),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "pipe:1",
    ]


class AudioCapture:
    """Runs ffmpeg as a subprocess and streams raw PCM to a callback.

    Requires Kodi's Python runtime to allow `subprocess` (true on desktop
    Linux/LibreELEC/CoreELEC, Windows, and macOS builds; not available on
    the Android/iOS app sandbox — see clients/kodi/README.md).
    """

    def __init__(
        self,
        config: CaptureConfig,
        on_pcm: Callable[[bytes], None],
        *,
        on_error: Optional[Callable[[str], None]] = None,
        read_bytes: int = 8192,
    ) -> None:
        self.config = config
        self.on_pcm = on_pcm
        self.on_error = on_error
        self.read_bytes = read_bytes
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.running:
            return
        cmd = build_capture_command(self.config)
        self._stop.clear()
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._thread = threading.Thread(target=self._pump, name="subfly-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _pump(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while not self._stop.is_set():
                chunk = proc.stdout.read(self.read_bytes)
                if not chunk:
                    break
                self.on_pcm(chunk)
        except Exception as exc:
            if self.on_error:
                try:
                    self.on_error(str(exc))
                except Exception:
                    pass
        finally:
            if not self._stop.is_set() and self.on_error:
                stderr = b""
                try:
                    if proc.stderr:
                        stderr = proc.stderr.read()
                except Exception:
                    pass
                if stderr:
                    try:
                        self.on_error(stderr.decode(errors="replace"))
                    except Exception:
                        pass
