"""Runs the CalibrationController in a CalibrationThread with the Qt patch bridge (offscreen)."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from kelvincal.ddc.contrast_optimizer import ContrastOptimizationConfig
from kelvincal.gui.controller import CalibrationController, CancelToken
from kelvincal.gui.workers import CalibrationThread, QtCalibrationObserver, QtPatchDisplay
from test_controller import FakeCompositor, FakeDDC, FakePanel, FakeSensor, _display


class TestCalibrationThread(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _run(self, press: str) -> tuple[dict, QtPatchDisplay, list[int]]:  # noqa: ANN001
        display = _display()
        display.connector = self.app.screens()[0].name()
        panel = FakePanel()
        cancel = CancelToken()
        patch = QtPatchDisplay(display.connector, cancel)
        observer = QtCalibrationObserver()
        steps: list[int] = []
        observer.contrast_step_measured.connect(lambda s: steps.append(s.contrast))
        controller = CalibrationController(
            display, FakeCompositor(), patch, observer, cancel, FakeDDC(panel),  # type: ignore[arg-type]
            sensor_factory=lambda _c: FakeSensor(panel),  # type: ignore[return-value]
        )
        thread = CalibrationThread(controller, lambda c: c.run_contrast(ContrastOptimizationConfig()))
        out: dict = {}
        thread.succeeded.connect(lambda r: out.setdefault("result", r.optimal_contrast))
        thread.failed.connect(lambda m: out.setdefault("error", m))
        thread.cancelled.connect(lambda: out.setdefault("cancelled", True))
        thread.finished.connect(self.app.quit)
        signal = patch.window.confirmed if press == "space" else patch.window.aborted
        QTimer.singleShot(100, signal.emit)
        QTimer.singleShot(15000, self.app.quit)  # safety net against dead-locks
        thread.start()
        self.app.exec()
        thread.wait(2000)
        return out, patch, steps

    def test_confirmed_run_measures_through_bridge(self) -> None:
        out, patch, steps = self._run("space")
        self.assertIn(out.get("result"), (71, 72))
        self.assertGreater(len(steps), 4)
        self.assertEqual(patch.window.current_rgb, (255, 255, 255))
        self.assertFalse(patch.window.isVisible())
        patch.dispose()

    def test_escape_at_placement_cancels(self) -> None:
        out, patch, steps = self._run("esc")
        self.assertTrue(out.get("cancelled"))
        self.assertEqual(steps, [])
        patch.dispose()


if __name__ == "__main__":
    unittest.main()
