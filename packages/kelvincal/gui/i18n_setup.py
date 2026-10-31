"""Installs the Qt translators for KelvinCal and Qt's own standard dialogs."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

TRANSLATIONS_DIR = Path(__file__).resolve().parent / "i18n"


def ui_locale() -> QLocale:
    """Returns the UI locale: `KELVINCAL_LANG` (e.g. "de", "en") overrides the system locale."""
    override = os.environ.get("KELVINCAL_LANG", "").strip()
    return QLocale(override) if override else QLocale.system()


def install_translators(app: QCoreApplication) -> list[QTranslator]:
    """Loads `kelvincal_<lang>.qm` and `qtbase_<lang>.qm` for the UI locale into `app`.

    Returns the installed translators; keep a reference so they are not garbage-collected.
    """
    locale = ui_locale()
    QLocale.setDefault(locale)
    installed: list[QTranslator] = []
    sources = (
        ("qtbase", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)),
        ("kelvincal", str(TRANSLATIONS_DIR)),
    )
    for name, directory in sources:
        translator = QTranslator(app)
        if translator.load(locale, name, "_", directory) and _load_into_memory(translator):
            app.installTranslator(translator)
            installed.append(translator)
    return installed


def _load_into_memory(translator: QTranslator) -> bool:
    """Reloads the .qm file `translator` found from a private copy in memory.

    QTranslator maps the file into memory; if it is rewritten while KelvinCal runs (lrelease in a source
    checkout), the next translation reads a half-written file and crashes the process.
    """
    try:
        data = Path(translator.filePath()).read_bytes()
    except OSError:
        return True   # keep the mapped file
    translator._qm_data = data   # QTranslator does not copy the buffer: keep it alive with the translator
    return translator.load(data)
