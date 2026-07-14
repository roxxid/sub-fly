"""SubFly client SDK — talk to a SubFly transcription server from any Python app."""

from .client import SubFlyClient, SubFlyError, SubtitleCue
from .ws import WebSocketClient, WebSocketError, build_ws_url

__all__ = [
    "SubFlyClient",
    "SubFlyError",
    "SubtitleCue",
    "WebSocketClient",
    "WebSocketError",
    "build_ws_url",
]
__version__ = "1.0.0"
