"""Offscreen smoke test: main window pages with simulated displays under light and dark colour schemes."""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from kelvincal.argyll.instruments import InstrumentStatus, parse_spotread_usage
from kelvincal.core.models import DDCState, DisplayInfo
import kelvincal.gui.main_window as mw
from kelvincal.gui.theme import ThemeManager, available_schemes, is_dark, palette_from_scheme


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

    def setUp(self) -> None:
        QSettings().clear()

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
        self.assertFalse(win.page_simple.workflow_cards["ddc"].isEnabled())  # no DDC/CI
        self.assertEqual(win.page_simple.current_workflow(), "software")
        self.assertTrue(win.page_simple.btn_start.isEnabled())               # software workflow needs no DDC/CI
        self.assertFalse(win.page_expert.btn_all.isEnabled())                # expert defaults to DDC workflow
        win.select_display("DP-1")
        win._on_instruments(InstrumentStatus("3.4.1", []))  # sensor unplugged
        self.assertFalse(win.page_simple.btn_start.isEnabled())
        self.assertFalse(win.page_expert.btn_all.isEnabled())
        self.assertFalse(win.page_expert.phase_buttons[0].isEnabled())
        win._on_instruments(InstrumentStatus("3.4.1", ["X-Rite i1 DisplayPro"]))
        self.assertTrue(win.page_simple.btn_start.isEnabled())
        self.assertFalse(win.act_measure_ccss.isEnabled())               # colorimeter only
        win._on_instruments(InstrumentStatus("3.4.1", ["X-Rite i1 DisplayPro", "X-Rite i1 Pro"], [1, 2]))
        self.assertTrue(win.act_measure_ccss.isEnabled())
        self.assertTrue(win.page_expert.selector.correction.btn_measure.isEnabled())
        applied: list[str] = []
        win.activate_preset = applied.append                # an updated active preset is applied again
        win.active_preset = "Office"
        win._reapply_if_active(["Photo"])
        win._reapply_if_active(["Office", "Photo"])
        self.assertEqual(applied, ["Office"])
        del win.activate_preset
        # D-Bus requests (plasmoid, second start)
        win.presets = [mw.Preset(name="Office", displays=[])]
        win._job = object()
        self.assertIn("measurement", win.apply_preset_request("Office"))       # refused while measuring
        win._job = None
        self.assertIn("Office2", win.apply_preset_request("Office2"))          # unknown preset
        self.assertEqual(win.status_dict(), {"active_preset": "Office", "busy": False, "applying": "",
                                             "preset_error": ""})
        win._show_nav(mw.NAV_PRESETS)
        win.bring_to_front("HDMI-A-1")
        self.assertEqual((win.selected_connector, win.nav.currentRow()), ("HDMI-A-1", mw.NAV_MONITORS))
        theme.apply("", save=False)
        win.close()

    def test_close_during_job_does_not_block(self) -> None:
        """Closing while a job runs cancels it and closes only after the worker has finished."""
        from kelvincal.gui.controller import CancelToken

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


    def test_test_patch_window_toggles(self) -> None:
        """A second click on "Test Patch Window" closes the open window again."""
        from PySide6.QtCore import QObject, Signal

        class FakeWindow(QObject):
            confirmed = Signal()
            aborted = Signal()
            instances: list = []

            def __init__(self, connector: str) -> None:
                super().__init__()
                self.visible = False
                FakeWindow.instances.append(self)

            def show_placement(self, prompt, hints=None) -> None:  # noqa: ANN001
                self.visible = True

            def close(self) -> None:
                self.visible = False

        orig = mw.WaylandPatchWindow
        mw.WaylandPatchWindow = FakeWindow
        try:
            win = mw.KelvinCalMainWindow(ThemeManager(self.app))
            _spin(300)
            win.act_test_patch.trigger()
            self.assertTrue(FakeWindow.instances[-1].visible)
            self.assertTrue(win.act_test_patch.isChecked())
            win.act_test_patch.trigger()                     # second trigger closes it
            self.assertFalse(FakeWindow.instances[-1].visible)
            self.assertIsNone(win._test_window)
            self.assertFalse(win.act_test_patch.isChecked())
            win.act_test_patch.trigger()                     # opens a new one
            FakeWindow.instances[-1].confirmed.emit()        # Space in the window
            self.assertFalse(win.act_test_patch.isChecked())
            self.assertEqual(len(FakeWindow.instances), 2)
            win.act_test_patch.trigger()
            win.close()                                      # closing the app closes the test window too
            self.assertFalse(FakeWindow.instances[-1].visible)
            self.assertIsNone(win._test_window)
        finally:
            mw.WaylandPatchWindow = orig

    def test_batch_uses_simple_page_workflow_over_expert_setting(self) -> None:
        """Starting a batch from Simple Mode uses Simple Mode's workflow even if Expert Mode saved 'software'."""
        from kelvincal.core.targets import TARGETS, WORKFLOW_DDC, WORKFLOW_SOFTWARE

        class FakeBatchDialog:
            last_kwargs: dict = {}

            def __init__(self, targets, display_label, preselect="", parent=None, **kwargs) -> None:  # noqa: ANN001, ANN003
                FakeBatchDialog.last_kwargs = kwargs
                self._targets = [targets[0]]
                self.verify = True

            def exec(self) -> int:
                return mw.QDialog.DialogCode.Accepted

            def selected_targets(self):  # noqa: ANN202
                return list(self._targets)

        orig_dlg = mw.BatchSetupDialog
        mw.BatchSetupDialog = FakeBatchDialog
        try:
            win = mw.KelvinCalMainWindow(ThemeManager(self.app))
            _spin(200)
            # Simulate stale QSettings leaving Expert Mode on 'software' while Simple Mode is on 'ddc' for DP-1
            win.page_expert.seg_workflow.setCurrentIndex(1)
            self.assertEqual(win.page_expert.parameters().workflow, WORKFLOW_SOFTWARE)
            self.assertEqual(win.page_simple.current_workflow(), WORKFLOW_DDC)

            captured: list[tuple[list, tuple[str, ...]]] = []

            class FakeCtl:
                def run_batch(self, items, _contrast_cfg, _verify):  # noqa: ANN001, ANN202
                    captured.append((items, ()))
                    return []

            def fake_start_job(fn, _on_done, _err_title, _subtitle, phases, _rng) -> None:  # noqa: ANN001
                fn(FakeCtl())
                captured[-1] = (captured[-1][0], phases)

            win._start_job = fake_start_job  # type: ignore[method-assign]
            win.action_run_batch("DP-1")
            self.assertEqual(FakeBatchDialog.last_kwargs["workflow"], WORKFLOW_DDC)
            items, phases = captured[-1]
            self.assertEqual([it.profile_config.workflow for it in items], [WORKFLOW_DDC])
            self.assertEqual(phases, ("1a", "1b", "2", "3"))

            # Non-DDC display (HDMI-A-1) in Simple Mode uses 'software' workflow and allows batch run
            win.action_run_batch("HDMI-A-1")
            self.assertEqual(FakeBatchDialog.last_kwargs["workflow"], WORKFLOW_SOFTWARE)
            items_sw, phases_sw = captured[-1]
            self.assertEqual([it.profile_config.workflow for it in items_sw], [WORKFLOW_SOFTWARE])
            self.assertEqual(phases_sw, ("1s", "2", "3"))
            self.assertEqual(items_sw[0].target_luminance, TARGETS[0].luminance)
            win.close()
        finally:
            mw.BatchSetupDialog = orig_dlg

    def test_presets_watcher_ignored_while_applying_preset(self) -> None:
        """File-watcher events while `activate_preset` is running must not trigger a parallel `refresh_displays`."""
        win = mw.KelvinCalMainWindow(ThemeManager(self.app))
        _spin(200)
        refreshes: list[bool] = []
        win.refresh_displays = lambda then=None: refreshes.append(True)  # type: ignore[method-assign]
        win.preset_manager.upsert_preset(mw.Preset(name="Office", displays=[]))
        # Simulatepresets.json mtime change occurring while a preset is being applied in the worker thread
        win._presets_seen = 0.0
        win._applying_preset = "Office"
        win._on_presets_file()
        self.assertEqual(refreshes, [])
        # Once _applying_preset clears and mtime differs, external changes refresh displays again
        win._applying_preset = ""
        win._on_presets_file()
        self.assertEqual(refreshes, [True])
        win.close()


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


