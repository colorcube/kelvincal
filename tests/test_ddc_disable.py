"""The DDC/CI write guard: with `enabled=False` the client must not write a single VCP code."""

from __future__ import annotations

import unittest
from unittest import mock

from kelvincal.ddc import ddc_client
from kelvincal.ddc.ddc_client import DDCClient


class TestDDCClientDisabled(unittest.TestCase):
    def test_no_write_methods_touch_the_bus(self) -> None:
        client = DDCClient(enabled=False)
        with mock.patch.object(ddc_client.subprocess, "run") as run:
            client.set_vcp_values(10, {"10": 40, "12": 70})
            client.set_rgb_gains(10, 100, 90, 95)
            client.set_hue(10, {"red": 45, "blue": 55})
            client.force_settings_apply(10)
            client.set_contrast(10, 60)
            client.set_brightness(10, 30)
        run.assert_not_called()

    def test_readback_probe_is_skipped(self) -> None:
        client = DDCClient(enabled=False)
        with mock.patch.object(ddc_client.subprocess, "run") as run:
            self.assertEqual(client._calibrate_gain_readback(10), {})
        run.assert_not_called()

    def test_read_state_does_not_probe(self) -> None:
        client = DDCClient(enabled=False)
        out = "VCP 10 C 50 100\nVCP 12 C 50 100\nVCP 16 C 120 100\nVCP 18 C 255 100\nVCP 1A C 255 100\n"
        proc = mock.Mock(stdout=out)
        with mock.patch.object(ddc_client.subprocess, "run", return_value=proc) as run, \
                mock.patch.object(client, "_calibrate_gain_readback") as probe:
            state = client.read_state(10)
        probe.assert_not_called()
        self.assertEqual(run.call_count, 1)          # one read, no probe writes
        self.assertEqual(state.brightness, 50)

    def test_enabled_client_still_writes(self) -> None:
        client = DDCClient(enabled=True)
        with mock.patch.object(ddc_client.subprocess, "run") as run:
            client.set_vcp_values(10, {"10": 40}, settle=False)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
