"""Qt-free calibration workflow shared by the GUI and the CLI.

The controller runs Phase 1a (contrast search), Phase 1b (whitepoint/luminance regulation) and
Phase 2+3 (dispread + colprof) for one display. It never touches Qt directly: the patch window is
reached through the `PatchDisplay` protocol and progress is reported to a `CalibrationObserver`.
Both may be implemented with thread-safe Qt bridges (see `kcal_gui.workers`), so the controller
can run in a worker thread while the GUI stays responsive.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable, Protocol

from kcal_argyll.profile_inspector import ProfileInspection, inspect_profile
from kcal_argyll.profile_pipeline import (
    CalibrationPipeline,
    PipelineCancelled,
    ProfileConfig,
    StagedProfile,
)
from kcal_argyll.spotread_session import SpotreadSession
from kcal_core.compositor.base import CompositorBackend
from kcal_core.i18n import translate
from kcal_core.models import D65_X, D65_Y, ColorMeasurement, ContrastStepResult, DisplayInfo
from kcal_ddc.contrast_optimizer import (
    ContrastOptimizationConfig,
    ContrastOptimizationResult,
    ContrastOptimizer,
)
from kcal_ddc.ddc_client import DDCClient
from kcal_ddc.whitepoint_optimizer import WhitepointOptimizationResult, WhitepointOptimizer


PHASE_CONTRAST = "1a"
PHASE_WHITEPOINT = "1b"
PHASE_MEASURE = "2"
PHASE_PROFILE = "3"


class CalibrationCancelled(Exception):
    """Raised inside the workflow when the user cancelled the run."""


class CancelToken:
    """Thread-safe cancel/pause flag checked by the workflow before every measurement."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._running = threading.Event()
        self._running.set()

    def cancel(self) -> None:
        self._cancelled.set()
        self._running.set()  # wake up a paused workflow so it can terminate

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    def checkpoint(self) -> None:
        """Blocks while paused; raises CalibrationCancelled once cancelled."""
        self._running.wait()
        if self._cancelled.is_set():
            raise CalibrationCancelled()


class PatchDisplay(Protocol):
    """Fullscreen patch output on the target display."""

    def wait_for_placement(self, prompt: str, cancel: CancelToken) -> bool:
        """Shows the alignment crosshair; returns False if the user aborted.

        The first line of `prompt` is the instruction, further lines are shown as details."""

    def show_patch(self, rgb: tuple[int, int, int], status: str, progress: float | None = None) -> None:
        """Displays `rgb` and returns once the patch has been rendered. `progress` is 0..1 if known."""

    def close(self) -> None:
        """Hides the patch window."""


class CalibrationObserver:
    """Receives workflow progress. All methods are no-ops by default; may be called from any thread."""

    def status(self, message: str) -> None:
        pass

    def phase_started(self, phase: str) -> None:
        pass

    def phase_finished(self, phase: str) -> None:
        pass

    def progress(self, phase: str, current: int, total: int) -> None:
        pass

    def contrast_step(self, step: ContrastStepResult) -> None:
        pass

    def whitepoint_reading(
        self, measurement: ColorMeasurement, ddc: tuple[int, int, int, int]
    ) -> None:
        pass

    def patch_measured(self, rgb: tuple[int, int, int], index: int, total: int) -> None:
        pass


@dataclass
class ProfilingResult:
    """Outcome of Phase 2+3: staged profile (already active in the compositor) plus restore information."""

    staged: StagedProfile
    inspection: ProfileInspection
    previous_icc_path: str
    previous_source: str


@dataclass
class FullCalibrationResult:
    contrast: ContrastOptimizationResult
    whitepoint: WhitepointOptimizationResult
    profiling: ProfilingResult


# Patch window settle time after a colour change before the sensor is triggered.
PATCH_SETTLE_S = 0.05


