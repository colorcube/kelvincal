"""Session D-Bus interface `de.colorcube.kelvincal` of the running GUI (single instance, plasmoid, CLI).

Methods on object `/`:
- `Activate(token)` – raise the window
- `ShowDisplay(connector, token)` – raise the window with that display selected on the "Displays" page
- `ApplyPreset(name) -> str` – apply a preset; "" on success, else the reason (e.g. a measurement runs)
- `Status() -> str` – JSON: active preset, whether a measurement is running

`token` is the caller's XDG activation token (Wayland focus stealing prevention), "" if it has none.

Without a session bus (or if the name is taken) the GUI runs as before, only without these extras.
"""

from __future__ import annotations

import json
from typing import Protocol

from PySide6.QtCore import ClassInfo, QObject, Slot
from PySide6.QtDBus import QDBusAbstractAdaptor, QDBusConnection, QDBusInterface, QDBusMessage

SERVICE = "de.colorcube.kelvincal"
PATH = "/"
INTERFACE = "de.colorcube.kelvincal"
TIMEOUT_MS = 3000


class Target(Protocol):
    """What the main window provides to the D-Bus interface."""

    def bring_to_front(self, connector: str = "", token: str = "") -> None: ...
    def apply_preset_request(self, name: str) -> str: ...
    def status_dict(self) -> dict: ...


@ClassInfo({"D-Bus Interface": INTERFACE})
class KelvinCalAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent: QObject, target: Target) -> None:
        super().__init__(parent)
        self.target = target

    @Slot(str)
    def Activate(self, token: str) -> None:  # noqa: N802 - D-Bus method name
        self.target.bring_to_front("", token)

    @Slot(str, str)
    def ShowDisplay(self, connector: str, token: str) -> None:  # noqa: N802
        self.target.bring_to_front(connector, token)

    @Slot(str, result=str)
    def ApplyPreset(self, name: str) -> str:  # noqa: N802
        return self.target.apply_preset_request(name)

    @Slot(result=str)
    def Status(self) -> str:  # noqa: N802
        return json.dumps(self.target.status_dict(), ensure_ascii=False)


class DBusService:
    """Owns the exported object; `registered` is False if another instance already has the name."""

    def __init__(self, target: Target, service: str = SERVICE) -> None:
        self.service = service
        self.holder = QObject()
        self.adaptor = KelvinCalAdaptor(self.holder, target)
        bus = QDBusConnection.sessionBus()
        self.registered = bus.isConnected() and bus.registerService(service)
        if self.registered:
            bus.registerObject(PATH, self.holder)

    def unregister(self) -> None:
        if self.registered:
            bus = QDBusConnection.sessionBus()
            bus.unregisterObject(PATH)
            bus.unregisterService(self.service)
            self.registered = False


def _interface(service: str) -> QDBusInterface | None:
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected() or not bus.interface().isServiceRegistered(service).value():
        return None
    iface = QDBusInterface(service, PATH, INTERFACE, bus)
    iface.setTimeout(TIMEOUT_MS)
    return iface if iface.isValid() else None


def call_running(method: str, *args: str, service: str = SERVICE) -> tuple[bool, str]:
    """Calls `method` on a running KelvinCal GUI. Returns (reached, string result or error message)."""
    iface = _interface(service)
    if iface is None:
        return False, ""
    reply = iface.call(method, *args)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return False, reply.errorMessage()
    values = reply.arguments()
    return True, str(values[0]) if values and values[0] is not None else ""
