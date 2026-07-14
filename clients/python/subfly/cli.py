#!/usr/bin/env python3
"""CLI for exercising a SubFly server without Kodi.

Examples:
  python -m subfly.cli health --url http://192.168.1.50:8765
  python -m subfly.cli transcribe --url http://192.168.1.50:8765 \\
      --media /media/Movies/film.mkv --start 0
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .client import SubFlyClient, SubtitleCue


def cmd_health(args: argparse.Namespace) -> int:
    client = SubFlyClient(args.url, token=args.token or "")
    print(json.dumps(client.health(), indent=2))
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    client = SubFlyClient(args.url, token=args.token or "")
    print(json.dumps(client.info(), indent=2))
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    client = SubFlyClient(args.url, token=args.token or "")
    session = client.start_session(
        args.media,
        start_seconds=args.start,
        language=args.language,
    )
    print(f"session {session['session_id']}", file=sys.stderr)
    print(f"resolved {session.get('resolved_path')}", file=sys.stderr)

    done = {"ok": False}

    def on_message(data):
        if not isinstance(data, dict):
            return
        typ = data.get("type")
        if typ == "subtitle":
            cue = SubtitleCue.from_message(data)
            print(f"[{cue.start:8.2f} -> {cue.end:8.2f}] {cue.text}", flush=True)
        elif typ in {"pipeline_done", "session_stopped"}:
            done["ok"] = True
        elif typ == "error":
            print(f"ERROR: {data.get('message')}", file=sys.stderr)
            done["ok"] = True

    client.connect_session_ws(session["session_id"], on_message=on_message)
    try:
        # Feed a playback clock so the server does not race too far ahead
        pos = float(args.start)
        while not done["ok"]:
            client.send_position(pos)
            time.sleep(1.0)
            pos += 1.0
            if args.duration > 0 and (pos - args.start) >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        client.close_ws()
        client.stop_session()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="subfly", description="SubFly client CLI")
    parser.add_argument("--url", default="http://127.0.0.1:8765", help="SubFly server URL")
    parser.add_argument("--token", default="", help="Optional API token")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_health = sub.add_parser("health", help="GET /healthz")
    p_health.set_defaults(func=cmd_health)

    p_info = sub.add_parser("info", help="GET /v1/info")
    p_info.set_defaults(func=cmd_info)

    p_tr = sub.add_parser("transcribe", help="Transcribe a media path on the server")
    p_tr.add_argument("--media", required=True, help="Media path as the server should see it (or Kodi path if mapped)")
    p_tr.add_argument("--start", type=float, default=0.0)
    p_tr.add_argument("--duration", type=float, default=0.0, help="Stop after N seconds of simulated playback (0=until done)")
    p_tr.add_argument("--language", default="en")
    p_tr.set_defaults(func=cmd_transcribe)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
