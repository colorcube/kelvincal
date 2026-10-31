"""Keeps the screen awake while measuring: no dimming, screen locker, DPMS off or suspend.

A measurement can take an hour or more without any user input. If the desktop dims the screen, locks
it or switches it off, the sensor measures the wrong thing (or nothing). For the duration of a run we
therefore register inhibitions on the session bus:
- `org.freedesktop.ScreenSaver.Inhibit`: screen locker, dimming and DPMS (KWin/PowerDevil under Plasma)
- `org.freedesktop.PowerManagement.Inhibit.Inhibit`: suspend

Both services drop an inhibition as soon as the D-Bus connection that requested it disappears. Each
inhibitor uses its own private connection and releases by closing it; this also covers crashes, and
avoids `UnInhibit(uint32 cookie)`, which PySide's QtDBus cannot call with the right argument type.
Without a session bus (or the services) inhibiting silently does nothing.
"""

from __future__ import annotations

import itertools

from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

APP_NAME = "KelvinCal"
SERVICES = (
    ("org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver"),
    ("org.freedesktop.PowerManagement.Inhibit", "/org/freedesktop/PowerManagement/Inhibit",
     "org.freedesktop.PowerManagement.Inhibit"),
)
_ids = itertools.count(1)


class SleepInhibitor:
    """`acquire()` once at the start of a run, `release()` at its end (idempotent; also a context manager)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self._name = ""
        self.active: list[str] = []   # services that accepted the inhibition

    def acquire(self) -> bool:
        if self._name:
            return bool(self.active)
        self._name = f"kelvincal-inhibit-{next(_ids)}"
        bus = QDBusConnection.connectToBus(QDBusConnection.BusType.SessionBus, self._name)
        if not bus.isConnected():
            return False
        for service, path, interface in SERVICES:
            reply = QDBusInterface(service, path, interface, bus).call("Inhibit", APP_NAME, self.reason)
            if reply.type() == QDBusMessage.MessageType.ReplyMessage:
                self.active.append(service)
        return bool(self.active)

    def release(self) -> None:
        if self._name:
            QDBusConnection.disconnectFromBus(self._name)
        self._name = ""
        self.active = []

    def __enter__(self) -> SleepInhibitor:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
