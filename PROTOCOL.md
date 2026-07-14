# SubFly protocol

Contract between any **client** and the **SubFly server** Docker image.
Stable enough to build third-party players/plugins against.

Base URL example: `http://<server>:8765`

Optional auth: send `X-Api-Token: <token>` or `Authorization: Bearer <token>`
(WebSocket: `?token=<token>`).

---

## REST

### `GET /healthz`

```json
{"ok": true, "version": "1.0.0", "model_ready": true}
```

### `GET /v1/info`

Model + config (requires token when configured).

### `POST /v1/sessions`

Start transcription of a media file/URL the server can open.

Request:

```json
{
  "media_path": "/media/Movies/film.mkv",
  "start_seconds": 0.0,
  "language": "en"
}
```

Response:

```json
{
  "session_id": "uuid",
  "resolved_path": "/data/Movies/film.mkv",
  "ws_url": "/v1/ws/uuid"
}
```

### `POST /v1/sessions/{id}/seek`

```json
{"position": 120.5}
```

### `POST /v1/sessions/{id}/pause`

```json
{"paused": true}
```

### `DELETE /v1/sessions/{id}`

Stop the session.

---

## WebSocket — file/URL session

`WS /v1/ws/{session_id}`

### Server → client events

| `type` | Meaning |
|--------|---------|
| `session_started` | Pipeline ready |
| `subtitle` | Caption cue (see below) |
| `seeked` / `paused` / `resumed` | Control acks |
| `pipeline_done` | ffmpeg/Whisper finished the file |
| `session_stopped` | Session torn down |
| `error` | `{ "message": "..." }` |

Subtitle cue:

```json
{
  "type": "subtitle",
  "session_id": "uuid",
  "start": 12.4,
  "end": 15.1,
  "text": "We're going to need a bigger boat.",
  "language": "en"
}
```

`start` / `end` are **media timestamps in seconds**. Clients should show a cue when the player clock is inside that range.

### Client → server controls

```json
{"type": "position", "position": 12.4}
{"type": "seek", "position": 90.0}
{"type": "pause", "paused": true}
{"type": "stop"}
```

Send `position` about once per second so the server stays roughly in sync with playback.

---

## WebSocket — live PCM (recommended default)

`WS /v1/live?language=en&start_seconds=0`

This is the **source-agnostic mode**: the server never opens a file, so it
works for anything a client can capture audio from — local files, external
add-on libraries, live TV/PVR, plugin sources, DRM content post-decode,
screen/system audio, anything. All three bundled clients (`clients/kodi`,
`clients/android`, `clients/python`) use this by default.

1. Connect (optionally with `?token=`)
2. Send binary frames continuously: **16 kHz mono PCM s16le**, for as long
   as something is playing — this is genuinely a live, continuous, two-way
   stream, not a one-shot request
3. Receive `subtitle` events (same shape as above) as they're transcribed
4. Send JSON control messages, ideally about once a second:
   - `{"type": "position", "position": 12.4}` — current playback clock
   - `{"type": "seek", "position": 90.0}` — same effect as `position`, sent
     right after a seek so the server resyncs immediately instead of
     waiting for the next tick
   - `{"type": "pause", "paused": true}` — server stops transcribing
     incoming audio while paused (send this immediately on pause/resume,
     not just on the next tick)
   - `{"type": "stop"}` — end the session

### Timestamp sync

Cue `start`/`end` values are computed from a running "expected playback
position" the server maintains per session, seeded from `start_seconds` and
advanced by `chunk_seconds` after every processed chunk. Whenever the
client's reported `position` drifts from that running value by more than
~1.5 chunk-lengths (a seek, a live-TV channel change, a long pause), the
server snaps its internal offset to match instead of accumulating drift
forever. Send `position` regularly and send `seek` immediately after a user
seek so this recovers fast.

---

## Path mapping

Servers often mount media at a different prefix than the player.

Configure `SUBFLY_PATH_MAPS=src=dst,src2=dst2` on the server so clients can send their native paths (e.g. Kodi `/media/...` → container `/data/...`).
