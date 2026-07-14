# SubFly Kodi client

Installable Kodi service addon that consumes a SubFly **server**.

Source lives in `service.subfly/` (Kodi requires the folder name to match the addon id).

```bash
python3 scripts/package-kodi-addon.py
# → dist/service.subfly-1.0.0.zip
```

In Kodi: install from zip, set **SubFly service URL** to your server, enable live subtitles.

This client speaks the same protocol as `clients/python` — see [PROTOCOL.md](../../PROTOCOL.md).
