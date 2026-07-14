"""Unit tests for SubFly service helpers (no GPU required)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.audio import pcm_s16le_to_float32
from app.pathmap import rewrite_media_path


def test_rewrite_local_path_map():
    mapped = rewrite_media_path(
        "/media/Movies/Film.mkv",
        [("/media", "/data")],
    )
    assert mapped == "/data/Movies/Film.mkv"


def test_rewrite_longest_prefix_wins():
    mapped = rewrite_media_path(
        "/media/tv/Show/S01E01.mkv",
        [("/media", "/data"), ("/media/tv", "/tv")],
    )
    assert mapped == "/tv/Show/S01E01.mkv"


def test_rewrite_http_passthrough():
    url = "http://nas:8096/Videos/123/stream"
    assert rewrite_media_path(url, [("/media", "/data")]) == url


def test_rewrite_file_url():
    mapped = rewrite_media_path("file:///media/Movies/A.mkv", [("/media", "/data")])
    assert mapped == "/data/Movies/A.mkv"


def test_reject_plugin_urls():
    with pytest.raises(ValueError):
        rewrite_media_path("plugin://plugin.video.youtube/play/", [])


def test_pcm_conversion_roundtrip_scale():
    samples = [0, 16384, -16384, 32767]
    pcm = struct.pack("<4h", *samples)
    arr = pcm_s16le_to_float32(pcm)
    assert isinstance(arr, np.ndarray)
    assert arr.dtype == np.float32
    assert arr.shape == (4,)
    assert abs(arr[1] - 0.5) < 0.01
