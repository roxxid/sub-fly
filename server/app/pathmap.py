"""Path rewriting between Kodi client paths and container mounts."""

from __future__ import annotations

import os
from urllib.parse import unquote, urlparse


def rewrite_media_path(raw_path: str, path_maps: list[tuple[str, str]]) -> str:
    """Map a Kodi file path/URL to a path the container can open.

    Supports:
    - Local absolute paths with configured prefix rewrites
    - smb:// / nfs:// left as-is for ffmpeg (when credentials are in the URL)
    - http(s)/rtsp streams left as-is
    """
    if not raw_path:
        raise ValueError("empty media path")

    path = unquote(raw_path.strip())

    # Special protocol: plugin:// etc. cannot be fetched server-side
    parsed = urlparse(path)
    if parsed.scheme in {"plugin", "addons", "pvr"}:
        raise ValueError(
            f"unsupported media scheme '{parsed.scheme}': "
            "SubFly needs a real file path or stream URL"
        )

    if parsed.scheme in {"http", "https", "rtsp", "rtsps", "rtmp", "udp", "tcp"}:
        return path

    if parsed.scheme in {"smb", "nfs", "ftp", "sftp"}:
        return path

    # file:// URLs
    if parsed.scheme == "file":
        path = unquote(parsed.path)

    # Apply prefix maps (longest prefix first)
    for src, dst in sorted(path_maps, key=lambda p: len(p[0]), reverse=True):
        if path.startswith(src):
            mapped = dst + path[len(src) :]
            return mapped

    return path


def media_exists(path: str) -> bool:
    """True when the path is a local file that exists."""
    parsed = urlparse(path)
    if parsed.scheme and parsed.scheme not in {"", "file"}:
        return True  # remote URL — let ffmpeg decide
    return os.path.isfile(path)
