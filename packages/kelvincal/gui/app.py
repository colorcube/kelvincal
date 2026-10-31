"""Graphical interface `kelvincal` (Qt 6 / PySide6) for KelvinCal under Wayland."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import socket
import sys
from typing import Callable

from PySide6.QtCore import QSettings, QSocketNotifier
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kelvincal.argyll import processes
from kelvincal.core import recovery
from kelvincal.gui.dbus_service import DBusService, call_running
from kelvincal.gui.i18n_setup import install_translators
from kelvincal.gui.main_window import KelvinCalMainWindow
from kelvincal.gui.theme import ThemeManager

APP_ID = "de.colorcube.kelvincal"
# used when the icon is not installed into the icon theme (running from the source tree)
ICON_FILE = Path(__file__).resolve().parents[3] / "share/icons/hicolor/scalable/apps" / f"{APP_ID}.svg"

__all__ = ["APP_ID", "KelvinCalMainWindow", "main"]


def migrate_settings() -> None:
    """Moves the settings file of versions before the app ID change (organisation "kde.org")."""
    new = Path(QSettings().fileName())
    old = new.parent.parent / "kde.org" / new.name
    if old.is_file() and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        old.replace(new)


QUIT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def install_quit_signals(on_quit: Callable[[], None]) -> QSocketNotifier:
    """Ctrl+C, SIGTERM (e.g. logout) and SIGHUP (terminal closed) end KelvinCal like closing the window:
    a running measurement is cancelled and the display restored first. A second signal ends it at once.

    Python signal handlers only run while the interpreter does, not inside Qt's event loop; the wake-up
    socket lets the event loop notice the signal immediately.
    """
    read_sock, write_sock = socket.socketpair()
    read_sock.setblocking(False)
    write_sock.setblocking(False)
    signal.set_wakeup_fd(write_sock.fileno())
    for sig in QUIT_SIGNALS:
        signal.signal(sig, lambda *_: None)
    notifier = QSocketNotifier(read_sock.fileno(), QSocketNotifier.Type.Read)
    received = 0

    def activated() -> None:
        nonlocal received
        try:
            data = read_sock.recv(64)
        except BlockingIOError:
            return
        if not data:
            return
        received += 1
        if received == 1:
            on_quit()
            return
        print("KelvinCal: quitting immediately; the display may keep the measurement state.", file=sys.stderr)
        processes.terminate_all(timeout_s=1.0)
        os._exit(128 + data[-1])

    notifier.activated.connect(activated)
    notifier.sockets = (read_sock, write_sock)  # type: ignore[attr-defined] - keep them open
    return notifier


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="kelvincal", description="KelvinCal display calibration (GUI)")
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
    recovery.enable()
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(str(ICON_FILE))))
    app._translators = install_translators(app)  # type: ignore[attr-defined]
    theme = ThemeManager(app)
    theme.restore()
    win = KelvinCalMainWindow(theme)
    win.show()
    service = DBusService(win)
    quit_notifier = install_quit_signals(win.quit_now)  # noqa: F841 - must stay alive
    # logout during a measurement: cancel it and restore the display before the session ends
    app.commitDataRequest.connect(lambda _manager: win.quit_now() if win.is_measuring() else None)
    if args.display:
        win.bring_to_front(args.display)
    code = app.exec()
    service.unregister()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
