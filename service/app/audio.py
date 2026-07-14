"""ffmpeg helpers for extracting PCM audio from media."""

from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import AsyncIterator
from typing import Optional

log = logging.getLogger("subfly.audio")


async def stream_pcm_chunks(
    media_path: str,
    *,
    sample_rate: int = 16000,
    start_seconds: float = 0.0,
    chunk_seconds: float = 3.0,
    channels: int = 1,
) -> AsyncIterator[tuple[float, bytes]]:
    """Yield (chunk_start_time, s16le PCM bytes) from a media file/URL.

    Uses ffmpeg to decode and resample audio to mono PCM for Whisper.
    """
    bytes_per_sample = 2 * channels
    chunk_bytes = int(sample_rate * chunk_seconds * bytes_per_sample)
    if chunk_bytes <= 0:
        raise ValueError("invalid chunk size")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, start_seconds):.3f}",
        "-i",
        media_path,
        "-vn",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "pipe:1",
    ]

    log.info("starting ffmpeg for %s @ %.2fs", media_path, start_seconds)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None

    buffer = bytearray()
    offset = max(0.0, start_seconds)
    try:
        while True:
            data = await proc.stdout.read(65536)
            if not data:
                break
            buffer.extend(data)
            while len(buffer) >= chunk_bytes:
                chunk = bytes(buffer[:chunk_bytes])
                del buffer[:chunk_bytes]
                yield offset, chunk
                offset += chunk_seconds
        if len(buffer) >= sample_rate * bytes_per_sample * 0.4:
            # pad last partial chunk with silence so Whisper gets a full window
            pad = chunk_bytes - len(buffer)
            if pad > 0:
                buffer.extend(b"\x00" * pad)
            yield offset, bytes(buffer[:chunk_bytes])
    finally:
        if proc.returncode is None:
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
        stderr = b""
        if proc.stderr is not None:
            try:
                stderr = await proc.stderr.read()
            except Exception:
                pass
        if proc.returncode not in (0, None, -9) and stderr:
            log.warning("ffmpeg exited %s: %s", proc.returncode, stderr.decode(errors="replace"))


def pcm_s16le_to_float32(pcm: bytes) -> "object":
    """Convert s16le PCM bytes to float32 numpy array in [-1, 1]."""
    import numpy as np

    if not pcm:
        return np.zeros(0, dtype=np.float32)
    count = len(pcm) // 2
    samples = struct.unpack(f"<{count}h", pcm[: count * 2])
    return (np.asarray(samples, dtype=np.float32) / 32768.0).astype(np.float32)


async def probe_duration(media_path: str) -> Optional[float]:
    """Return media duration in seconds, or None if unknown."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        media_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    try:
        return float(out.decode().strip())
    except (ValueError, AttributeError):
        return None
