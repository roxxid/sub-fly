# SubFly Python client

Reusable stdlib-only client for any app that talks to a SubFly server.

```bash
pip install -e clients/python
subfly health --url http://192.168.1.50:8765
subfly transcribe --url http://192.168.1.50:8765 --media /media/Movies/film.mkv
```

```python
from subfly import SubFlyClient, SubtitleCue

client = SubFlyClient("http://192.168.1.50:8765")
session = client.start_session("/media/Movies/film.mkv", start_seconds=12.0)

def on_event(msg):
    if isinstance(msg, dict) and msg.get("type") == "subtitle":
        cue = SubtitleCue.from_message(msg)
        print(cue.start, cue.text)

client.connect_session_ws(session["session_id"], on_message=on_event)
```

Works without Kodi. Build your own player integration (VLC, mpv, web UI, etc.) against the same server protocol.
