"""Offscreen smoke test: main window pages with simulated displays under light and dark colour schemes."""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from kcal_argyll.instruments import InstrumentStatus, parse_spotread_usage
from kcal_core.models import DDCState, DisplayInfo
import kcal_gui.main_window as mw
from kcal_gui.theme import ThemeManager, available_schemes, is_dark, palette_from_scheme


def _displays(**_kw) -> list[DisplayInfo]:  # noqa: ANN003
    return [
        DisplayInfo(connector="DP-1", drm_card_connector="card1-DP-1", edid_hash="a", model="EIZO CS2740",
                    i2c_bus=7, ddc=DDCState(38, 72, 100, 96, 91), color_profile_source="sRGB"),
        DisplayInfo(connector="HDMI-A-1", drm_card_connector="card1-HDMI-A-1", edid_hash="b", model="TV"),
    ]


def _spin(ms: int = 200) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class TestMainWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.tmp.name)
        os.environ["KELVINCAL_PRESETS_PATH"] = os.path.join(cls.tmp.name, "presets.json")
        cls._orig = (mw.discover_displays, mw.detect_instruments)
        mw.discover_displays = _displays
        mw.detect_instruments = lambda: InstrumentStatus("3.4.1", ["X-Rite i1 DisplayPro"])

    @classmethod
    def tearDownClass(cls) -> None:
        mw.discover_displays, mw.detect_instruments = cls._orig
        del os.environ["KELVINCAL_PRESETS_PATH"]
        cls.tmp.cleanup()

    def test_pages_render_in_light_and_dark(self) -> None:
        theme = ThemeManager(self.app)
        win = mw.KelvinCalMainWindow(theme)
        win.show()
        _spin(500)
        self.assertEqual(win.selected_connector, "DP-1")  # display with DDC preferred
        self.assertEqual(len(win.page_simple.monitor_cards), 2)
        self.assertTrue(win.page_simple.btn_start.isEnabled())
        for scheme in ("BreezeLight", "BreezeDark"):
            if not any(s.key == scheme for s in available_schemes()):
                continue
            theme.apply(scheme, save=False)
            self.assertEqual(is_dark(), scheme == "BreezeDark")
            for nav in range(3):
                win._show_nav(nav)
                for mode in (0, 1):
                    win.set_mode(mode)
                    self.assertFalse(win.grab().isNull())
        win.select_display("HDMI-A-1")
        self.assertFalse(win.page_simple.btn_start.isEnabled())  # no DDC/CI
        win.select_display("DP-1")
        win._on_instruments(InstrumentStatus("3.4.1", []))  # sensor unplugged
        self.assertFalse(win.page_simple.btn_start.isEnabled())
        self.assertFalse(win.page_expert.btn_all.isEnabled())
        self.assertTrue(win.page_expert.phase_buttons[0].isEnabled())  # test patch needs no sensor
        win._on_instruments(InstrumentStatus("3.4.1", ["X-Rite i1 DisplayPro"]))
        self.assertTrue(win.page_simple.btn_start.isEnabled())
        theme.apply("", save=False)
        win.close()

    def test_close_during_job_does_not_block(self) -> None:
        """Closing while a job runs cancels it and closes only after the worker has finished."""
        from kcal_gui.controller import CancelToken

        theme = ThemeManager(self.app)
        win = mw.KelvinCalMainWindow(theme)
        win.show()
        _spin(300)

        class FakeJob:
            def deleteLater(self) -> None:  # noqa: N802
                pass

        cancel = CancelToken()
        win._job, win._job_cancel = FakeJob(), cancel
        orig = mw.QMessageBox.question
        mw.QMessageBox.question = staticmethod(lambda *a, **k: mw.QMessageBox.StandardButton.Yes)
        try:
            self.assertFalse(win.close())          # ignored: worker still running
            self.assertTrue(cancel.cancelled)
            self.assertTrue(win.isVisible())
            win._on_job_finished()                 # worker done → window closes by itself
            _spin(100)
            self.assertFalse(win.isVisible())
        finally:
            mw.QMessageBox.question = orig


class TestThemeAndInstruments(unittest.TestCase):
    def test_breeze_dark_palette(self) -> None:
        scheme = next((s for s in available_schemes() if s.key == "BreezeDark"), None)
        if scheme is None:
            self.skipTest("BreezeDark.colors not installed")
        pal = palette_from_scheme(scheme.path)
        self.assertTrue(is_dark(pal))
        self.assertEqual(pal.color(pal.ColorRole.Window).name(), "#202326")

    def test_parse_spotread_usage(self) -> None:
        text = ("Measure spot values, Version 3.4.1\n -c listno  Set instrument port\n"
                "    1 = '/dev/bus/usb/003/070 (X-Rite i1 DisplayPro, ColorMunki Display)'\n -t  ...\n")
        status = parse_spotread_usage(text)
        self.assertEqual((status.argyll_version, status.instruments), ("3.4.1", ["X-Rite i1 DisplayPro"]))


if __name__ == "__main__":
    unittest.main()