class CalibrationController:
    """Runs the calibration phases for a single display."""

    def __init__(
        self,
        display: DisplayInfo,
        compositor: CompositorBackend,
        patch_display: PatchDisplay,
        observer: CalibrationObserver | None = None,
        cancel: CancelToken | None = None,
        ddc_client: DDCClient | None = None,
        ccss_path: str | None = None,
        sensor_factory: Callable[[str | None], SpotreadSession] | None = None,
    ) -> None:
        self.display = display
        self.compositor = compositor
        self.patch_display = patch_display
        self.observer = observer or CalibrationObserver()
        self.cancel = cancel or CancelToken()
        self.ddc = ddc_client or DDCClient()
        self.ccss_path = ccss_path
        # Factory for the spot-measurement session (overridable for tests/simulation).
        self.sensor_factory = sensor_factory or (lambda ccss: SpotreadSession(ccss_path=ccss))

    # ------------------------------------------------------------------ helpers

    def _require_ddc(self) -> int:
        if self.display.i2c_bus is None:
            raise RuntimeError(
                translate(
                    "Controller",
                    "{connector} has no DDC/CI (I²C) bus; hardware phases are unavailable.",
                ).format(connector=self.display.connector)
            )
        return self.display.i2c_bus

    def _wait_for_placement(self) -> None:
        prompt = translate("Controller", "Place the sensor in the centre of the crosshair")
        details = [self.display.connector, self.display.model,
                   translate("Controller", "ColorGuard active")]
        prompt += "\n" + " · ".join(d for d in details if d)
        if not self.patch_display.wait_for_placement(prompt, self.cancel):
            self.cancel.cancel()
        self.cancel.checkpoint()

    def _measure(
        self, sensor: SpotreadSession, rgb: tuple[int, int, int], status: str
    ) -> ColorMeasurement:
        self.cancel.checkpoint()
        self.patch_display.show_patch(rgb, status)
        time.sleep(PATCH_SETTLE_S)
        return sensor.measure_rgb(rgb)

    def _initial_hw(self) -> tuple[int, int, int, int, int]:
        d = self.display.ddc
        return (
            d.brightness if d.brightness is not None else 50,
            d.contrast if d.contrast is not None else 50,
            d.red_gain if d.red_gain is not None else 100,
            d.green_gain if d.green_gain is not None else 100,
            d.blue_gain if d.blue_gain is not None else 100,
        )

    def _restore_hw(self, values: tuple[int, int, int, int, int]) -> None:
        bus = self.display.i2c_bus
        if bus is None:
            return
        b, c, r, g, bl = values
        try:
            self.ddc.set_vcp_values(bus, {"10": b, "12": c, "16": r, "18": g, "1A": bl})
            self.observer.status(
                translate("Controller", "Original DDC values restored.")
            )
        except Exception as exc:  # noqa: BLE001
            self.observer.status(
                translate("Controller", "Could not restore DDC values: {exc}").format(exc=exc)
            )

    # ------------------------------------------------------------------ phases (inside guard + sensor)

    def _contrast(
        self, sensor: SpotreadSession, config: ContrastOptimizationConfig
    ) -> ContrastOptimizationResult:
        bus = self._require_ddc()
        self.observer.phase_started(PHASE_CONTRAST)
        self.observer.status(
            translate(
                "Controller",
                "Phase 1a: binary contrast search on {display_label} [{min_contrast}..{max_contrast}]...",
            ).format(
                display_label=self.display.display_label,
                min_contrast=config.min_contrast,
                max_contrast=config.max_contrast,
            )
        )
        status = f"Phase 1a · {self.display.connector}"
        res = ContrastOptimizer(config).run(
            set_contrast_fn=lambda k: self.ddc.set_contrast(bus, k),
            measure_patch_fn=lambda rgb: self._measure(sensor, rgb, status),
            on_step=self.observer.contrast_step,
        )
        self.display.ddc.contrast = res.optimal_contrast
        self.observer.status(
            translate(
                "Controller",
                "✓ Optimal contrast: {optimal_contrast}% ({peak_luminance_cdm2:.1f} cd/m²)",
            ).format(
                optimal_contrast=res.optimal_contrast,
                peak_luminance_cdm2=res.peak_luminance_cdm2,
            )
        )
        self.observer.phase_finished(PHASE_CONTRAST)
        return res

    def _whitepoint(
        self,
        sensor: SpotreadSession,
        target_luminance: float,
        whitepoint_xy: tuple[float, float] | None = None,
    ) -> WhitepointOptimizationResult:
        target_x, target_y = whitepoint_xy or (D65_X, D65_Y)
        bus = self._require_ddc()
        self.observer.phase_started(PHASE_WHITEPOINT)
        self.observer.status(
            translate(
                "Controller",
                "Phase 1b: whitepoint (x={x:.4f}, y={y:.4f}) & luminance regulation ({target_luminance:.0f} cd/m²)...",
            ).format(x=target_x, y=target_y, target_luminance=target_luminance)
        )
        status = f"Phase 1b · {self.display.connector}"
        current: list[int] = []

        def apply(b: int, r: int, g: int, bl: int) -> None:
            current[:] = [b, r, g, bl]
            self.ddc.set_vcp_values(bus, {"10": b, "16": r, "18": g, "1A": bl})

        def measure_white() -> ColorMeasurement:
            m = self._measure(sensor, (255, 255, 255), status)
            self.observer.whitepoint_reading(m, tuple(current))  # type: ignore[arg-type]
            return m

        initial_b, _c, initial_r, initial_g, initial_bl = self._initial_hw()
        res = WhitepointOptimizer(
            target_luminance_cdm2=target_luminance, target_x=target_x, target_y=target_y
        ).run(
            initial_brightness=initial_b,
            initial_gains=(initial_r, initial_g, initial_bl),
            apply_ddc_fn=apply,
            measure_white_fn=measure_white,
        )
        ddc = self.display.ddc
        ddc.brightness, ddc.red_gain, ddc.green_gain, ddc.blue_gain = (
            res.brightness, res.red_gain, res.green_gain, res.blue_gain,
        )
        fm = res.final_measurement
        self.observer.status(
            translate(
                "Controller",
                "✓ Whitepoint regulated: brightness {brightness}%, RGB ({red_gain}, {green_gain}, {blue_gain}), {Y:.1f} cd/m², {cct_kelvin:.0f} K",
            ).format(
                brightness=res.brightness,
                red_gain=res.red_gain,
                green_gain=res.green_gain,
                blue_gain=res.blue_gain,
                Y=fm.Y,
                cct_kelvin=fm.cct_kelvin,
            )
        )
        self.observer.phase_finished(PHASE_WHITEPOINT)
        return res

    def _profiling(self, guard, config: ProfileConfig) -> ProfilingResult:  # noqa: ANN001
        if self.ccss_path and not config.ccss_path:
            config.ccss_path = self.ccss_path
        self.observer.phase_started(PHASE_MEASURE)
        connector = self.display.connector

        def on_patch(rgb: tuple[int, int, int], index: int, total: int) -> None:
            self.cancel.checkpoint()
            if total:
                status = translate("Controller", "Phase 2 · Patch {index}/{total} ({percent} %)").format(
                    index=index, total=total, percent=round(index * 100 / total))
            else:
                status = f"Phase 2 · {connector}"
            self.patch_display.show_patch(rgb, status, index / total if total else None)
            self.observer.patch_measured(rgb, index, total)
            self.observer.progress(PHASE_MEASURE, index, total)

        def on_measurement_finished() -> None:
            self.patch_display.close()
            self.observer.phase_finished(PHASE_MEASURE)
            self.observer.phase_started(PHASE_PROFILE)

        try:
            staged = CalibrationPipeline(config).generate_staged_profile(
                update_patch_fn=on_patch,
                on_status_fn=self.observer.status,
                cancel_check=lambda: self.cancel.cancelled,
                on_measurement_finished=on_measurement_finished,
            )
        except PipelineCancelled as exc:
            raise CalibrationCancelled() from exc
        self.patch_display.close()
        try:
            self.compositor.apply_output_profile(
                connector=connector,
                icc_profile_path=str(staged.staged_icc_path),
                color_profile_source="ICC",
                brightness=None,
            )
            guard.keep_new_profile = True
            inspection = inspect_profile(
                staged.staged_icc_path, ti3_path=staged.ti3_path, target_gamma=config.gamma
            )
        except Exception:
            staged.cleanup()
            raise
        self.observer.phase_finished(PHASE_PROFILE)
        return ProfilingResult(
            staged=staged,
            inspection=inspection,
            previous_icc_path=guard.previous_icc_path,
            previous_source=guard.previous_source,
        )

    # ------------------------------------------------------------------ public entry points

    def run_contrast(self, config: ContrastOptimizationConfig) -> ContrastOptimizationResult:
        self._require_ddc()
        initial = self._initial_hw()
        try:
            self._wait_for_placement()
            with self.compositor.calibration_guard(self.display.connector):
                with self.sensor_factory(self.ccss_path) as sensor:
                    return self._contrast(sensor, config)
        except BaseException:
            self._restore_hw(initial)
            raise
        finally:
            self.patch_display.close()

    def run_whitepoint(
        self, target_luminance: float, whitepoint_xy: tuple[float, float] | None = None
    ) -> WhitepointOptimizationResult:
        self._require_ddc()
        initial = self._initial_hw()
        try:
            self._wait_for_placement()
            with self.compositor.calibration_guard(self.display.connector):
                with self.sensor_factory(self.ccss_path) as sensor:
                    return self._whitepoint(sensor, target_luminance, whitepoint_xy)
        except BaseException:
            self._restore_hw(initial)
            raise
        finally:
            self.patch_display.close()

    def run_profiling(self, config: ProfileConfig) -> ProfilingResult:
        try:
            self._wait_for_placement()
            with self.compositor.calibration_guard(self.display.connector) as guard:
                return self._profiling(guard, config)
        finally:
            self.patch_display.close()

    def run_full(
        self,
        contrast_config: ContrastOptimizationConfig,
        target_luminance: float,
        profile_config: ProfileConfig,
        whitepoint_xy: tuple[float, float] | None = None,
    ) -> FullCalibrationResult:
        """Phase 1a → 1b → 2 → 3 under a single ColorGuard. DDC values are restored if 1a/1b fail."""
        self._require_ddc()
        initial = self._initial_hw()
        try:
            self._wait_for_placement()
            with self.compositor.calibration_guard(self.display.connector) as guard:
                try:
                    # spotread must release the instrument before dispread opens it.
                    with self.sensor_factory(self.ccss_path) as sensor:
                        contrast = self._contrast(sensor, contrast_config)
                        whitepoint = self._whitepoint(sensor, target_luminance, whitepoint_xy)
                except BaseException:
                    self._restore_hw(initial)
                    raise
                profiling = self._profiling(guard, profile_config)
            return FullCalibrationResult(contrast=contrast, whitepoint=whitepoint, profiling=profiling)
        finally:
            self.patch_display.close()
