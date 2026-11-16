"""Tests for DDC gain readback scale calibration and normalization."""

from __future__ import annotations

import unittest

from kelvincal.ddc.ddc_client import derive_scale, normalized_gain


class TestReadbackScale(unittest.TestCase):
    # JBM32O240: green/blue read back on a 0-255 scale while advertising max 100
    def test_2_55x_scale_detected(self) -> None:
        probes = [(20, 51), (60, 153), (100, 255)]
        scale = derive_scale(probes)
        self.assertAlmostEqual(scale, 2.55, places=1)

    def test_identity_scale(self) -> None:
        # Red on the same panel tracks writes 1:1
        scale = derive_scale([(20, 21), (40, 41)])
        self.assertAlmostEqual(scale, 1.0, places=1)

    def test_absurd_scale_rejected(self) -> None:
        self.assertEqual(derive_scale([(10, 20), (20, 4000)]), 1.0)

    def test_too_few_probes(self) -> None:
        self.assertEqual(derive_scale([(64, 163)]), 1.0)

    def test_normalize_255_readback(self) -> None:
        self.assertEqual(normalized_gain(153, 2.55, 0.0, 100), 60)
        self.assertEqual(normalized_gain(255, 2.55, 0.0, 100), 100)
        self.assertEqual(normalized_gain(51, 2.55, 0.0, 100), 20)

    def test_normalize_over_range_red(self) -> None:
        # Red read 120 against max 100 (scale 1.0) clamps to max, not clip
        self.assertEqual(normalized_gain(120, 1.0, 0.0, 100), 100)

    def test_normalize_identity(self) -> None:
        self.assertEqual(normalized_gain(87, 1.0, 0.0, 100), 87)


if __name__ == "__main__":
    unittest.main()
