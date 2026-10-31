"""Recovery after a crash: the ColorGuard records the state before a measurement, a killed run leaves it
behind, the next start offers to restore it."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kelvincal.core import recovery
from kelvincal.core.compositor.base import CompositorBackend, CompositorOutputState

PACKAGES = str(Path(__file__).resolve().parents[1] / "packages")


class FakeCompositor(CompositorBackend):
    def __init__(self) -> None:
        self.state = CompositorOutputState("DP-2", color_profile_source="ICC", icc_profile_path="/icc/old.icc")
        self.applied: list[tuple[str, str, str]] = []

    @property
    def name(self) -> str:
        return "fake"

    def get_outputs(self) -> dict[str, CompositorOutputState]:
        return {"DP-2": self.state}

    def apply_output_profile(self, connector: str, icc_profile_path: str = "", color_profile_source: str = "ICC",
                             brightness: float | None = None, disable_hdr_wcg: bool = False) -> None:
        self.applied.append((connector, icc_profile_path, color_profile_source))

    def apply_batch(self, updates: list[dict[str, object]]) -> None:
        pass


class FakeDDC:
    def __init__(self) -> None:
        self.written: list[tuple[int, dict]] = []

    def set_vcp_values(self, bus: int, values: dict) -> None:
        self.written.append((bus, values))


# a measurement that is killed while the display is in its raw state
CRASH = """
import os, signal, sys
sys.path.insert(0, sys.argv[1])
from kelvincal.core import recovery
from kelvincal.core.compositor.base import CompositorBackend, CompositorOutputState
class C(CompositorBackend):
    name = "fake"
    def get_outputs(self):
        return {"DP-2": CompositorOutputState("DP-2", color_profile_source="ICC", icc_profile_path="/icc/old.icc",
                                              hdr_enabled=True)}
    def apply_output_profile(self, *a, **k): pass
    def apply_batch(self, u): pass
recovery.enable()
with C().calibration_guard("DP-2", settle_seconds=0):
    recovery.note_ddc("DP-2", 7, (38, 72, 100, 96, 91))
    os.kill(os.getpid(), signal.SIGKILL)
"""


class RecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._state = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = self.tmp.name
        recovery.enable()

    def tearDown(self) -> None:
        recovery.enable(False)
        if self._state is None:
            os.environ.pop("XDG_STATE_HOME", None)
        else:
            os.environ["XDG_STATE_HOME"] = self._state
        self.tmp.cleanup()

    def _files(self) -> list[str]:
        folder = recovery.recovery_dir()
        return sorted(p.name for p in folder.glob("*")) if folder.is_dir() else []

    def test_clean_run_leaves_nothing(self) -> None:
        comp = FakeCompositor()
        with comp.calibration_guard("DP-2", settle_seconds=0):
            recovery.note_ddc("DP-2", 7, (38, 72, 100, 96, 91))
            self.assertEqual(self._files(), ["DP-2.json"])
            self.assertEqual(recovery.interrupted(), [])   # own process is still running
        self.assertEqual(self._files(), [])
        with self.assertRaises(RuntimeError):   # an error inside also restores and clears
            with comp.calibration_guard("DP-2", settle_seconds=0):
                raise RuntimeError
        self.assertEqual(self._files(), [])

    def test_kept_profile_is_cleared_after_the_review(self) -> None:
        with FakeCompositor().calibration_guard("DP-2", settle_seconds=0) as guard:
            guard.keep_new_profile = True
        self.assertEqual(self._files(), ["DP-2.json"])   # staged profile active until saved/discarded
        recovery.clear("DP-2")
        self.assertEqual(self._files(), [])

    def test_killed_run_is_restored(self) -> None:
        proc = subprocess.run([sys.executable, "-c", CRASH, PACKAGES], env=os.environ.copy())
        self.assertEqual(proc.returncode, -signal.SIGKILL)
        [entry] = recovery.interrupted()
        self.assertEqual((entry.connector, entry.icc_profile_path, entry.color_profile_source, entry.ddc,
                          entry.hdr_enabled), ("DP-2", "/icc/old.icc", "ICC", [38, 72, 100, 96, 91], True))
        # a new run before the restore keeps the record from before the interrupted one
        comp = FakeCompositor()
        comp.state = CompositorOutputState("DP-2", color_profile_source="sRGB")   # leftover of the crash
        with comp.calibration_guard("DP-2", settle_seconds=0):
            pass
        [entry] = recovery.interrupted()
        self.assertEqual(entry.icc_profile_path, "/icc/old.icc")
        ddc = FakeDDC()
        recovery.restore(entry, comp, ddc)
        self.assertEqual(comp.applied[-1], ("DP-2", "/icc/old.icc", "ICC"))
        self.assertEqual(ddc.written, [(7, {"10": 38, "12": 72, "16": 100, "18": 96, "1A": 91})])
        self.assertEqual(recovery.interrupted(), [])

    def test_recycled_pid_of_another_program_counts_as_interrupted(self) -> None:
        recovery._write(recovery.Interrupted("DP-1", pid=1, started="2026-10-31T10:12:00"))
        self.assertEqual([e.connector for e in recovery.interrupted()], ["DP-1"])

    def test_disabled_writes_and_offers_nothing(self) -> None:
        recovery._write(recovery.Interrupted("DP-1", pid=1))
        recovery.enable(False)
        with FakeCompositor().calibration_guard("DP-2", settle_seconds=0):
            pass
        self.assertEqual(self._files(), ["DP-1.json"])
        self.assertEqual(recovery.interrupted(), [])

    def test_main_window_offers_it(self) -> None:
        from PySide6.QtCore import QEventLoop, QSettings, QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox

        import kelvincal.gui.main_window as mw
        from kelvincal.argyll.instruments import InstrumentStatus

        _app = QApplication.instance() or QApplication([])
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, self.tmp.name)
        QSettings().setValue("setup/check_on_start", False)
        os.environ["KELVINCAL_PRESETS_PATH"] = os.path.join(self.tmp.name, "presets.json")
        recovery._write(recovery.Interrupted("DP-2", "/icc/old.icc", "ICC", pid=1, started="2026-10-31T10:12:00"))
        comp = FakeCompositor()
        with mock.patch.object(mw, "get_compositor_backend", lambda: comp), \
                mock.patch.object(mw, "discover_displays", lambda **_kw: []), \
                mock.patch.object(mw, "detect_instruments", lambda: InstrumentStatus()):
            try:
                win = mw.KelvinCalMainWindow()
                loop = QEventLoop()
                QTimer.singleShot(200, loop.quit)
                loop.exec()
                [box] = [w for w in win.findChildren(QMessageBox) if w.isVisible()]
                self.assertIn("DP-2", box.text())
                self.assertIn("old.icc", box.text())
                discard = next(b for b in box.buttons() if box.buttonRole(b) == QMessageBox.ButtonRole.DestructiveRole)
                discard.click()
                self.assertEqual(self._files(), [])
                self.assertEqual(comp.applied, [])   # discarded: nothing switched
                win.close()
            finally:
                del os.environ["KELVINCAL_PRESETS_PATH"]


if __name__ == "__main__":
    unittest.main()
