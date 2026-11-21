"""KWin backend: compositor brightness is only synced for outputs whose DDC/CI KWin controls."""

from __future__ import annotations

import unittest
from unittest import mock

from kelvincal.core.compositor.base import (
    CalibrationColorGuard,
    CompositorBackend,
    CompositorOutputState,
    NightLightInhibitor,
)
from kelvincal.core.compositor.kwin import KWinBackend


class _RecordingBackend(CompositorBackend):
    def __init__(self, outputs: dict[str, CompositorOutputState]) -> None:
        self._outputs = outputs
        self.applied: list[dict[str, object]] = []

    @property
    def name(self) -> str:
        return "fake"

    def get_outputs(self) -> dict[str, CompositorOutputState]:
        return self._outputs

    def apply_output_profile(
        self,
        connector: str,
        icc_profile_path: str = "",
        color_profile_source: str = "ICC",
        brightness: float | None = None,
        disable_hdr_wcg: bool = False,
    ) -> None:
        self.applied.append(
            {
                "connector": connector,
                "icc": icc_profile_path,
                "source": color_profile_source,
                "brightness": brightness,
            }
        )

    def apply_batch(self, updates: list[dict[str, object]]) -> None:
        pass


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


class SoftwareDimmingGuardTest(unittest.TestCase):
    def test_external_non_ddc_resets_software_dimming_even_when_allow_ddc_true(self) -> None:
        backend = _RecordingBackend(
            {"HDMI-A-1": CompositorOutputState(connector="HDMI-A-1", brightness=0.72, allow_ddc_ci=True)}
        )
        with CalibrationColorGuard(backend, "HDMI-A-1", settle_seconds=0.0, ddc_answers=False):
            pass
        self.assertEqual(backend.applied[0]["brightness"], 1.0)
        self.assertEqual(backend.applied[1]["brightness"], 0.72)

    def test_internal_edp_panel_never_resets_backlight_brightness(self) -> None:
        backend = _RecordingBackend(
            {"eDP-1": CompositorOutputState(connector="eDP-1", brightness=0.60, allow_ddc_ci=False)}
        )
        with CalibrationColorGuard(backend, "eDP-1", settle_seconds=0.0, ddc_answers=False):
            pass
        self.assertIsNone(backend.applied[0]["brightness"])
        self.assertIsNone(backend.applied[1]["brightness"])

    def test_external_ddc_panel_with_allow_ddc_true_keeps_hardware_brightness(self) -> None:
        backend = _RecordingBackend(
            {"DP-1": CompositorOutputState(connector="DP-1", brightness=0.80, allow_ddc_ci=True)}
        )
        with CalibrationColorGuard(backend, "DP-1", settle_seconds=0.0, ddc_answers=True):
            pass
        self.assertIsNone(backend.applied[0]["brightness"])
        self.assertIsNone(backend.applied[1]["brightness"])


class NightLightInhibitorTest(unittest.TestCase):
    def test_waits_for_temperature_ramp_and_uninhibits(self) -> None:
        from PySide6.QtDBus import QDBusMessage

        temps = [4500, 5600, 6500]
        calls: list[tuple] = []

        class FakeReply:
            def type(self):  # noqa: ANN202
                return QDBusMessage.MessageType.ReplyMessage

            def arguments(self):  # noqa: ANN202
                return [42]

        class FakeIface:
            def __init__(self, *args) -> None:  # noqa: ANN002
                pass

            def property(self, name: str):  # noqa: ANN202
                if name == "running":
                    return True
                if name == "currentTemperature":
                    return temps.pop(0) if len(temps) > 1 else temps[0]
                return None

            def call(self, method: str, *args):  # noqa: ANN002, ANN202
                calls.append((method, *args))
                return FakeReply()

        class FakeBus:
            def isConnected(self) -> bool:  # noqa: N802
                return True

        with mock.patch("PySide6.QtDBus.QDBusConnection.connectToBus", return_value=FakeBus()), \
                mock.patch("PySide6.QtDBus.QDBusConnection.disconnectFromBus") as disc, \
                mock.patch("PySide6.QtDBus.QDBusInterface", FakeIface):
            with NightLightInhibitor(transition_timeout_s=0.5, poll_interval_s=0.01):
                self.assertEqual(calls, [("inhibit",)])
                self.assertEqual(temps, [6500])  # waited until 6500 K reached
        self.assertEqual(calls, [("inhibit",), ("uninhibit", 42)])
        disc.assert_called_once()


if __name__ == "__main__":
    unittest.main()
