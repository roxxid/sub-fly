#!/usr/bin/env python3
"""Package the Kodi addon as an installable zip."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "clients" / "kodi" / "service.subfly"
OUT_DIR = ROOT / "dist"
ZIP_PATH = OUT_DIR / "service.subfly-1.0.0.zip"


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"addon source missing: {SRC}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in SRC.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith(".") or path.suffix == ".pyc" or "__pycache__" in path.parts:
                continue
            arc = Path("service.subfly") / path.relative_to(SRC)
            zf.write(path, arcname=str(arc))

    print(f"Wrote {ZIP_PATH}")


if __name__ == "__main__":
    main()
