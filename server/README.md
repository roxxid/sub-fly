# SubFly server

Docker image that runs live English speech-to-text on a CUDA GPU (Tesla T4 and friends).

Clients (Kodi addon, Python SDK, or anything speaking [PROTOCOL.md](../PROTOCOL.md)) send a media path; this service demuxes audio and streams subtitle cues back.

## Build

```bash
cd server
docker build -t subfly-server:1.0.0 .
```

## Run (Unraid / NVIDIA)

```bash
cp .env.example .env
# MEDIA_PATH=/mnt/user/media
# SUBFLY_PATH_MAPS=/media=/data
docker compose up -d
```

Older Unraid nvidia runtime:

```bash
docker compose -f docker-compose.unraid.yml up -d --build
```

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `SUBFLY_MODEL_SIZE` | `large-v3` | Whisper model |
| `SUBFLY_DEVICE` | `cuda` | `cuda` or `cpu` |
| `SUBFLY_COMPUTE_TYPE` | `float16` | CTranslate2 compute type |
| `SUBFLY_LANGUAGE` | `en` | Output language |
| `SUBFLY_PATH_MAPS` | `/media=/data` | Client path → container path |
| `SUBFLY_API_TOKEN` | _(empty)_ | Optional shared secret |
| `SUBFLY_CHUNK_SECONDS` | `3.0` | Audio window size — smaller is lower latency, larger gives Whisper more context per chunk |
| `SUBFLY_BEAM_SIZE` | `5` | Beam search width — higher can improve accuracy at the cost of GPU time per chunk |
| `SUBFLY_VAD_FILTER` | `true` | Skip silent stretches with Silero VAD before transcribing |

See ["How accurate is this, really?"](../README.md#how-accurate-is-this-really) in the top-level README for what actually moves accuracy, including the per-session `vocabulary_hint` mechanism (documented in [PROTOCOL.md](../PROTOCOL.md#vocabulary-hints-characterplace-names-in-universe-terms)).

## Publish (optional)

```bash
docker tag subfly-server:1.0.0 your-registry/subfly-server:1.0.0
docker push your-registry/subfly-server:1.0.0
```

Others can then run your image without building from source.
