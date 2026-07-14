# SubFly Kodi client (desktop / LibreELEC / CoreELEC / Windows / macOS)

Kodi service addon for builds where Kodi's Python can spawn a subprocess:
**Windows, macOS, desktop Linux, LibreELEC, CoreELEC**.

**Running Kodi on an Android TV stick or box?** Use
[`clients/android`](../android/README.md) instead — Kodi's Android APK is
sandboxed and can't run `ffmpeg`/PulseAudio the way this addon does. The
Android app captures system audio a different way and doesn't need this
addon installed at all.

Source lives in `service.subfly/` (Kodi requires the folder name to match the addon id).

```bash
python3 scripts/package-kodi-addon.py
# → dist/service.subfly-1.0.0.zip
```

In Kodi: install from zip, set **SubFly service URL** to your server, enable live subtitles.

## Capture modes

- **Live capture (default)** — spawns `ffmpeg` to grab the audio Kodi is
  outputting (PulseAudio/PipeWire monitor, ALSA loopback, a Windows virtual
  cable, or a macOS BlackHole device) and streams it continuously. Works for
  literally anything Kodi can play out loud: local files, external add-on
  libraries, live TV/PVR, plugin sources, DRM content post-decode.
- **File path (opt-in)** — tells the server to open the exact file Kodi
  reports playing. Slightly faster and needs no local capture setup, but
  only works when Kodi reports a real, server-reachable path — it fails for
  add-ons/plugins, live TV, and DRM.

Set both in the addon's settings under **Audio capture**. See platform setup
below for the capture backend/device fields.

### Linux (PulseAudio/PipeWire) — LibreELEC, CoreELEC, desktop

Most LibreELEC/CoreELEC builds run PipeWire's Pulse-compatible layer or
plain PulseAudio. Backend: `pulse`, device left blank uses
`default.monitor`. If that doesn't pick up Kodi's audio, list monitor
sources:

```bash
pactl list sources short | grep monitor
```

and put the exact name in **Capture device**.

### Linux (ALSA only, no Pulse)

Some CoreELEC/LibreELEC images run ALSA directly. Load a loopback device:

```bash
modprobe snd-aloop
```

Backend: `alsa`, device `hw:Loopback,1,0` (default). Route Kodi's audio
output to the loopback capture side via your platform's ALSA/asound
configuration — this varies by image, check your distro's audio docs.

### Windows

Install a virtual audio cable (e.g. VB-Audio Virtual Cable), set it as
Kodi's playback device (or use Windows' "Listen to this device" /
Stereo Mix to loop the default output back as a capture device). Backend:
`dshow`, device e.g. `audio=Virtual Cable` — adjust to match the exact
device name shown by:

```bash
ffmpeg -list_devices true -f dshow -i dummy
```

### macOS

Install [BlackHole](https://existential.audio/blackhole/) (2ch), set it as
an aggregate output alongside your speakers so you still hear audio, and set
Kodi to output there. Backend: `avfoundation`, device `:BlackHole 2ch`
(default) — list devices with:

```bash
ffmpeg -f avfoundation -list_devices true -i ""
```

### Custom

Backend `custom` + **Custom ffmpeg input arguments** lets you pass any
ffmpeg input verbatim, e.g. `-f pulse -i alsa_output.pci-0000_00_1f.3.monitor`.

## Protocol

This client speaks the same protocol as `clients/python` and
`clients/android` — see [PROTOCOL.md](../../PROTOCOL.md).
