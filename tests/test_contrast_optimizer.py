"""Unit tests for the binary-search ContrastOptimizer (including single-channel clipping) and PresetManager."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from kcal_core.models import ColorMeasurement, D65_X, D65_Y, DDCState, DisplayInfo
from kcal_ddc.contrast_optimizer import ContrastOptimizationConfig, ContrastOptimizer
from kcal_presets.manager import PresetManager


def _xyz_from_xyY(x: float, y: float, Y: float) -> tuple[float, float, float]:
    X = (x / y) * Y
    Z = ((1.0 - x - y) / y) * Y
    return (X, Y, Z)


class TestOptimizersAndPresets(unittest.TestCase):
    def test_binary_search_contrast_optimizer_luminance_clipping(self) -> None:
        """Simulates a panel that scales linearly up to contrast 72 and clips starting at 73."""
        true_max_unclipped_contrast = 72
        current_k = 50

        def set_contrast(k: int) -> None:
            nonlocal current_k
            current_k = k

        def measure_patch(rgb: tuple[int, int, int]) -> ColorMeasurement:
            level = rgb[0] / 255.0
            gain = current_k / float(true_max_unclipped_contrast)
            effective_signal = min(1.0, level * gain)
            Y = 140.0 * (effective_signal ** 2.2)
            X, Y_val, Z = _xyz_from_xyY(D65_X, D65_Y, Y)
            return ColorMeasurement(rgb=rgb, X=X, Y=Y_val, Z=Z)

        optimizer = ContrastOptimizer(
            ContrastOptimizationConfig(min_contrast=40, max_contrast=90, low_level=248)
        )
        res = optimizer.run(set_contrast, measure_patch)

        self.assertTrue(6 <= len(res.steps) <= 7)
        self.assertIn(res.optimal_contrast, (71, 72))
        self.assertEqual(current_k, res.optimal_contrast)

    def test_binary_search_detects_single_channel_blue_clipping(self) -> None:
        """Verifies that even when luminance Y barely drops, single-channel clipping is caught via Δu'v'."""
        current_k = 50

        def set_contrast(k: int) -> None:
            nonlocal current_k
            current_k = k

        def measure_patch(rgb: tuple[int, int, int]) -> ColorMeasurement:
            level = rgb[0] / 255.0
            Y = 140.0 * (level ** 2.2) * (current_k / 65.0)
            if current_k >= 66 and rgb[0] == 255:
                x, y = D65_X + 0.006, D65_Y + 0.006
            else:
                x, y = D65_X, D65_Y
            X, Y_val, Z = _xyz_from_xyY(x, y, Y)
            return ColorMeasurement(rgb=rgb, X=X, Y=Y_val, Z=Z)

        optimizer = ContrastOptimizer(
            ContrastOptimizationConfig(min_contrast=40, max_contrast=90, low_level=248)
        )
        res = optimizer.run(set_contrast, measure_patch)

        self.assertEqual(res.optimal_contrast, 65)
        clipped_66_or_higher = [s for s in res.steps if s.contrast >= 66]
        self.assertTrue(all(s.clipped and "single-channel" in s.reason for s in clipped_66_or_higher))

    def test_preset_manager_capture_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            preset_file = Path(tmp_dir) / "presets.json"
            mgr = PresetManager(config_path=preset_file)

            fake_displays = [
                DisplayInfo(
                    connector="DP-2",
                    drm_card_connector="card1-DP-2",
                    edid_hash="0123456789abcdef0123456789abcdef",
                    model="LEN P32p-20",
                    serial="SN-MOCK-003",
                    i2c_bus=8,
                    color_profile_source="ICC",
                    icc_profile_path="/home/user/.local/share/icc/Monitor_1.icc",
                    ddc=DDCState(
                        brightness=87, contrast=60, red_gain=99, green_gain=100, blue_gain=99
                    ),
                )
            ]

            saved = mgr.capture_current_state(
                name="Photography (140 cd/m²)",
                description="Test preset",
                displays=fake_displays,
            )
            self.assertEqual(saved.name, "Photography (140 cd/m²)")

            active_name, loaded = mgr.load_all()
            self.assertEqual(active_name, "Photography (140 cd/m²)")
            self.assertEqual(len(loaded), 1)
            self.assertEqual(
                loaded[0].displays[0].edid_hash, "0123456789abcdef0123456789abcdef"
            )
            self.assertEqual(loaded[0].displays[0].ddc_brightness, 87)
            self.assertEqual(loaded[0].displays[0].ddc_contrast, 60)


if __name__ == "__main__":
    unittest.main()
