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
            with mock.patch.object(ddc_client, "CALIBRATION_STORE", store), \
                    mock.patch.object(ddc_client, "_bus_edid_map", return_value={}):
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

    def test_persisted_factors_apply_even_when_raw_values_below_max(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "ddc_calibration.json"
            with mock.patch.object(ddc_client, "CALIBRATION_STORE", store), \
                    mock.patch.object(ddc_client, "_bus_edid_map", return_value={10: "edid-qdoled"}):
                ddc_client.save_calibrations({"edid-qdoled": {"16": (2.55, 0.0, 2.55),
                                                              "18": (2.55, 0.0, 1.0),
                                                              "1A": (2.55, 0.0, 1.0)}})
                low_proc = mock.Mock(stdout="VCP 10 C 50 100\nVCP 12 C 70 100\n"
                                            "VCP 16 C 89 100\nVCP 18 C 97 100\nVCP 1A C 99 100\n")
                with mock.patch.object(ddc_client.subprocess, "run", return_value=low_proc):
                    state = DDCClient().read_state(10)
                self.assertEqual((state.red_gain, state.green_gain, state.blue_gain), (35, 38, 39))

    def test_set_vcp_values_and_set_rgb_gains_scale_passthrough_without_double_scaling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "ddc_calibration.json"
            with mock.patch.object(ddc_client, "CALIBRATION_STORE", store), \
                    mock.patch.object(ddc_client, "_bus_edid_map", return_value={10: "edid-qdoled"}):
                ddc_client.save_calibrations({"edid-qdoled": {"16": (2.55, 0.0, 2.55),
                                                              "18": (2.55, 0.0, 1.0),
                                                              "1A": (2.55, 0.0, 1.0)}})
                client = DDCClient(settle_seconds=0)
                with mock.patch.object(ddc_client.subprocess, "run") as run_mock:
                    client.set_vcp_values(10, {"10": 50, "16": 47, "18": 100, "1A": 95})
                    client.set_rgb_gains(10, 47, 100, 95)
                first_cmd = run_mock.call_args_list[0].args[0]
                second_cmd = run_mock.call_args_list[1].args[0]
                self.assertEqual(first_cmd[-8:], ["10", "50", "16", "120", "18", "100", "1A", "95"])
                self.assertEqual(second_cmd[-6:], ["16", "120", "18", "100", "1A", "95"])

    def test_edid_key_survives_i2c_bus_renumbering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "ddc_calibration.json"
            with mock.patch.object(ddc_client, "CALIBRATION_STORE", store):
                ddc_client.save_calibrations({"edid-qdoled": {"16": (2.55, 0.0, 2.55),
                                                              "18": (2.55, 0.0, 1.0),
                                                              "1A": (2.55, 0.0, 1.0)}})
                # After reboot: bus 7 is now a normal EIZO, bus 9 is the QD-OLED
                with mock.patch.object(ddc_client, "_bus_edid_map",
                                       return_value={7: "edid-eizo", 9: "edid-qdoled"}):
                    client = DDCClient(settle_seconds=0)
                    with mock.patch.object(ddc_client.subprocess, "run") as run_mock:
                        client.set_rgb_gains(7, 100, 96, 91)
                        client.set_rgb_gains(9, 47, 100, 95)
                    self.assertEqual(run_mock.call_args_list[0].args[0][-6:], ["16", "100", "18", "96", "1A", "91"])
                    self.assertEqual(run_mock.call_args_list[1].args[0][-6:], ["16", "120", "18", "100", "1A", "95"])

    def test_failed_gain_probe_restores_raw_value_without_clamping(self) -> None:
        client = DDCClient(settle_seconds=0)
        written: list[dict[str, int]] = []

        def fake_set(_bus: int, pairs: dict[str, int], **_kw) -> None:  # noqa: ANN003
            written.append(dict(pairs))
            if len(written) == 1:
                raise RuntimeError("I2C bus hiccup during probe")

        with mock.patch.object(client, "_getvcp_raw", side_effect=[(200, 100), None, None]), \
                mock.patch.object(client, "set_vcp_values", side_effect=fake_set):
            with self.assertRaises(RuntimeError):
                client._calibrate_gain_readback(10)
        # First call was the failed probe, second call in finally restores raw 200 (not clamped 100)
        self.assertEqual(written[-1], {"16": 200})


if __name__ == "__main__":
    unittest.main()
