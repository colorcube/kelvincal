"""D-Bus interface of the GUI: forwarding from a second start, plasmoid and CLI (needs a session bus)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtDBus import QDBusConnection  # noqa: E402

from kelvincal.gui.dbus_service import DBusService, call_running  # noqa: E402

TEST_SERVICE = f"de.colorcube.kelvincal.test{os.getpid()}"


class FakeWindow:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.busy = False

    def bring_to_front(self, connector: str = "", token: str = "") -> None:
        self.calls.append(("front", connector, token))

    def apply_preset_request(self, name: str) -> str:
        self.calls.append(("apply", name))
        return "busy" if self.busy else ""

    def status_dict(self) -> dict:
        return {"active_preset": "Büro", "busy": self.busy}


@unittest.skipUnless(QDBusConnection.sessionBus().isConnected(), "no session bus")
class DBusServiceTest(unittest.TestCase):
    def test_methods_reach_the_window(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        win = FakeWindow()
        service = DBusService(win, TEST_SERVICE)
        self.assertTrue(service.registered)
        # The client is a separate process (own bus connection), like the plasmoid or kelvincal-cli.
        script = (
            "import json, sys\n"
            "from PySide6.QtCore import QCoreApplication\n"
            "from kelvincal.gui.dbus_service import call_running\n"
            "app = QCoreApplication([])\n"
            f"s = {TEST_SERVICE!r}\n"
            "print(json.dumps([call_running('ShowDisplay', 'DP-2', 'tok', service=s),\n"
            "                  call_running('ApplyPreset', 'Foto', service=s),\n"
            "                  call_running('Status', service=s)]))\n")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
        proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, env=env, text=True)
        deadline = time.monotonic() + 20
        while proc.poll() is None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        out = proc.communicate(timeout=5)[0]
        show, apply, status = (tuple(r) for r in json.loads(out))
        service.unregister()
        self.assertEqual(show, (True, ""))
        self.assertEqual(apply, (True, ""))
        self.assertEqual(status, (True, '{"active_preset": "Büro", "busy": false}'))
        self.assertEqual(win.calls, [("front", "DP-2", "tok"), ("apply", "Foto")])
        self.assertEqual(call_running("Status", service=TEST_SERVICE), (False, ""))   # gone after unregister


if __name__ == "__main__":
    unittest.main()
