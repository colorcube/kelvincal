"""Setup check: distribution-specific fixes, I²C and USB access, instrument, dialog and the check at start."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QLabel

from kelvincal.core import setup_check
from kelvincal.core.models import DDCState, DisplayInfo
from kelvincal.core.setup_check import ERROR, INFO, OK, WARNING, Check

ROOT = os.geteuid() == 0   # root may access everything: the "denied" cases cannot be built


def _display(connector: str, bus: int | None, ddc: bool = True) -> DisplayInfo:
    return DisplayInfo(connector=connector, drm_card_connector=f"card1-{connector}", edid_hash=connector,
                       model="EIZO", i2c_bus=bus, ddc=DDCState(38, 72, 100, 96, 91) if ddc else None)


class DistributionTest(unittest.TestCase):
    def _distro(self, text: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "os-release"
            path.write_text(text)
            return setup_check.distribution(path)

    def test_family_from_id_and_id_like(self) -> None:
        self.assertEqual(self._distro('NAME="Fedora Linux"\nID=fedora\nVERSION_ID=44\n'), "fedora")
        self.assertEqual(self._distro("ID=ubuntu\nID_LIKE=debian\n"), "debian")
        self.assertEqual(self._distro('ID=opensuse-tumbleweed\nID_LIKE="opensuse suse"\n'), "suse")
        self.assertEqual(self._distro("ID=nixos\n"), "")

    def test_package_names(self) -> None:
        self.assertEqual(setup_check.install_command("argyllcms", distro="fedora"), "sudo dnf install argyllcms")
        self.assertEqual(setup_check.install_command("argyllcms", "ddcutil", distro="debian"),
                         "sudo apt install argyll ddcutil")
        self.assertIn("argyllcms", setup_check.install_command("argyllcms", distro=""))


class ChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = Path(self.tmp.name)
        for bus in (5, 7):
            (self.dev / f"i2c-{bus}").write_text("")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_argyll_missing(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            check = setup_check.check_argyll("", distro="debian")
        self.assertEqual((check.status, check.fix), (ERROR, "sudo apt install argyll"))

    def test_i2c_ok_and_display_without_ddc(self) -> None:
        checks = setup_check.check_i2c([_display("DP-1", 5), _display("DP-2", 7, ddc=False)], self.dev)
        self.assertEqual([(c.key, c.status) for c in checks], [("ddc:DP-2", WARNING)])
        self.assertIn("DDC/CI", checks[0].fix)
        checks = setup_check.check_i2c([_display("DP-1", 5)], self.dev)
        self.assertEqual([c.status for c in checks], [OK])

    @unittest.skipIf(ROOT, "root can access every device node")
    def test_i2c_without_access(self) -> None:
        (self.dev / "i2c-7").chmod(0)
        checks = setup_check.check_i2c([_display("DP-1", 5), _display("DP-2", 7)], self.dev)
        self.assertEqual(checks[0].status, ERROR)
        self.assertIn("DP-2", checks[0].title)
        self.assertNotIn("DP-1", checks[0].title)
        self.assertTrue(checks[0].fix)

    def test_no_i2c_bus_at_all(self) -> None:
        checks = setup_check.check_i2c([_display("eDP-1", None)], self.dev)
        self.assertEqual(checks[0].status, WARNING)
        self.assertIn("i2c-dev", checks[0].fix)

    def test_usb_instruments_from_sysfs(self) -> None:
        usb = self.dev / "usb"
        for name, vendor, product in (("3-2", "0765", "ColorMunki Display"), ("3-3", "046d", "Keyboard")):
            d = usb / name
            d.mkdir(parents=True)
            for key, value in (("idVendor", vendor), ("busnum", "3"), ("devnum", "117"), ("product", product)):
                (d / key).write_text(value + "\n")
        self.assertEqual(setup_check.usb_instruments(usb), [("ColorMunki Display", Path("/dev/bus/usb/003/117"))])

    def test_instrument(self) -> None:
        self.assertEqual(setup_check.check_instrument(["X-Rite i1 DisplayPro"], []).status, OK)
        self.assertEqual(setup_check.check_instrument([], []).status, INFO)
        node = self.dev / "i2c-5"   # any accessible file as device node
        self.assertEqual(setup_check.check_instrument([], [("i1 Pro", node)]).status, WARNING)

    @unittest.skipIf(ROOT, "root can access every device node")
    def test_instrument_without_access(self) -> None:
        node = self.dev / "i2c-5"
        node.chmod(0)
        check = setup_check.check_instrument([], [("ColorMunki Display", node)], distro="fedora")
        self.assertEqual((check.status, check.fix), (ERROR, "sudo dnf install colord"))

    def test_other_compositor(self) -> None:
        self.assertEqual(setup_check.check_compositor("mutter").status, WARNING)


def _spin(ms: int = 100) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


PROBLEMS = [
    Check("argyll", OK, "ArgyllCMS 3.4.1"),
    Check("i2c", ERROR, "No access to the I²C bus of DP-1", "Needs access.", "sudo usermod -aG i2c $USER"),
    Check("ddc:DP-2", WARNING, "DP-2 does not answer over DDC/CI", "", "Turn on DDC/CI in the menu."),
]


class DialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_commands_copyable_instructions_as_text(self) -> None:
        from kelvincal.gui.setup_dialog import SetupCheckDialog

        dlg = SetupCheckDialog(PROBLEMS)
        body = dlg.area.widget()
        commands = [e.text() for e in body.findChildren(QLabel, "command")]
        self.assertEqual(commands, ["sudo usermod -aG i2c $USER"])
        self.assertIn("Turn on DDC/CI in the menu.", [label.text() for label in body.findChildren(QLabel)])
        self.assertFalse(dlg.btn_again.isEnabled())   # no way to re-run given

    def test_shown_at_start_only_on_errors(self) -> None:
        import kelvincal.gui.main_window as mw
        from kelvincal.argyll.instruments import InstrumentStatus

        os.environ["KELVINCAL_PRESETS_PATH"] = os.path.join(self.tmp.name, "presets.json")
        patches = [
            mock.patch.object(mw, "discover_displays", lambda **_kw: [_display("DP-1", 7)]),
            mock.patch.object(mw, "detect_instruments", lambda: InstrumentStatus("3.4.1", ["X-Rite i1 DisplayPro"])),
        ]
        for p in patches:
            p.start()
        try:
            for checks, on_start, shown in ((PROBLEMS, True, True), (PROBLEMS[:1], True, False),
                                            (PROBLEMS, False, False)):
                QSettings().setValue("setup/check_on_start", on_start)
                seen: list = []
                with mock.patch.object(mw, "run_checks", lambda *a, _c=checks: seen.append(a) or _c):
                    win = mw.KelvinCalMainWindow()
                    for _ in range(30):
                        _spin(50)
                        if win._setup_dialog is not None or (seen and not win._tasks):
                            break
                    self.assertEqual(win._setup_dialog is not None, shown)
                    if on_start:   # reuses what the window detected
                        self.assertEqual(seen[0][1:], ("3.4.1", ["X-Rite i1 DisplayPro"], win.compositor.name))
                    win.close()
        finally:
            for p in patches:
                p.stop()
            del os.environ["KELVINCAL_PRESETS_PATH"]


if __name__ == "__main__":
    unittest.main()
