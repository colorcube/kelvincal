"""Locale-aware number formatting for the GUI (decimal comma in German, etc.)."""

from __future__ import annotations

from PySide6.QtCore import QLocale


def num(value: float | int | None, decimals: int = 0, unit: str = "") -> str:
    """Formats `value` with the default locale; `None` becomes an en dash. `unit` is appended with a space."""
    if value is None:
        return "–"
    text = QLocale().toString(float(value), "f", decimals) if decimals else QLocale().toString(round(value))
    return f"{text} {unit}" if unit else text


def pct(value: float | int | None, decimals: int = 0) -> str:
    return num(value, decimals, "%")


def cdm2(value: float | None, decimals: int = 1) -> str:
    return num(value, decimals, "cd/m²")
