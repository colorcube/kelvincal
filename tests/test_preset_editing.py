"""Tests for preset rename/duplicate/delete and drift detection."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from kcal_core.models import DDCState, DisplayInfo, DisplayPresetEntry, Preset
from kcal_presets.manager import PresetManager, preset_drift


class _NoCompositor:
    pass


def _manager(tmp: str) -> PresetManager:
    return PresetManager(config_path=Path(tmp) / "presets.json", compositor=_NoCompositor(), ddc_client=object())  # type: ignore[arg-type]


def _entry() -> DisplayPresetEntry:
    return DisplayPresetEntry(edid_hash="h1", connector="DP-2", ddc_brightness=41, ddc_blue_gain=92,
                              icc_profile="/icc/a.icc")


class TestPresetEditing(unittest.TestCase):
    def test_rename_duplicate_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = _manager(tmp)
            mgr.upsert_preset(Preset(name="Foto", displays=[_entry()]), mark_active=True)
            mgr.rename_preset("Foto", "Fotobearbeitung")
            active, presets = mgr.load_all()
            self.assertEqual(active, "Fotobearbeitung")
            mgr.duplicate_preset("Fotobearbeitung", "Kopie")
            self.assertEqual([p.name for p in mgr.load_all()[1]], ["Fotobearbeitung", "Kopie"])
            with self.assertRaises(ValueError):
                mgr.rename_preset("Kopie", "Fotobearbeitung")
            mgr.delete_preset("Fotobearbeitung")
            active, presets = mgr.load_all()
            self.assertEqual((active, [p.name for p in presets]), ("", ["Kopie"]))

    def test_drift(self) -> None:
        live = DisplayInfo(connector="DP-2", drm_card_connector="card1-DP-2", edid_hash="h1",
                           ddc=DDCState(brightness=41, blue_gain=89), icc_profile_path="/icc/a.icc",
                           color_profile_source="ICC")
        preset = Preset(name="Foto", displays=[_entry()])
        self.assertEqual(preset_drift(preset, [live]), {"DP-2": ["ddc_blue_gain"]})
        live.ddc.blue_gain = 92
        self.assertEqual(preset_drift(preset, [live]), {})


class TestPresetsPage(unittest.TestCase):
    def test_actions_per_display_column(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from kcal_gui.pages.presets import PresetsPage

        _app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            icc = Path(tmp) / "a.icc"
            icc.write_bytes(b"")
            entries = [DisplayPresetEntry(edid_hash="h1", connector="DP-2", icc_profile=str(icc)),
                       DisplayPresetEntry(edid_hash="h2", connector="DP-9", icc_profile="/missing.icc")]
            live = [DisplayInfo(connector="DP-2", drm_card_connector="card1-DP-2", edid_hash="h1")]
            page = PresetsPage()
            page.set_data("Foto", [Preset(name="Foto", displays=entries)], live)
            self.assertEqual(len(page.column_buttons), 2)
            (recal1, show1), (recal2, show2) = page.column_buttons
            self.assertEqual((recal1.isEnabled(), show1.isEnabled()), (True, True))
            self.assertEqual((recal2.isEnabled(), show2.isEnabled()), (False, False))   # not connected, no file
            requested: list[str] = []
            page.recalibrate_requested.connect(requested.append)
            page.inspect_requested.connect(requested.append)
            recal1.click()
            show1.click()
            self.assertEqual(requested, ["DP-2", str(icc)])
            page.set_busy(True)
            self.assertFalse(recal1.isEnabled())

    def test_columns_follow_the_desktop_arrangement(self) -> None:
        import os
        from unittest import mock

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QRect
        from PySide6.QtWidgets import QApplication

        import kcal_gui.pages.presets as presets_mod

        _app = QApplication.instance() or QApplication([])
        entries = [DisplayPresetEntry(edid_hash=h, connector=c) for h, c in
                   (("a", "DP-1"), ("b", "DP-2"), ("c", "HDMI-A-2"), ("d", "DP-9"))]
        geometries = {"DP-1": QRect(2560, 0, 2560, 1440), "DP-2": QRect(5120, 0, 2560, 1440),
                      "HDMI-A-2": QRect(0, 0, 2560, 1440)}
        with mock.patch.object(presets_mod, "screen_geometries", lambda: geometries):
            page = presets_mod.PresetsPage()
            page.set_data("P", [Preset(name="P", displays=entries)], [])
        headers = [page.table.horizontalHeaderItem(c).text().split("\n")[0] for c in range(4)]
        self.assertEqual(headers, ["HDMI-A-2", "DP-1", "DP-2", "DP-9"])   # unplaced display last


if __name__ == "__main__":
    unittest.main()
