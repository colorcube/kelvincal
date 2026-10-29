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
        if translator.load(locale, name, "_", directory):
            app.installTranslator(translator)
            installed.append(translator)
    return installed
