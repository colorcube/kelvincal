"""Graphical interface `kcal-gui` (Qt 6 / PySide6) for KelvinCal under Wayland."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kcal_gui.dbus_service import DBusService, call_running
from kcal_gui.i18n_setup import install_translators
from kcal_gui.main_window import KelvinCalMainWindow
from kcal_gui.theme import ThemeManager

APP_ID = "de.colorcube.kelvincal"
# used when the icon is not installed into the icon theme (running from the source tree)
ICON_FILE = Path(__file__).resolve().parents[2] / "share/icons/hicolor/scalable/apps" / f"{APP_ID}.svg"

__all__ = ["APP_ID", "KelvinCalMainWindow", "main"]


def migrate_settings() -> None:
    """Moves the settings file of versions before the app ID change (organisation "kde.org")."""
    new = Path(QSettings().fileName())
    old = new.parent.parent / "kde.org" / new.name
    if old.is_file() and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        old.replace(new)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="kcal-gui", description="KelvinCal display calibration (GUI)")
    parser.add_argument("--display", metavar="CONNECTOR", default="",
                        help="Select this display (e.g. DP-2); passed on to an already running KelvinCal")
    args, _qt_args = parser.parse_known_args(argv[1:])   # leave Qt's own options (-platform …) alone
    return args


def main() -> int:
    args = parse_args(sys.argv)
    app = QApplication(sys.argv)
    app.setApplicationName("kelvincal")
    app.setApplicationDisplayName("KelvinCal")
    app.setOrganizationName("kelvincal")  # settings: ~/.config/kelvincal/kelvincal.conf, next to presets.json
    app.setOrganizationDomain("colorcube.de")
    app.setDesktopFileName(APP_ID)
    # single instance: a second start only brings the running window to the front
    token = os.environ.pop("XDG_ACTIVATION_TOKEN", "")
    reached, _ = call_running("ShowDisplay", args.display, token) if args.display else call_running("Activate", token)
    if reached:
        return 0
    if token:
        os.environ["XDG_ACTIVATION_TOKEN"] = token   # for our own first window
    migrate_settings()
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(str(ICON_FILE))))
    app._translators = install_translators(app)  # type: ignore[attr-defined]
    theme = ThemeManager(app)
    theme.restore()
    win = KelvinCalMainWindow(theme)
    win.show()
    service = DBusService(win)
    if args.display:
        win.bring_to_front(args.display)
    code = app.exec()
    service.unregister()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
