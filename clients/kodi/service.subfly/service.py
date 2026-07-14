# -*- coding: utf-8 -*-
"""SubFly Kodi service entrypoint.

Starts at Kodi boot and watches for video playback. When a file starts,
connects to the SubFly GPU service and shows live English captions.
"""

from __future__ import annotations

import sys
import os

# Ensure resources/lib is importable
_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(_ADDON_DIR, "resources", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import xbmc
import xbmcaddon

from monitor import SubFlyMonitor  # noqa: E402


def main() -> None:
    addon = xbmcaddon.Addon()
    xbmc.log("[SubFly] service starting", xbmc.LOGINFO)
    monitor = SubFlyMonitor(addon)
    monitor.run()
    xbmc.log("[SubFly] service stopped", xbmc.LOGINFO)


if __name__ == "__main__":
    main()
