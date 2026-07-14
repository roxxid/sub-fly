#!/usr/bin/env python3
"""Package the Kodi addon as a zip installable from zip file."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "kodi-addon" / "service.subfly"
OUT_DIR = ROOT / "dist"
ZIP_PATH = OUT_DIR / "service.subfly-1.0.0.zip"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in SRC.rglob("*"):
            if path.is_file():
                if path.name.startswith(".") or path.suffix == ".pyc":
                    continue
                arc = Path("service.subfly") / path.relative_to(SRC)
                zf.write(path, arcname=str(arc))

    print(f"Wrote {ZIP_PATH}")


if __name__ == "__main__":
    main()
