"""Desktop arrangement of the outputs as the compositor reports it (QScreen = Wayland output)."""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication


def screen_geometries() -> dict[str, QRect]:
    """Logical desktop geometry per connector name (e.g. "DP-1"); empty if the platform has none.

    Under KWin/Wayland `QScreen.name()` is the connector name and `geometry()` the position and
    (scaled) size in the desktop layout, i.e. the arrangement of the KDE display settings.
    """
    app = QGuiApplication.instance()
    if app is None:
        return {}
    return {s.name(): QRect(s.geometry()) for s in QGuiApplication.screens() if s.name()}
