"""Graphical interface `kcal-gui` (Qt 6 / PySide6) for KelvinCal under Wayland."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kcal_gui.i18n_setup import install_translators
from kcal_gui.main_window import KelvinCalMainWindow
from kcal_gui.theme import ThemeManager

APP_ID = "org.kde.kelvincal"

__all__ = ["APP_ID", "KelvinCalMainWindow", "main"]


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("kelvincal")
    app.setApplicationDisplayName("KelvinCal")
    app.setOrganizationDomain("kde.org")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme("preferences-desktop-display-color"))
    app._translators = install_translators(app)  # type: ignore[attr-defined]
    theme = ThemeManager(app)
    theme.restore()
    win = KelvinCalMainWindow(theme)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
