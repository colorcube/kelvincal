"""Visual whitepoint matching: gain steps, offset, controller measurement and the dialog."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import kcal_gui.controller as controller_mod  # noqa: E402
from kcal_core.models import D65_X, D65_Y, ColorMeasurement, DDCState, DisplayInfo  # noqa: E402
from kcal_ddc.visual_match import COOLER, GREENER, MAGENTA, WARMER, nudge, white_offset  # noqa: E402
from kcal_gui.white_offset import (  # noqa: E402
    VisualWhiteDialog,
    set_white_offset,
    shifted_whitepoint,
    white_offset_for,
)
from test_controller import FakeCompositor, FakePanel, FakePatchDisplay, FakeSensor, _display  # noqa: E402
from test_controller import FakeDDC as PanelDDC  # noqa: E402


def _white(x: float, y: float) -> ColorMeasurement:
    return ColorMeasurement((255, 255, 255), x / y * 140, 140, (1 - x - y) / y * 140)


class NudgeTest(unittest.TestCase):
    def test_steps_keep_the_strongest_channel_at_max(self) -> None:
        self.assertEqual(nudge((100, 99, 90), WARMER), (100, 99, 89))       # red at max → less blue
        self.assertEqual(nudge((97, 92, 99), WARMER), (98, 92, 99))         # red can still go up
        self.assertEqual(nudge((100, 99, 90), COOLER), (100, 99, 91))
        self.assertEqual(nudge((96, 90, 100), COOLER), (95, 90, 100))       # blue at max → less red
        self.assertEqual(nudge((100, 95, 89), GREENER), (100, 96, 89))
        self.assertEqual(nudge((97, 100, 99), GREENER), (96, 100, 98))      # green at max → less red and blue
        self.assertEqual(nudge((100, 95, 89), MAGENTA), (100, 94, 89))
        self.assertEqual(nudge((100, 50, 89), MAGENTA), (100, 50, 89))      # never below min_gain

    def test_offset_accumulates(self) -> None:
        self.assertEqual(white_offset((0.3132, 0.3298), (0.3153, 0.3228)), (0.0021, -0.007))
        self.assertEqual(white_offset((0.3150, 0.3230), (0.3150, 0.3240), (0.0021, -0.007)), (0.0021, -0.006))


class ControllerTest(unittest.TestCase):
    def test_white_offset_measures_both_states_and_keeps_the_matched_one(self) -> None:
        panel = FakePanel()
        sensor = FakeSensor(panel)
        ctl = controller_mod.CalibrationController(
            display=_display(), compositor=FakeCompositor(), patch_display=FakePatchDisplay(),
            ddc_client=PanelDDC(panel), sensor_factory=lambda _ccss: sensor)  # type: ignore[arg-type]
        with mock.patch.object(controller_mod, "WHITE_SETTLE_S", 0.0):
            start, final = ctl.run_white_offset((100, 100, 100), (97, 100, 100))
        self.assertAlmostEqual(start.xy[0] - final.xy[0], 3 * 0.0004, places=4)
        self.assertEqual((panel.vcp["16"], panel.vcp["18"], panel.vcp["1A"]), (97, 100, 100))
        self.assertEqual(ctl.display.ddc.red_gain, 97)


class FakeDDC:
    def __init__(self) -> None:
        self.state = DDCState(brightness=36, contrast=79, red_gain=100, green_gain=99, blue_gain=90)
        self.writes: list[dict[str, int]] = []

    def read_state(self, bus: int) -> DDCState:
        return self.state

    def set_vcp_values(self, bus: int, values: dict[str, int], **_kw: object) -> None:
        self.writes.append(dict(values))


class DialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.disp = DisplayInfo(connector="DP-2", drm_card_connector="card1-DP-2", edid_hash="dp2", i2c_bus=8,
                                model="LEN P32p-20")
        self.ref = DisplayInfo(connector="DP-1", drm_card_connector="card1-DP-1", edid_hash="dp1", i2c_bus=7,
                               model="LEN P32u-10")
        QSettings().remove("whiteoffset")
        self.ddc = FakeDDC()

    def _settle(self, dlg: VisualWhiteDialog) -> None:
        for _ in range(5):
            dlg._wait_for_tasks()
            QApplication.processEvents()

    def test_offset_storage_and_shifted_target(self) -> None:
        self.assertEqual(white_offset_for(self.disp), (0.0, 0.0))
        self.assertEqual(shifted_whitepoint(self.disp, None), (D65_X, D65_Y))
        set_white_offset(self.disp, (0.0026, -0.0062))
        self.assertEqual(white_offset_for(self.disp), (0.0026, -0.0062))
        x, y = shifted_whitepoint(self.disp, (D65_X, D65_Y))
        self.assertAlmostEqual(x, D65_X + 0.0026)
        self.assertAlmostEqual(y, D65_Y - 0.0062)
        self.assertEqual(white_offset_for(self.ref), (0.0, 0.0))

    def test_steps_write_gains_and_cancel_restores(self) -> None:
        dlg = VisualWhiteDialog(self.disp, [self.disp, self.ref], self.ddc, lambda *a: None)
        self._settle(dlg)
        self.assertEqual(dlg.start, (100, 99, 90))
        self.assertFalse(dlg.btn_accept.isEnabled())
        dlg.step(MAGENTA)
        self._settle(dlg)
        dlg.step(WARMER)
        self._settle(dlg)
        self.assertEqual(dlg.gains, (100, 98, 89))
        self.assertEqual(self.ddc.writes[-1], {"16": 100, "18": 98, "1A": 89})
        self.assertEqual(dlg.pad.position, (-1, -1))          # one step warmer, one step magenta
        dlg.pad.stepRequested.emit(GREENER)                     # click into the pad
        self._settle(dlg)
        self.assertEqual((dlg.gains, dlg.pad.position), ((100, 99, 89), (-1, 0)))
        self.assertTrue(dlg.btn_accept.isEnabled())
        dlg.reject()
        self.assertEqual(self.ddc.writes[-1], {"16": 100, "18": 99, "1A": 90})
        self.assertEqual(white_offset_for(self.disp), (0.0, 0.0))

    def test_measure_and_save_stores_offset(self) -> None:
        calls = []

        def measure(start, final, on_done, on_failed) -> None:  # noqa: ANN001
            calls.append((start, final))
            on_done(_white(0.3132, 0.3298), _white(0.3153, 0.3228))

        dlg = VisualWhiteDialog(self.disp, [self.disp, self.ref], self.ddc, measure)
        self._settle(dlg)
        dlg.step(MAGENTA)
        self._settle(dlg)
        with mock.patch("kcal_gui.white_offset.QMessageBox.information"):
            dlg._measure_and_save()
        self.assertEqual(calls, [((100, 99, 90), (100, 98, 90))])
        self.assertEqual(white_offset_for(self.disp), (0.0021, -0.007))
        self.assertEqual(dlg.accepted_offset, (0.0021, -0.007))
        self.assertEqual(dlg.result(), dlg.DialogCode.Accepted)


if __name__ == "__main__":
    unittest.main()
