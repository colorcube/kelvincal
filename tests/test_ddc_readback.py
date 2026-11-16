"""Tests for DDC gain readback scale calibration and normalization."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kelvincal.ddc import ddc_client
from kelvincal.ddc.ddc_client import DDCClient, classify_gain_channel, derive_scale, normalized_gain


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


class TestGainChannelClassification(unittest.TestCase):
    def test_passthrough_red_channel(self) -> None:
        # JBM32O240 red: writes/reads hit a raw 0-255 register while max advertises 100
        probes = [(64, 65), (32, 32)]
        range_probe = (200, 201)
        read_scale, write_scale = classify_gain_channel(probes, range_probe, 100)
        self.assertAlmostEqual(read_scale, 2.55, places=2)
        self.assertAlmostEqual(write_scale, 2.55, places=2)

    def test_scaled_write_channel(self) -> None:
        # JBM32O240 green/blue: writes 0-100, reads raw 0-255
        probes = [(64, 163), (32, 82)]
        range_probe = (200, 255)
        read_scale, write_scale = classify_gain_channel(probes, range_probe, 100)
        self.assertAlmostEqual(read_scale, 2.55, places=2)
        self.assertEqual(write_scale, 1.0)

    def test_honest_channel(self) -> None:
        # Normal 0-100 panel: write above max clamps back to max
        probes = [(64, 64), (32, 33)]
        range_probe = (200, 100)
        read_scale, write_scale = classify_gain_channel(probes, range_probe, 100)
        self.assertEqual((read_scale, write_scale), (1.0, 1.0))

    def test_no_range_probe(self) -> None:
        self.assertEqual(classify_gain_channel([(64, 64), (32, 32)], None, 100), (1.0, 1.0))


class TestCalibrationPersistence(unittest.TestCase):
    def test_second_instance_does_not_reprobe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "ddc_calibration.json"
            with mock.patch.object(ddc_client, "CALIBRATION_STORE", store):
                fake_proc = mock.Mock(stdout="VCP 10 C 63 100\nVCP 12 C 40 100\n"
                                            "VCP 16 C 120 100\nVCP 18 C 255 100\nVCP 1A C 255 100\n")
                with mock.patch.object(ddc_client.subprocess, "run", return_value=fake_proc), \
                        mock.patch.object(DDCClient, "_calibrate_gain_readback",
                                          side_effect=lambda bus: {"16": (2.55, 0.0, 2.55),
                                                                   "18": (2.55, 0.0, 1.0),
                                                                   "1A": (2.55, 0.0, 1.0)}) as calibrate:
                    first = DDCClient()
                    first.read_state(10)
                    self.assertEqual(calibrate.call_count, 1)
                    second = DDCClient()
                    second.read_state(10)
                    self.assertEqual(calibrate.call_count, 1)
                    self.assertEqual(second.read_state(10).red_gain, 47)


if __name__ == "__main__":
    unittest.main()


class TestInputToggleAndHue(unittest.TestCase):
    def test_force_settings_apply_toggles_and_restores(self) -> None:
        client = DDCClient()
        writes: list[dict] = []
        with mock.patch.object(client, "set_vcp_values",
                               side_effect=lambda bus, pairs, settle=True, verify=False: writes.append(dict(pairs))), \
                mock.patch.object(client, "read_input_source", return_value=0x0F), \
                mock.patch.object(ddc_client, "APPLY_SETTLE_SECONDS", 0.0):
            client.force_settings_apply(10)
        self.assertEqual(writes, [{"60": 0x11}, {"60": 0x0F}])

    def test_force_settings_apply_swaps_when_on_alternate(self) -> None:
        client = DDCClient()
        writes: list[dict] = []
        with mock.patch.object(client, "set_vcp_values",
                               side_effect=lambda bus, pairs, settle=True, verify=False: writes.append(dict(pairs))), \
                mock.patch.object(client, "read_input_source", return_value=0x11), \
                mock.patch.object(ddc_client, "APPLY_SETTLE_SECONDS", 0.0):
            client.force_settings_apply(10)
        self.assertEqual(writes, [{"60": 0x0F}, {"60": 0x11}])

    def test_read_hue(self) -> None:
        client = DDCClient()
        out = "VCP 9B C 50 100\nVCP 9C C 51 100\nVCP 9D C 52 100\nVCP 9E C 50 100\nVCP 9F C 49 100\nVCP A0 C 50 100\n"
        with mock.patch.object(client, "_getvcp_raw_output", return_value=out):
            hue = client.read_hue(10)
        self.assertEqual(hue, {"red": 50, "yellow": 51, "green": 52, "cyan": 50, "blue": 49, "magenta": 50})

    def test_set_hue(self) -> None:
        client = DDCClient()
        writes: list[dict] = []
        with mock.patch.object(client, "set_vcp_values",
                               side_effect=lambda bus, pairs, settle=True, verify=False: writes.append(dict(pairs))):
            client.set_hue(10, {"red": 45, "blue": 55})
        self.assertEqual(writes, [{"9B": 45, "9F": 55}])
