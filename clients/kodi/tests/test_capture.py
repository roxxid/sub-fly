# -*- coding: utf-8 -*-
"""Unit tests for the audio capture command builder (no ffmpeg required)."""

import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "service.subfly" / "resources" / "lib"
sys.path.insert(0, str(LIB))

from capture import CaptureConfig, build_capture_command  # noqa: E402


def test_pulse_default_device():
    cmd = build_capture_command(CaptureConfig(backend="pulse"))
    assert cmd[0] == "ffmpeg"
    assert "-f" in cmd and "pulse" in cmd
    assert "default.monitor" in cmd
    assert cmd[-1] == "pipe:1"
    assert "s16le" in cmd


def test_alsa_default_device():
    cmd = build_capture_command(CaptureConfig(backend="alsa"))
    assert "alsa" in cmd
    assert "hw:Loopback,1,0" in cmd


def test_device_override():
    cmd = build_capture_command(
        CaptureConfig(backend="pulse", device="alsa_output.custom.monitor")
    )
    assert "alsa_output.custom.monitor" in cmd
    assert "default.monitor" not in cmd


def test_dshow_and_avfoundation_presets():
    win = build_capture_command(CaptureConfig(backend="dshow"))
    assert "dshow" in win
    mac = build_capture_command(CaptureConfig(backend="avfoundation"))
    assert "avfoundation" in mac


def test_custom_backend_uses_raw_args():
    cmd = build_capture_command(
        CaptureConfig(backend="custom", custom_input_args="-f pulse -i my.monitor")
    )
    assert "-f" in cmd and "pulse" in cmd and "my.monitor" in cmd


def test_custom_backend_requires_args():
    with pytest.raises(ValueError):
        build_capture_command(CaptureConfig(backend="custom", custom_input_args=""))


def test_unknown_backend_rejected():
    with pytest.raises(ValueError):
        build_capture_command(CaptureConfig(backend="nope"))


def test_ffmpeg_path_override():
    cmd = build_capture_command(CaptureConfig(backend="pulse", ffmpeg_path="/usr/local/bin/ffmpeg"))
    assert cmd[0] == "/usr/local/bin/ffmpeg"


def test_sample_rate_and_channels():
    cmd = build_capture_command(CaptureConfig(backend="pulse", sample_rate=16000, channels=1))
    ar_idx = cmd.index("-ar")
    ac_idx = cmd.index("-ac")
    assert cmd[ar_idx + 1] == "16000"
    assert cmd[ac_idx + 1] == "1"
