"""Thin translation wrapper around Qt's translation system (source language: English).

User-visible strings are written as `translate("Context", "English text")`, so `lupdate` can extract
them into `kcal_gui/i18n/kelvincal_<lang>.ts`. The translators themselves are installed by
`kcal_gui.i18n_setup.install_translators()`. Without PySide6 or without a QCoreApplication the
English source text is returned unchanged, so the backend stays usable without Qt.
"""

from __future__ import annotations

try:
    from PySide6.QtCore import QCoreApplication
except ImportError:  # pragma: no cover - PySide6 is a hard dependency of the GUI only
    QCoreApplication = None  # type: ignore[assignment,misc]


def translate(context: str, text: str, disambiguation: str | None = None, n: int = -1) -> str:
    """Returns the translation of `text` in `context`, or `text` itself if none is installed."""
    if QCoreApplication is None:
        return text
    return QCoreApplication.translate(context, text, disambiguation, n)


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:  # noqa: N802 - name recognised by lupdate
    """Marks `text` for extraction without translating it (translate it later at display time)."""
    return text
