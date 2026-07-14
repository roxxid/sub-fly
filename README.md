# SubFly

Reusable **server + clients** for live English subtitles on anything Kodi plays.

```
┌────────────────────────────┐         REST / WebSocket          ┌──────────────────────────┐
│  Client                    │ ────────────────────────────────► │  Server (Docker + GPU)   │
│  • Kodi addon (desktop)    │   continuous audio + playback      │  faster-whisper on CUDA  │
│  • Android TV app          │   clock, source-agnostic          │  Tesla T4 / any CUDA GPU │
│  • Python SDK / your app   │ ◄──────────────────────────────── │                          │
└────────────────────────────┘         timed subtitle cues       └──────────────────────────┘
```

Clients don't tell the server "open this file." They capture the actual
audio being played — post-decode, so the source doesn't matter — and stream
it continuously for as long as something is playing. That's what makes this
work for external add-on libraries, live TV/PVR, plugin sources, and DRM
content, not just plain local files.

Anyone can reuse:

- **`server/`** — build/run the Docker image on Unraid (or any NVIDIA host)
- **`clients/kodi/`** — Kodi service addon for desktop/LibreELEC/CoreELEC/Windows/macOS
- **`clients/android/`** — native app for Kodi on Android TV sticks/boxes (Shield, Chromecast with Google TV, generic boxes; see caveats for Fire TV)
- **`clients/python/`** — stdlib Python SDK + CLI for other apps
- **`PROTOCOL.md`** — the wire contract so you can write new clients

## Quick start

### 1. Server (Unraid + Tesla T4)

```bash
cd server
cp .env.example .env
docker compose up -d --build
curl http://<unraid-ip>:8765/healthz
```

See [server/README.md](server/README.md).

### 2. Pick your client(s)

| Where Kodi runs | Use |
|---|---|
| Windows / macOS / desktop Linux / LibreELEC / CoreELEC | [clients/kodi](clients/kodi/README.md) — Python addon, spawns ffmpeg against a loopback audio device |
| Android TV stick/box (Shield, Chromecast with Google TV, generic Android TV, Fire TV*) | [clients/android](clients/android/README.md) — native app using `AudioPlaybackCaptureConfiguration` |
| Anything else / building your own integration | [clients/python](clients/python/README.md) — SDK + CLI, or implement [PROTOCOL.md](PROTOCOL.md) directly |

\* Fire TV runs Fire OS, an Android fork — the APIs this depends on are
generally present but not guaranteed identical across Amazon's builds. Test
on your device; see [clients/android/README.md](clients/android/README.md#a-real-caveat-fire-tv).

Kodi's Android build is sandboxed and can't spawn `ffmpeg`/PulseAudio like
desktop builds — that's why Android gets its own native app instead of a
Python addon. It captures system audio via Android's own API and reads
playback state from Kodi's JSON-RPC, so no Kodi addon install is needed on
that platform at all.

## Repo layout

| Path | Role |
|------|------|
| `server/` | Dockerized transcription service (server-side) |
| `clients/kodi/service.subfly/` | Kodi plugin for desktop-class platforms |
| `clients/android/` | Native Android TV app (Kotlin/Gradle) |
| `clients/python/subfly/` | Reusable Python client SDK |
| `PROTOCOL.md` | API contract for third-party clients |
| `scripts/` | Package addon / Unraid helper |

## How a session works

1. Client detects playback started (Kodi Player events, or polling Kodi's
   JSON-RPC on Android) and opens `WS /v1/live?language=...&start_seconds=...`
2. Client streams 16kHz mono PCM continuously — captured from system audio
   output, not read from the source file — for as long as something plays
3. Client sends `position` updates about once a second so the server keeps
   caption timestamps anchored to the real playback clock (handles seeks,
   live-TV channel jumps, pause gaps)
4. Server runs Whisper on the GPU and streams back `subtitle` cues
5. Client shows text when the player time falls inside a cue's `start`/`end`

An alternate `POST /v1/sessions` + file-path flow exists for cases where a
client can hand the server a directly-openable local/network path and wants
to skip local audio capture — see [PROTOCOL.md](PROTOCOL.md) — but it only
works for plain resolvable files, not add-ons/live TV/DRM.

## License

MIT
