"""Applying a preset writes all DDC values (a cached display state may be stale) and syncs KWin's brightness."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from kelvincal.core.compositor.base import CompositorBackend, CompositorOutputState
from kelvincal.core.models import DDCState, DisplayInfo, DisplayPresetEntry, Preset
from kelvincal.presets.manager import PresetManager


class FakeCompositor(CompositorBackend):
    def __init__(self) -> None:
        self.synced: list[dict[str, int]] = []

    @property
    def name(self) -> str:
        return "fake"

    def get_outputs(self) -> dict[str, CompositorOutputState]:
        return {}

    def apply_output_profile(self, *a, **k) -> None:  # noqa: ANN002, ANN003
        pass

    def apply_batch(self, updates) -> None:  # noqa: ANN001
        pass

    def sync_brightness(self, values: dict[str, int]) -> list[str]:
        self.synced.append(dict(values))
        return list(values)


class FakeDDC:
    def __init__(self) -> None:
        self.writes: list[tuple[int, dict[str, int]]] = []

    def set_vcp_values(self, bus, values, verify=True, settle=True) -> None:  # noqa: ANN001
        self.writes.append((bus, dict(values)))


class PresetApplyTest(unittest.TestCase):
    def test_stale_cache_does_not_skip_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            comp, ddc = FakeCompositor(), FakeDDC()
            mgr = PresetManager(config_path=Path(tmp) / "p.json", compositor=comp, ddc_client=ddc)
            mgr.save_all([Preset("Office", displays=[DisplayPresetEntry(
                edid_hash="h", connector="HDMI-A-2", ddc_brightness=36, ddc_contrast=83, ddc_red_gain=100,
                ddc_green_gain=91, ddc_blue_gain=99, icc_profile="/p.icc")])])
            # the cache claims the display already has the preset values; the hardware may not
            cached = DisplayInfo(connector="HDMI-A-2", drm_card_connector="c", edid_hash="h", i2c_bus=5,
                                 icc_profile_path="/p.icc", color_profile_source="ICC",
                                 ddc=DDCState(brightness=36, contrast=83, red_gain=100, green_gain=91, blue_gain=99))
            mgr.apply_preset("Office", displays=[cached])
            self.assertEqual(ddc.writes, [(5, {"10": 36, "12": 83, "16": 100, "18": 91, "1A": 99})])
            self.assertEqual(comp.synced, [{"HDMI-A-2": 36}])


if __name__ == "__main__":
    unittest.main()
