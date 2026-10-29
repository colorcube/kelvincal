"""Tests for the Qt-free CalibrationController with a simulated panel, sensor and compositor."""

from __future__ import annotations

import unittest

from kcal_core.compositor.base import CompositorBackend, CompositorOutputState
from kcal_core.models import ColorMeasurement, D65_X, D65_Y, DDCState, DisplayInfo
from kcal_ddc.contrast_optimizer import ContrastOptimizationConfig
from kcal_gui.controller import (
    CalibrationCancelled,
    CalibrationController,
    CalibrationObserver,
    CancelToken,
)


class FakePanel:
    """Panel that clips above contrast 72 and whose white chromaticity follows the RGB gains."""

    def __init__(self) -> None:
        self.vcp = {"10": 50, "12": 50, "16": 100, "18": 100, "1A": 100}

    def measure(self, rgb: tuple[int, int, int]) -> ColorMeasurement:
        level = rgb[0] / 255.0
        gain = self.vcp["12"] / 72.0
        Y = 2.8 * self.vcp["10"] * min(1.0, level * gain) ** 2.2
        x = D65_X + (self.vcp["16"] - 92) * 0.0004
        y = D65_Y
        X = x / y * Y
        Z = (1.0 - x - y) / y * Y
        return ColorMeasurement(rgb=rgb, X=X, Y=Y, Z=Z)


class FakeDDC:
    def __init__(self, panel: FakePanel) -> None:
        self.panel = panel

    def set_contrast(self, bus: int, k: int, settle: bool = True) -> None:
        self.panel.vcp["12"] = k

    def set_vcp_values(self, bus: int, values: dict[str, int]) -> None:
        self.panel.vcp.update(values)


class FakeSensor:
    def __init__(self, panel: FakePanel, on_measure=None) -> None:  # noqa: ANN001
        self.panel = panel
        self.on_measure = on_measure
        self.count = 0

    def __enter__(self) -> FakeSensor:
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        pass

    def measure_rgb(self, rgb: tuple[int, int, int]) -> ColorMeasurement:
        self.count += 1
        if self.on_measure:
            self.on_measure(self.count)
        return self.panel.measure(rgb)


class FakeCompositor(CompositorBackend):
    def __init__(self) -> None:
        self.state = CompositorOutputState(connector="DP-1", color_profile_source="ICC", icc_profile_path="/old.icc")
        self.calls: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return "fake"

    def get_outputs(self) -> dict[str, CompositorOutputState]:
        return {"DP-1": self.state}

    def apply_output_profile(self, connector, icc_profile_path="", color_profile_source="ICC",  # noqa: ANN001
                             brightness=None, disable_hdr_wcg=False) -> None:  # noqa: ANN001
        self.calls.append((color_profile_source, icc_profile_path))

    def apply_batch(self, updates) -> None:  # noqa: ANN001
        pass

    def calibration_guard(self, connector: str, settle_seconds: float = 0.4):  # noqa: ANN201
        return super().calibration_guard(connector, settle_seconds=0.0)


class FakePatchDisplay:
    def __init__(self, confirm: bool = True) -> None:
        self.confirm = confirm
        self.patches: list[tuple[int, int, int]] = []
        self.closed = 0

    def wait_for_placement(self, prompt: str, cancel: CancelToken) -> bool:
        return self.confirm

    def show_patch(self, rgb: tuple[int, int, int], status: str, progress: float | None = None) -> None:
        self.patches.append(rgb)

    def close(self) -> None:
        self.closed += 1


class RecordingObserver(CalibrationObserver):
    def __init__(self) -> None:
        self.phases: list[str] = []
        self.steps = 0

    def phase_started(self, phase: str) -> None:
        self.phases.append(phase)

    def contrast_step(self, step) -> None:  # noqa: ANN001
        self.steps += 1


def _display() -> DisplayInfo:
    return DisplayInfo(
        connector="DP-1", drm_card_connector="card1-DP-1", edid_hash="abc", i2c_bus=7,
        ddc=DDCState(brightness=50, contrast=50, red_gain=100, green_gain=100, blue_gain=100),
    )


class TestCalibrationController(unittest.TestCase):
    def _controller(self, panel: FakePanel, sensor: FakeSensor, cancel: CancelToken | None = None,
                    patch: FakePatchDisplay | None = None):  # noqa: ANN202
        comp = FakeCompositor()
        observer = RecordingObserver()
        ctl = CalibrationController(
            display=_display(), compositor=comp, patch_display=patch or FakePatchDisplay(),
            observer=observer, cancel=cancel, ddc_client=FakeDDC(panel),  # type: ignore[arg-type]
            sensor_factory=lambda _ccss: sensor,  # type: ignore[return-value]
        )
        return ctl, comp, observer

    def test_contrast_phase_runs_and_restores_colour_state(self) -> None:
        panel = FakePanel()
        ctl, comp, observer = self._controller(panel, FakeSensor(panel))
        res = ctl.run_contrast(ContrastOptimizationConfig(min_contrast=40, max_contrast=90))
        self.assertIn(res.optimal_contrast, (71, 72))
        self.assertEqual(observer.phases, ["1a"])
        self.assertGreater(observer.steps, 4)
        # Guard: switched to sRGB for measuring, then restored the previous ICC profile.
        self.assertEqual(comp.calls[0], ("sRGB", ""))
        self.assertEqual(comp.calls[-1], ("ICC", "/old.icc"))

    def test_cancel_restores_original_ddc_values(self) -> None:
        panel = FakePanel()
        cancel = CancelToken()
        sensor = FakeSensor(panel, on_measure=lambda n: cancel.cancel() if n == 3 else None)
        ctl, comp, _ = self._controller(panel, sensor, cancel=cancel)
        with self.assertRaises(CalibrationCancelled):
            ctl.run_contrast(ContrastOptimizationConfig(min_contrast=40, max_contrast=90))
        self.assertEqual(panel.vcp["12"], 50)  # original contrast restored
        self.assertEqual(sensor.count, 3)       # no further measurement after cancel
        self.assertEqual(comp.calls[-1], ("ICC", "/old.icc"))

    def test_placement_abort_cancels_before_any_measurement(self) -> None:
        panel = FakePanel()
        sensor = FakeSensor(panel)
        ctl, _, _ = self._controller(panel, sensor, patch=FakePatchDisplay(confirm=False))
        with self.assertRaises(CalibrationCancelled):
            ctl.run_whitepoint(120.0)
        self.assertEqual(sensor.count, 0)

    def test_whitepoint_phase_converges(self) -> None:
        panel = FakePanel()
        ctl, _, _ = self._controller(panel, FakeSensor(panel))
        res = ctl.run_whitepoint(120.0)
        self.assertLess(res.red_gain, 100)
        self.assertAlmostEqual(res.final_measurement.Y, 120.0, delta=5.0)

    def test_pause_blocks_until_resume(self) -> None:
        import threading
        cancel = CancelToken()
        cancel.pause()
        passed = threading.Event()
        t = threading.Thread(target=lambda: (cancel.checkpoint(), passed.set()))
        t.start()
        self.assertFalse(passed.wait(0.1))
        cancel.resume()
        self.assertTrue(passed.wait(1.0))
        t.join()


if __name__ == "__main__":
    unittest.main()
