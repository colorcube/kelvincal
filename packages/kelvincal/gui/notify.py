"""Desktop notifications: KNotification (events configurable in the system settings) if the KF6 bindings
and `kelvincal.notifyrc` are installed, else the freedesktop notification service, else nothing.

Events (see share/knotifications6/kelvincal.notifyrc): calibrationFinished, calibrationFailed,
verificationFinished, presetFailed.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QStandardPaths

try:
    from KNotifications import KNotification
except ImportError:  # optional: python3-kf6-knotifications
    KNotification = None  # type: ignore[assignment,misc]

COMPONENT = "kelvincal"
ICON = "de.colorcube.kelvincal"
_active: set = set()   # keeps KNotification objects alive until they are closed


def _notifyrc_installed() -> bool:
    return bool(QStandardPaths.locate(QStandardPaths.StandardLocation.GenericDataLocation,
                                      f"knotifications6/{COMPONENT}.notifyrc"))


def backend() -> str:
    """"knotification", "freedesktop" or "" (no notifications)."""
    if KNotification is not None and _notifyrc_installed():
        return "knotification"
    from PySide6.QtDBus import QDBusConnection

    bus = QDBusConnection.sessionBus()
    if bus.isConnected() and bus.interface().isServiceRegistered("org.freedesktop.Notifications").value():
        return "freedesktop"
    return ""


def notify(event: str, title: str, text: str, on_click: Callable[[], None] | None = None,
           error: bool = False) -> None:
    """Shows a notification; `on_click` is the default action (e.g. raise the window)."""
    kind = backend()
    if kind == "knotification":
        n = KNotification(event)
        n.setComponentName(COMPONENT)
        n.setTitle(title)
        n.setText(text)
        n.setIconName(ICON)
        if on_click is not None:
            action = n.addDefaultAction(title)
            action.activated.connect(on_click)
        _active.add(n)
        n.closed.connect(lambda: _active.discard(n))
        n.sendEvent()
    elif kind == "freedesktop":
        from PySide6.QtDBus import QDBusInterface

        iface = QDBusInterface("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                               "org.freedesktop.Notifications")
        hints = {"desktop-entry": ICON, "urgency": 2 if error else 1}
        iface.call("Notify", "KelvinCal", 0, ICON, title, text, [], hints, -1)

