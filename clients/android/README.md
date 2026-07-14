# SubFly Captions — Android TV client

A native Android app for the sticks where a Kodi Python addon can't do audio
capture: **Android TV boxes and sticks** (Nvidia Shield, Chromecast with
Google TV, generic Android TV boxes, Fire TV — see caveat below).

Kodi's Android build runs in a sandboxed APK. It can't spawn `ffmpeg`, can't
open a PulseAudio/ALSA loopback device, and there's no shell to shell out to.
The only thing that works on stock Android is Android's own system audio
capture API. So this is a **separate app**, installed alongside Kodi on the
same stick, that:

1. Captures whatever audio Android is currently outputting (post-decode, so
   it doesn't matter if Kodi is playing a local file, an add-on stream, live
   TV/PVR, or DRM content — by the time it reaches the speakers it's just
   PCM)
2. Streams it continuously to your SubFly server over `/v1/live`
3. Polls Kodi's own JSON-RPC API to know the current playback clock/pause
   state
4. Draws captions in a system overlay window on top of Kodi

No Kodi addon is required on Android — this app replaces that role entirely
for this platform, because it reads playback state straight from Kodi's
JSON-RPC instead of via Kodi's Python API.

## Requirements

- **Android 10 (API 29) or newer.** `AudioPlaybackCaptureConfiguration` (the
  API this depends on) doesn't exist before that. Most current Android TV
  sticks and Shields qualify; very old boxes on Android 7/8/9 cannot run this
  — there's no software fix for that, see "If your device is too old" below.
- Kodi's built-in web server enabled: **Kodi → Settings → Services →
  Control → Allow remote control via HTTP** (leave it on default port 8080,
  or set a username/password and enter the same in this app).
- Network reachability from the stick to your SubFly server.

### A real caveat: Fire TV

Fire TV devices run Amazon's Fire OS, a fork of Android. `AudioPlaybackCaptureConfiguration`
and the overlay/foreground-service APIs this app uses are part of stock
Android and are generally present on Fire OS too (Fire OS tracks AOSP fairly
closely), but Amazon's own apps and Kodi builds can vary in whether they set
`android:allowAudioPlaybackCapture="false"`, and MediaProjection's consent
dialog can behave differently across Fire TV launchers. **Test it on your
specific Fire TV model before relying on it.** If capture produces only
silence, the source app (Kodi) or the OS is blocking capture — see
Troubleshooting.

## Build

```bash
cd clients/android
./gradlew assembleDebug
# → app/build/outputs/apk/debug/app-debug.apk
```

This project was built and verified in CI-equivalent conditions (real
Android SDK 34 + Gradle 8.9): `assembleDebug` and `lintDebug` both pass
clean, no errors or warnings.

Install over ADB (enable Developer options → USB/network debugging on the
stick first — Settings → Device Preferences → About → tap the build number
7 times, then Developer options → Network debugging):

```bash
adb connect <stick-ip>:5555
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

This is the important bit if your stick's launcher is locked down and hides
the "install unknown apps" toggle: `adb install` doesn't go through that UI
flag at all. As long as network/USB debugging is reachable, you can install
this app even on devices where the on-screen settings for sideloading are
missing or disabled. If Kodi itself is sideloaded on the stick (it almost
certainly is, since Kodi isn't Play-Store-distributed for Android TV in most
regions), this app installs through the exact same path and carries the same
trust level — it's not a step up in privilege from what you already did to
get Kodi running.

From the repo root, `make android-deploy STICK=192.168.1.50` (or just
`make android-connect STICK=... && make android-install` /
`make android-build` individually) wraps the build+connect+install+launch
sequence above.

If you'd rather not use adb at all, sideload the APK via a file manager /
"Send files to TV" app instead — same APK, no adb required either way.

## Setup on the device

1. Open **SubFly Captions**.
2. Enter your SubFly **server URL** (e.g. `http://192.168.1.50:8765`), API
   token if you set one, and language.
3. Confirm the **Kodi JSON-RPC** host/port. Leave host as `127.0.0.1` since
   this app and Kodi run on the same device; only change the port if you
   changed Kodi's web server port. Fill in username/password only if you set
   them in Kodi.
4. Tap **1. Grant overlay permission** → toggle on "Allow display over other
   apps" for SubFly Captions in the system settings screen that opens, then
   go back.
5. Tap **2. Start live captions**. Android will show a system dialog asking
   to start capturing screen/audio — accept it. This grant lasts until you
   stop the service; you won't be asked again until then.
6. Switch to Kodi and start playing anything. Captions appear automatically
   once the server produces the first cue.

The service keeps running in the background (small persistent notification)
so it survives switching between Kodi and other apps. Tap **Stop** in the
app, or the notification's Stop action, to end it.

## Why this needs a whole app instead of a Kodi addon

Kodi addons on Android run inside Kodi's embedded CPython, with no access to
`subprocess`, no shell, no system audio devices, and (depending on build) no
JNI bridge to Android APIs from Python. The desktop approach used by
`clients/kodi` (spawn `ffmpeg` against a PulseAudio/ALSA loopback device)
has literally nothing to attach to on Android. `AudioPlaybackCaptureConfiguration`
is Android's actual supported mechanism for "capture what the device is
playing," and it's only reachable from a native app holding a `MediaProjection`
token, which is why this exists as its own APK.

## If your device is too old (pre-Android 10)

There's no software capture path available. The only option is a hardware
one: an HDMI audio extractor between the stick and your TV/projector, feeding
a USB audio capture dongle plugged into a small always-on Linux box (even a
Raspberry Pi) near the TV, running `ffmpeg -f alsa -i hw:...` and streaming
to the same `/v1/live` endpoint this app uses — same protocol, just a
different capture source. That's a hardware project, not something this repo
automates, but the server side needs zero changes to support it.

## Troubleshooting

**Captions never appear / server logs show empty transcriptions**
Kodi's manifest may have playback-capture disabled for its media session, or
Android decided a specific stream is protected and blocked capture (common
for actual DRM-protected sources at the OS level, not just app-level DRM).
Check `adb logcat | grep SubFly` for `AudioRecord` creation errors.

**Overlay never shows even though logs show cues being received**
Re-check "Allow display over other apps" is enabled — Android silently
revokes this if the app is unused for a while on some OEM skins.

**Service dies when Kodi is minimized**
Check battery optimization / background-restriction settings for SubFly
Captions and set it to unrestricted; aggressive per-OEM task killers on some
Android TV boxes will otherwise kill the foreground service.

**MediaProjection dialog doesn't appear / times out**
Some launchers on Android TV render system dialogs behind the current app.
Try pressing the home/back button briefly after tapping "Start live
captions," or check for an on-screen dialog in the notification shade.
