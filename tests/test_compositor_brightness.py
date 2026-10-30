"""KWin backend: compositor brightness is only synced for outputs whose DDC/CI KWin controls."""

from __future__ import annotations

import unittest
from unittest import mock

from kcal_core.compositor.base import CompositorOutputState
from kcal_core.compositor.kwin import KWinBackend


class SyncBrightnessTest(unittest.TestCase):
    def test_only_differing_outputs_with_ddc_control(self) -> None:
        backend = KWinBackend.__new__(KWinBackend)
        outputs = {
            "DP-1": CompositorOutputState(connector="DP-1", brightness=0.87, allow_ddc_ci=True),
            "DP-2": CompositorOutputState(connector="DP-2", brightness=0.25, allow_ddc_ci=True),
            "HDMI-A-2": CompositorOutputState(connector="HDMI-A-2", brightness=1.0, allow_ddc_ci=False),
        }
        with mock.patch.object(KWinBackend, "get_outputs", return_value=outputs), \
                mock.patch.object(KWinBackend, "_kscreen") as run:
            changed = backend.sync_brightness({"DP-1": 36, "DP-2": 25, "HDMI-A-2": 40, "DP-3": 50})
        self.assertEqual(changed, ["DP-1"])
        run.assert_called_once_with(["output.DP-1.brightness.36"])


if __name__ == "__main__":
    unittest.main()
