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


if __name__ == "__main__":
    unittest.main()
