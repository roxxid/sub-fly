# -*- coding: utf-8 -*-
"""Pure helpers for building a Whisper vocabulary hint from Kodi metadata.

Kept free of any `xbmc*` imports so it can be unit tested without a running
Kodi instance or any stub modules — `monitor.py` does the Kodi-specific
extraction (reading InfoTagVideo fields) and hands plain values to
`build_vocabulary_hint()` here.
"""

from __future__ import annotations

MAX_HINT_CHARS = 480
MAX_CAST_NAMES = 8
MAX_PLOT_CHARS = 200


def build_vocabulary_hint(
    *,
    title: str = "",
    tvshowtitle: str = "",
    cast: list | None = None,
    genres: list | None = None,
    plot: str = "",
) -> str:
    """Build a short "what's playing" hint to bias Whisper's vocabulary.

    This is sent to the server as `vocabulary_hint`, which the server maps
    to faster-whisper's `hotwords` parameter: it nudges the decoder toward
    the specific character/place names and terminology of whatever's
    actually playing, instead of relying purely on general vocabulary
    statistics baked into Whisper's training data. It doesn't guarantee
    correct spelling of obscure names, but it measurably helps for anything
    Kodi has scraped metadata for.
    """
    bits: list[str] = []

    def add(value) -> None:
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v).strip() for v in value if str(v).strip())
        text = str(value).strip() if value else ""
        if text:
            bits.append(text)

    add(tvshowtitle)
    add(title)
    if cast:
        names = [str(c).strip() for c in cast if str(c).strip()][:MAX_CAST_NAMES]
        if names:
            add(f"Characters/cast: {', '.join(names)}")
    if genres:
        add(genres)
    if plot:
        add(str(plot)[:MAX_PLOT_CHARS])

    hint = ". ".join(bits)
    return hint[:MAX_HINT_CHARS]
