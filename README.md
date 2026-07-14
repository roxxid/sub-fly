# SubFly

Reusable **server + clients** for live English subtitles.

```
┌─────────────────────┐         REST / WebSocket          ┌──────────────────────────┐
│  Client             │ ────────────────────────────────► │  Server (Docker + GPU)   │
│  • Kodi addon       │   media path + playback clock     │  faster-whisper on CUDA  │
│  • Python SDK / CLI │ ◄──────────────────────────────── │  ffmpeg audio demux      │
│  • your own app     │         timed subtitle cues       │  Tesla T4 / any CUDA GPU │
└─────────────────────┘                                   └──────────────────────────┘
```

Anyone can reuse:

- **`server/`** — build/run the Docker image on Unraid (or any NVIDIA host)
- **`clients/kodi/`** — Kodi service addon that overlays live captions
- **`clients/python/`** — stdlib Python SDK + CLI for other apps
- **`PROTOCOL.md`** — the wire contract so you can write new clients

## Quick start

### 1. Server (Unraid + Tesla T4)

```bash
cd server
cp .env.example .env
# set MEDIA_PATH and SUBFLY_PATH_MAPS for your library
docker compose up -d --build
curl http://<unraid-ip>:8765/healthz
```

See [server/README.md](server/README.md).

### 2a. Kodi client

```bash
python3 scripts/package-kodi-addon.py
# Install dist/service.subfly-1.0.0.zip in Kodi
# Settings → service URL → http://<unraid-ip>:8765
```

### 2b. Python client (any app)

```bash
pip install -e clients/python
subfly health --url http://<unraid-ip>:8765
subfly transcribe --url http://<unraid-ip>:8765 --media /media/Movies/film.mkv
```

See [clients/python/README.md](clients/python/README.md) and [PROTOCOL.md](PROTOCOL.md).

## Repo layout

| Path | Role |
|------|------|
| `server/` | Dockerized transcription service (server-side) |
| `clients/kodi/service.subfly/` | Kodi plugin (client-side) |
| `clients/python/subfly/` | Reusable Python client SDK |
| `PROTOCOL.md` | API contract for third-party clients |
| `scripts/` | Package addon / Unraid helper |

## How a session works

1. Client starts playback and `POST /v1/sessions` with the media path + clock
2. Server maps the path, extracts audio, runs Whisper on the GPU
3. Client opens `WS /v1/ws/{session_id}` and receives `subtitle` events
4. Client shows text when the player time falls inside each cue’s `start`/`end`

## Path mapping

Players and Docker often see different mount prefixes for the same files:

```env
MEDIA_PATH=/mnt/user/media
SUBFLY_PATH_MAPS=/media=/data
```

Kodi path `/media/Movies/x.mkv` → container `/data/Movies/x.mkv`.

## License

MIT