class TestExpertProfileType(unittest.TestCase):
    """The profile type selector offers cLUT, Shaper + Matrix and Matrix (colprof -a X/s/m)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from kelvincal.gui.pages.monitors_expert import MonitorsExpertPage

        self.page = MonitorsExpertPage()
        self.settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                                  "kelvincal-test", "profile-type")
        self.settings.clear()

    def tearDown(self) -> None:
        self.settings.clear()
        self.page.deleteLater()

    def test_three_options_map_to_colprof_codes(self) -> None:
        self.assertEqual(self.page.seg_type.count(), 3)
        self.assertEqual(self.page.seg_type.labels, ["cLUT", "Shaper + Matrix", "Matrix"])
        for index, code in enumerate(("X", "s", "m")):
            self.page.seg_type.setCurrentIndex(index)
            self.assertEqual(self.page.parameters().profile_type, code)

    def test_each_option_has_a_tooltip(self) -> None:
        self.assertEqual(len(self.page.seg_type.tooltips), 3)
        self.assertTrue(all(self.page.seg_type.tooltips))

    def test_settings_round_trip_keeps_shaper(self) -> None:
        self.page.seg_type.setCurrentIndex(1)
        self.page.save_settings(self.settings)
        self.page.seg_type.setCurrentIndex(0)
        self.page.restore_settings(self.settings)
        self.assertEqual(self.page.parameters().profile_type, "s")

    def test_legacy_index_setting_maps_to_matrix(self) -> None:
        # Old builds stored the segment index of a two-option control: 1 meant Matrix.
        self.settings.setValue("params/profile_type", 1)
        self.page.restore_settings(self.settings)
        self.assertEqual(self.page.parameters().profile_type, "m")
        self.settings.setValue("params/profile_type", 0)
        self.page.restore_settings(self.settings)
        self.assertEqual(self.page.parameters().profile_type, "X")


if __name__ == "__main__":
    unittest.main()
