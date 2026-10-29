"""Graphical interface `kcal-gui` (Qt 6 / PySide6) for KelvinCal under Wayland."""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kcal_gui.i18n_setup import install_translators
from kcal_gui.main_window import KelvinCalMainWindow
from kcal_gui.theme import ThemeManager

APP_ID = "de.colorcube.kelvincal"

__all__ = ["APP_ID", "KelvinCalMainWindow", "main"]


def migrate_settings() -> None:
    """Moves the settings file of versions before the app ID change (organisation "kde.org")."""
    new = Path(QSettings().fileName())
    old = new.parent.parent / "kde.org" / new.name
    if old.is_file() and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        old.replace(new)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("kelvincal")
    app.setApplicationDisplayName("KelvinCal")
    app.setOrganizationName("kelvincal")  # settings: ~/.config/kelvincal/kelvincal.conf, next to presets.json
    app.setOrganizationDomain("colorcube.de")
    app.setDesktopFileName(APP_ID)
    migrate_settings()
    app.setWindowIcon(QIcon.fromTheme("preferences-desktop-display-color"))
    app._translators = install_translators(app)  # type: ignore[attr-defined]
    theme = ThemeManager(app)
    theme.restore()
    win = KelvinCalMainWindow(theme)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
