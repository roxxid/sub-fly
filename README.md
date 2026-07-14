# SubFly

Live English subtitles for Kodi, transcribed on your Unraid server with a Tesla T4.

When any video plays in Kodi, the SubFly addon tells the GPU service which file is playing. The service demuxes audio with ffmpeg, runs **faster-whisper** on CUDA, and streams caption cues back. The addon overlays them on screen in near real time.

```
Kodi (any video)
   │  media path + playback clock
   ▼
SubFly addon  ──WebSocket/REST──►  SubFly Docker (Unraid + Tesla T4)
   ▲                                 faster-whisper + ffmpeg
   └──────── live English cues ──────┘
```

## What's in this repo

| Path | Purpose |
|------|---------|
| `service/` | FastAPI + faster-whisper Docker service (GPU) |
| `kodi-addon/service.subfly/` | Kodi service addon (overlay + playback sync) |
| `scripts/` | Unraid install helper + addon zip packager |

## Requirements

**Unraid server**
- NVIDIA Driver community app installed
- Tesla T4 (16GB) or any CUDA GPU with enough VRAM
- Docker with GPU access (`gpus: all` / nvidia runtime)
- Media share mounted so the container can read the same files Kodi plays

**Kodi**
- Kodi 19+ (Matrix / Nexus / Omega)
- Network reachability to the Unraid host on port `8765`
- Playing files that resolve to real paths or HTTP(S) streams (not `plugin://` sources the server can't open)

## 1. Deploy the GPU service on Unraid

```bash
cd service
cp .env.example .env
# Edit MEDIA_PATH and SUBFLY_PATH_MAPS to match your library
docker compose up -d --build
```

Or run `scripts/unraid-install.sh`.

### Path mapping (important)

Kodi and Docker often see different mount prefixes for the same files.

Example:
- Kodi path: `/media/Movies/Inception.mkv`
- Unraid share in container: `/data/Movies/Inception.mkv`

Set:

```env
MEDIA_PATH=/mnt/user/media
SUBFLY_PATH_MAPS=/media=/data
```

Add more maps as comma-separated `src=dst` pairs:

```env
SUBFLY_PATH_MAPS=/media=/data,/mnt/user/media=/data
```

### Model choice

| Model | VRAM (approx) | Quality / latency |
|-------|---------------|-------------------|
| `small` | ~2GB | Fast, good for testing |
| `medium` | ~5GB | Strong balance |
| `large-v3` (default) | ~10GB | Best English quality on T4 |

```env
SUBFLY_MODEL_SIZE=large-v3
SUBFLY_COMPUTE_TYPE=float16
```

First start downloads the model into the `subfly-models` volume (can take several minutes).

### Health check

```bash
curl http://<unraid-ip>:8765/healthz
# {"ok":true,"version":"1.0.0","model_ready":true}
```

Optional auth: set `SUBFLY_API_TOKEN` and the same token in the Kodi addon settings.

## 2. Install the Kodi addon

```bash
python3 scripts/package-kodi-addon.py
# → dist/service.subfly-1.0.0.zip
```

On Kodi:
1. Settings → System → Add-ons → **Unknown sources** on
2. Add-ons → Install from zip file → select `service.subfly-1.0.0.zip`
3. Open **SubFly Live Subtitles** settings:
   - Enable live subtitles: **on**
   - Service URL: `http://<unraid-ip>:8765`
   - API token: only if you set one on the server
4. Restart Kodi (service addons load at startup)

Play any local/network video. You should get a "Live subtitles connected" toast, then captions along the bottom of the screen.

## API overview

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Liveness + model ready |
| `GET` | `/v1/info` | Model / config |
| `POST` | `/v1/sessions` | Start URL/file transcription `{"media_path","start_seconds","language"}` |
| `WS` | `/v1/ws/{session_id}` | Subtitle event stream + position/seek/pause control |
| `WS` | `/v1/live` | Alternate: push raw 16kHz mono s16le PCM, get captions |

Subtitle event:

```json
{"type":"subtitle","session_id":"...","start":12.4,"end":15.1,"text":"We're going to need a bigger boat.","language":"en"}
```

## Latency notes

Default chunk size is **3 seconds** of audio (`SUBFLY_CHUNK_SECONDS`). Lower values reduce delay but can hurt accuracy. With `large-v3` on a T4, expect roughly a few seconds of lag behind dialogue; the addon syncs cues to Kodi's playback clock so text appears at the right moment once transcribed.

Seek and pause are forwarded so the pipeline restarts or waits with the player.

## Limitations

- Sources Kodi plays via `plugin://` (YouTube, some scrapers) can't be opened by the server unless they expose a real HTTP stream URL.
- The container must be able to read the file (shared mount or reachable URL).
- DRM / encrypted streams are unsupported.
- Overlay styling is intentionally simple so it works across skins.

## Development

```bash
# Helper unit tests (no GPU)
cd service
pip install pytest numpy pydantic pydantic-settings
pytest -q
```

## License

MIT
