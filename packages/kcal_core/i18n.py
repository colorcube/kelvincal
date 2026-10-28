"""Lightweight localization helper (English default with automatic German UI support)."""

from __future__ import annotations

import os


def is_german_locale() -> bool:
    """Returns True if the active language environment prefers German ('de')."""
    override = os.environ.get("KELVINCAL_LANG", "").strip().lower()
    if override:
        return override.startswith("de")
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "").strip().lower()
        if val:
            return val.startswith("de")
    return False


def tr(en_text: str, de_text: str | None = None) -> str:
    """Returns `de_text` when running under a German locale, otherwise `en_text`."""
    if de_text and is_german_locale():
        return de_text
    return en_text
