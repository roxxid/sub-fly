# -*- coding: utf-8 -*-
"""Unit tests for the pure vocabulary-hint builder (no xbmc/Kodi needed)."""

import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "service.subfly" / "resources" / "lib"
sys.path.insert(0, str(LIB))

from hints import MAX_HINT_CHARS, build_vocabulary_hint  # noqa: E402


def test_combines_title_cast_genre_plot():
    hint = build_vocabulary_hint(
        title="The Wrath of Khan",
        tvshowtitle="",
        cast=["Spock", "Uhura", "Khan Noonien Singh"],
        genres=["Science Fiction", "Adventure"],
        plot="Khan escapes exile and seeks revenge on Admiral Kirk.",
    )
    assert "The Wrath of Khan" in hint
    assert "Spock" in hint
    assert "Khan Noonien Singh" in hint
    assert "Science Fiction" in hint
    assert "revenge on Admiral Kirk" in hint


def test_tvshowtitle_precedes_episode_title():
    hint = build_vocabulary_hint(title="The Long Night", tvshowtitle="Game of Thrones")
    assert hint.startswith("Game of Thrones")
    assert "The Long Night" in hint


def test_empty_metadata_gives_empty_hint():
    assert build_vocabulary_hint() == ""


def test_cast_list_is_capped():
    cast = [f"Actor {i}" for i in range(20)]
    hint = build_vocabulary_hint(title="X", cast=cast)
    assert "Actor 7" in hint
    assert "Actor 8" not in hint


def test_plot_is_truncated():
    long_plot = "word " * 200
    hint = build_vocabulary_hint(title="X", plot=long_plot)
    assert len(hint) <= MAX_HINT_CHARS


def test_overall_hint_is_capped():
    hint = build_vocabulary_hint(
        title="A very long movie title " * 10,
        cast=[f"Character Name {i}" for i in range(8)],
        plot="word " * 200,
    )
    assert len(hint) <= MAX_HINT_CHARS


def test_ignores_blank_and_falsy_fields():
    hint = build_vocabulary_hint(title="", tvshowtitle="", cast=[], genres=[], plot="")
    assert hint == ""
