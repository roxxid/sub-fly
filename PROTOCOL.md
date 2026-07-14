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
  "language": "en",
  "vocabulary_hint": "The Wrath of Khan. Characters/cast: Spock, Uhura, Khan Noonien Singh. Science Fiction."
}
```

`vocabulary_hint` is optional. See "Vocabulary hints" below.

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
{"type": "vocabulary_hint", "text": "..."}
{"type": "stop"}
```

Send `position` about once per second so the server stays roughly in sync with playback.

---

## WebSocket — live PCM (recommended default)

`WS /v1/live?language=en&start_seconds=0&vocabulary_hint=<url-encoded text>`

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
   - `{"type": "vocabulary_hint", "text": "..."}` — update the hotwords
     hint mid-session (metadata arrived late, or the item changed without
     a full session restart)
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

## Vocabulary hints (character/place names, in-universe terms)

Whisper models are trained on general-purpose vocabulary statistics, so
they're noticeably better at common dictionary words than at invented or
obscure proper nouns — a fictional character or place name unique to one
movie/show has no statistical support in the model's decoder unless that
specific title happens to be well-represented in Whisper's training data
(popular franchises usually are; small/indie/foreign productions with
invented names often aren't).

`vocabulary_hint` is optional free text (title, character/cast names, plot,
genre — anything that names the specific proper nouns of what's playing).
The server forwards it verbatim to faster-whisper's
[`hotwords`](https://github.com/SYSTRAN/faster-whisper) parameter, which
biases decoding toward that vocabulary for every chunk. It measurably helps
for content with rich, easily obtained metadata (a scraped Kodi library
item); it does nothing for content with none (an unscraped file, most
add-on/plugin streams) — that's fine, transcription just falls back to
Whisper's default behavior, it doesn't get *worse*.

The server truncates it to ~600 characters (well under faster-whisper's
~223-token internal limit for `hotwords`) and collapses whitespace; there's
no need for a client to pre-truncate beyond staying roughly in that range.
This is a bias, not a guarantee — it does not make transcription of truly
obscure invented terminology perfect, and it doesn't help with unrelated
sources of error (background music, heavy accents, overlapping dialogue,
whispered/shouted delivery). All three bundled clients build this
automatically from whatever metadata Kodi has for the currently playing
item (see `clients/kodi/service.subfly/resources/lib/hints.py` and
`clients/android/.../KodiRpcClient.kt#getNowPlayingHint`); pass an empty
string if you have nothing useful.

---

## Path mapping

Servers often mount media at a different prefix than the player.

Configure `SUBFLY_PATH_MAPS=src=dst,src2=dst2` on the server so clients can send their native paths (e.g. Kodi `/media/...` → container `/data/...`).
