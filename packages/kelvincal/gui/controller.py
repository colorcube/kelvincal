"""Qt-free calibration workflow shared by the GUI and the CLI.

The controller runs Phase 1a (contrast search), Phase 1b (whitepoint/luminance regulation) and
Phase 2+3 (dispread + colprof) for one display. It never touches Qt directly: the patch window is
reached through the `PatchDisplay` protocol and progress is reported to a `CalibrationObserver`.
Both may be implemented with thread-safe Qt bridges (see `kelvincal.gui.workers`), so the controller
can run in a worker thread while the GUI stays responsive.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import time
from typing import Callable, Protocol

from kelvincal.argyll.profile_inspector import ProfileInspection, inspect_profile
from kelvincal.argyll.profile_pipeline import (
    CalibrationPipeline,
    PipelineCancelled,
    ProfileConfig,
    StagedProfile,
)
from kelvincal.argyll.instruments import display_type_text
from kelvincal.argyll.spotread_session import DEFAULT_DISPLAY_TYPE, SpotreadSession
from kelvincal.argyll.ti3_check import MeasurementCheck, Ti3Data, Ti3Patch, check_measurements, parse_ti3, replace_xyz
from kelvincal.core import recovery
from kelvincal.core.compositor.base import CompositorBackend
from kelvincal.core.i18n import translate
from kelvincal.core.models import D65_X, D65_Y, ColorMeasurement, ContrastStepResult, DisplayInfo
from kelvincal.core.profile_meta import write_profile_meta
from kelvincal.core.verification import VerificationResult, evaluate, test_patches
from kelvincal.ddc.contrast_optimizer import (
    ContrastOptimizationConfig,
    ContrastOptimizationResult,
    ContrastOptimizer,
)
from kelvincal.ddc.ddc_client import DDCClient
from kelvincal.ddc.whitepoint_optimizer import WhitepointOptimizationResult, WhitepointOptimizer


PHASE_CONTRAST = "1a"
PHASE_WHITEPOINT = "1b"
PHASE_MEASURE = "2"
PHASE_PROFILE = "3"
PHASE_VERIFY = "verify"


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
        self, measurement: ColorMeasurement, ddc: tuple[int, int, int, int],
        target_xy: tuple[float, float] = (D65_X, D65_Y),
    ) -> None:
        pass

    def patch_measured(self, rgb: tuple[int, int, int], index: int, total: int) -> None:
        pass

    def batch_item_started(self, index: int, total: int, label: str) -> None:
        """Batch run: target `index` (1-based) of `total` begins."""

    def batch_item_finished(self, result: BatchItemResult) -> None:
        """Batch run: a target is done (successfully or with `result.error`)."""


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


@dataclass
class BatchItem:
    """One target of a batch run."""

    key: str                       # stored in the profile sidecar (target key)
    label: str
    target_luminance: float
    whitepoint_xy: tuple[float, float] | None
    profile_config: ProfileConfig
    whitepoint_label: str = ""     # for the sidecar ("D65", …)
    white_offset: tuple[float, float] = (0.0, 0.0)   # visual offset already contained in whitepoint_xy (sidecar)


@dataclass
class BatchItemResult:
    item: BatchItem
    ddc: tuple[int, int, int, int, int] | None = None    # hardware state the profile belongs to
    white: ColorMeasurement | None = None                 # 1b final measurement
    profile_path: Path | None = None
    inspection: ProfileInspection | None = None
    verification: VerificationResult | None = None
    error: str = ""
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.error and self.profile_path is not None


# Patch window settle time after a colour change before the sensor is triggered.
PATCH_SETTLE_S = 0.05
# Panel settle time after a DDC gain change before white is measured again.
WHITE_SETTLE_S = 1.0

REVIEW_REMEASURE, REVIEW_ACCEPT, REVIEW_CANCEL = "remeasure", "accept", "cancel"
MAX_REVIEW_ROUNDS = 3
FINAL_CHECK_ROUNDS = 3   # Phase 1c: contrast corrections after 1b at most
FINAL_CHECK_STEP = 2     # contrast step (%) when 1c finds clipping


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
        display_type: str = DEFAULT_DISPLAY_TYPE,
        display_type_label: str = "",
        reviewer: Callable[[MeasurementCheck, int], str] | None = None,
    ) -> None:
        self.display = display
        self.compositor = compositor
        self.patch_display = patch_display
        self.observer = observer or CalibrationObserver()
        self.cancel = cancel or CancelToken()
        self.ddc = ddc_client or DDCClient()
        self.ccss_path = ccss_path
        # instrument measurement mode (spotread/dispread -y, "" = none) and its name for reports
        self.display_type = display_type
        self.display_type_label = display_type_label
        # Factory for the spot-measurement session (overridable for tests/simulation).
        self.sensor_factory = sensor_factory or (
            lambda ccss: SpotreadSession(display_type=self.display_type, ccss_path=ccss,
                                         cancel_check=lambda: self.cancel.cancelled))
        # Decides what to do with implausible patches: REVIEW_REMEASURE / REVIEW_ACCEPT / REVIEW_CANCEL.
        # Without a reviewer (CLI) outliers are only reported.
        self.reviewer = reviewer

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
            d = self.display.ddc
            d.brightness, d.contrast, d.red_gain, d.green_gain, d.blue_gain = values
            self.observer.status(
                translate("Controller", "Original DDC values restored.")
            )
        except Exception as exc:  # noqa: BLE001
            self.observer.status(
                translate("Controller", "Could not restore DDC values: {exc}").format(exc=exc)
            )

    def _sync_compositor_brightness(self) -> None:
        """Hands the final DDC brightness to the compositor, so it does not restore its own value later."""
        brightness = self.display.ddc.brightness
        if brightness is None or self.display.i2c_bus is None:
            return
        try:
            if self.compositor.sync_brightness({self.display.connector: brightness}):
                self.observer.status(translate(
                    "Controller", "Compositor brightness of {connector} set to {brightness} % (= DDC).").format(
                    connector=self.display.connector, brightness=brightness))
        except Exception as exc:  # noqa: BLE001
            self.observer.status(translate(
                "Controller", "Could not set the compositor brightness: {exc}").format(exc=exc))

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
            self.observer.whitepoint_reading(m, tuple(current), (target_x, target_y))  # type: ignore[arg-type]
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

    def _final_check(
        self,
        sensor: SpotreadSession,
        config: ContrastOptimizationConfig,
        target_luminance: float,
        whitepoint_xy: tuple[float, float] | None,
        result: WhitepointOptimizationResult,
    ) -> WhitepointOptimizationResult:
        """Phase 1c: clipping check (near-white vs. white) with the final contrast, gains and brightness.

        1a searched the contrast with the RGB gains as they were before 1b; raising a gain or a digitally
        implemented brightness can make a channel clip afterwards. If so, the contrast is lowered one step
        and 1b re-regulates whitepoint and luminance (at most FINAL_CHECK_ROUNDS times).
        """
        bus = self._require_ddc()
        contrast = self.display.ddc.contrast
        if contrast is None:
            return result
        status = f"Phase 1c · {self.display.connector}"
        optimizer = ContrastOptimizer(config)
        for _round in range(FINAL_CHECK_ROUNDS):
            step = optimizer.evaluate_contrast(
                contrast,
                set_contrast_fn=lambda k: self.ddc.set_contrast(bus, k),
                measure_patch_fn=lambda rgb: self._measure(sensor, rgb, status),
            )
            if not step.clipped:
                self.observer.status(translate(
                    "Controller", "✓ Phase 1c: no clipping with the final settings (contrast {contrast}, "
                    "brightness {brightness}, RGB {r}/{g}/{b}).").format(
                    contrast=contrast, brightness=result.brightness, r=result.red_gain, g=result.green_gain,
                    b=result.blue_gain))
                return result
            lowered = contrast - FINAL_CHECK_STEP
            if lowered < config.min_contrast:
                self.observer.status(translate(
                    "Controller", "⚠ Phase 1c: clipping at contrast {contrast} ({reason}); cannot lower further."
                ).format(contrast=contrast, reason=step.reason))
                return result
            self.observer.status(translate(
                "Controller", "Phase 1c: clipping at contrast {contrast} ({reason}) – lowering to {lowered} and "
                "re-regulating whitepoint/luminance.").format(contrast=contrast, reason=step.reason, lowered=lowered))
            contrast = lowered
            self.ddc.set_contrast(bus, contrast)
            self.display.ddc.contrast = contrast
            result = self._whitepoint(sensor, target_luminance, whitepoint_xy)
        self.observer.status(translate("Controller", "⚠ Phase 1c: still clipping after {n} corrections.").format(
            n=FINAL_CHECK_ROUNDS))
        return result

    def _review_measurements(self, ti3_path: Path) -> None:
        """Checks the dispread data for outliers (mockup 1i) and re-measures them on request."""
        text = ti3_path.read_text(encoding="latin-1")
        for attempt in range(MAX_REVIEW_ROUNDS):
            data = parse_ti3(text)
            check = check_measurements(data)
            if check.ok:
                if attempt:
                    self.observer.status(translate("Controller", "Re-measured patches are plausible now."))
                return
            self.observer.status(translate(
                "Controller", "Plausibility check: {count} of {total} patches deviate (ΔE00 > {threshold})."
            ).format(count=len(check.outliers), total=len(data.patches), threshold=check.threshold))
            decision = self.reviewer(check, attempt) if self.reviewer else REVIEW_ACCEPT
            if decision == REVIEW_CANCEL:
                self.cancel.cancel()
                raise PipelineCancelled()
            if decision != REVIEW_REMEASURE:
                self.observer.status(translate("Controller", "Outliers kept; computing the profile anyway."))
                return
            text = replace_xyz(text, self._remeasure(data, [o.patch for o in check.outliers]))
            ti3_path.write_text(text, encoding="latin-1")
        self.observer.status(translate("Controller", "Patches still deviate after re-measuring; continuing."))

    def _remeasure(self, data: Ti3Data, patches: list[Ti3Patch]) -> dict[str, tuple[float, float, float]]:
        """Measures `patches` again with spotread and returns XYZ on the scale of the .ti3 file."""
        scale = 100.0 / data.white_luminance if data.normalised and data.white_luminance else 1.0
        result: dict[str, tuple[float, float, float]] = {}
        with self.sensor_factory(self.ccss_path) as sensor:
            for n, patch in enumerate(patches, start=1):
                rgb = tuple(round(v * 255 / 100) for v in patch.rgb)
                status = translate("Controller", "Re-measuring patch {id} ({n}/{total})").format(
                    id=patch.sample_id, n=n, total=len(patches))
                self.observer.status(status)
                m = self._measure(sensor, rgb, status)  # type: ignore[arg-type]
                result[patch.sample_id] = (m.X * scale, m.Y * scale, m.Z * scale)
        return result

    def _profiling(self, guard, config: ProfileConfig) -> ProfilingResult:  # noqa: ANN001
        if self.ccss_path and not config.ccss_path:
            config.ccss_path = self.ccss_path
        config.display_type = self.display_type
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
                review_measurements=self._review_measurements,
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
                recovery.note_ddc(self.display.connector, self.display.i2c_bus, initial)
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
                recovery.note_ddc(self.display.connector, self.display.i2c_bus, initial)
                with self.sensor_factory(self.ccss_path) as sensor:
                    res = self._whitepoint(sensor, target_luminance, whitepoint_xy)
                    return self._final_check(sensor, ContrastOptimizationConfig(), target_luminance,
                                             whitepoint_xy, res)
        except BaseException:
            self._restore_hw(initial)
            raise
        finally:
            self.patch_display.close()
            self._sync_compositor_brightness()

    def run_spot_check(self, raw: bool = False) -> dict[str, object]:
        """Measures white and black in the current state. Without `raw` whatever is active (ICC profile)
        is measured; with `raw` the display runs under ColorGuard (uncalibrated sRGB = hardware state only)."""
        from contextlib import nullcontext

        try:
            self._wait_for_placement()
            guard = self.compositor.calibration_guard(self.display.connector) if raw else nullcontext()
            with guard, self.sensor_factory(self.ccss_path) as sensor:
                status = translate("Controller", "Diagnostics · {connector}").format(connector=self.display.connector)
                white = self._measure(sensor, (255, 255, 255), status)
                black = self._measure(sensor, (0, 0, 0), status)
        finally:
            self.patch_display.close()
        return {
            "white_cdm2": round(white.Y, 2),
            "white_xyz": [round(v, 3) for v in (white.X, white.Y, white.Z)],
            "white_xy": [round(v, 4) for v in white.xy],
            "white_cct_k": round(white.cct_kelvin),
            "white_duv_d65": round(white.delta_uv_to_d65(), 4),
            "black_cdm2": round(black.Y, 4),
            "contrast": round(white.Y / black.Y) if black.Y > 0 else None,
            "spectral_correction": self.ccss_path or "",
            "display_type": self.display_type,
            "raw": raw,
        }

    def run_white_offset(self, start_gains: tuple[int, int, int], final_gains: tuple[int, int, int]
                         ) -> tuple[ColorMeasurement, ColorMeasurement]:
        """Visual whitepoint matching: measures white with the gains found by eye (`final_gains`) and with
        the calibrated ones (`start_gains`) under ColorGuard; the display keeps `final_gains` afterwards.
        Returns (start, final)."""
        bus = self._require_ddc()
        status = translate("Controller", "Visual whitepoint · {connector}").format(connector=self.display.connector)
        try:
            self._wait_for_placement()
            with self.compositor.calibration_guard(self.display.connector), \
                    self.sensor_factory(self.ccss_path) as sensor:
                self.ddc.set_vcp_values(bus, dict(zip(("16", "18", "1A"), final_gains)))
                time.sleep(WHITE_SETTLE_S)
                final = self._measure(sensor, (255, 255, 255), status)
                self.ddc.set_vcp_values(bus, dict(zip(("16", "18", "1A"), start_gains)))
                time.sleep(WHITE_SETTLE_S)
                start = self._measure(sensor, (255, 255, 255), status)
        finally:
            try:
                self.ddc.set_vcp_values(bus, dict(zip(("16", "18", "1A"), final_gains)))
            finally:
                self.patch_display.close()
        d = self.display.ddc
        d.red_gain, d.green_gain, d.blue_gain = final_gains
        return start, final

    def run_ccss(self, instrument: int, output: Path, technology: str = "u") -> Path:
        """Own colorimeter correction for this display, measured with spectrometer port `instrument`
        under ColorGuard (hardware state only). The prompts of the instrument are answered in the patch window."""
        from kelvincal.argyll.ccss_maker import make_ccss
        from kelvincal.argyll.dispread_runner import PROMPT_CALIBRATE

        details = " · ".join(d for d in (self.display.connector, self.display.model) if d)
        prompts = {
            PROMPT_CALIBRATE: translate(
                "Controller", "Calibrate the spectrometer: put it on its calibration tile (or cap it), then press Space"),
        }
        place = translate("Controller", "Place the spectrometer in the centre of the crosshair, then press Space")

        def on_prompt(kind: str, _text: str) -> bool:
            self.observer.status(prompts.get(kind, place))
            ok = self.patch_display.wait_for_placement(f"{prompts.get(kind, place)}\n{details}", self.cancel)
            if not ok:
                self.cancel.cancel()
            return ok

        def on_patch(rgb: tuple[int, int, int], index: int, total: int) -> None:
            self.cancel.checkpoint()
            total = max(total, index)   # dispread shows extra patches with a spectrometer (black first)
            status = translate("Controller", "Spectral correction · Patch {index}/{total}").format(
                index=index, total=total)
            self.patch_display.show_patch(rgb, status, index / total)
            self.observer.patch_measured(rgb, index, total)

        label = self.display.model or self.display.edid_identifier or self.display.connector
        try:
            with self.compositor.calibration_guard(self.display.connector):
                self.observer.phase_started(PHASE_MEASURE)
                path = make_ccss(instrument, output, label, on_patch, on_prompt, technology,
                                 on_status_fn=self.observer.status, cancel_check=lambda: self.cancel.cancelled)
                self.observer.phase_finished(PHASE_MEASURE)
                return path
        except PipelineCancelled as exc:
            raise CalibrationCancelled() from exc
        finally:
            self.patch_display.close()

    def _verify(self, sensor: SpotreadSession, target_xy: tuple[float, float], profile_label: str
                ) -> VerificationResult:
        """Measures the sRGB test patches with whatever profile is active and evaluates them."""
        patches = test_patches()
        total = len(patches) + 2
        self.observer.phase_started(PHASE_VERIFY)

        def measure(rgb: tuple[int, int, int], index: int, name: str) -> tuple[float, float, float]:
            status = translate("Controller", "Verification · {name} ({index}/{total})").format(
                name=name, index=index, total=total)
            self.patch_display.show_patch(rgb, status, index / total)
            time.sleep(PATCH_SETTLE_S)
            self.cancel.checkpoint()
            m = sensor.measure_rgb(rgb)
            self.observer.patch_measured(rgb, index, total)
            self.observer.progress(PHASE_VERIFY, index, total)
            return (m.X, m.Y, m.Z)

        white = measure((255, 255, 255), 1, translate("Verification", "White"))
        black = measure((0, 0, 0), 2, translate("Verification", "Black"))
        measured = [measure(p.rgb, i, p.display_name) for i, p in enumerate(patches, start=3)]
        self.patch_display.close()
        result = evaluate(patches, measured, white, black, target_xy, profile_label,
                          f"{self.display.model} ({self.display.connector})")
        result.ddc = self._live_ddc()
        result.correction = self.ccss_path or ""
        result.display_type = display_type_text(self.display_type, self.display_type_label)
        self.observer.status(translate(
            "Controller", "Verification: mean ΔE00 {mean}, max ΔE00 {max} ({name}).").format(
            mean=f"{result.mean:.2f}", max=f"{result.maximum.delta_e:.2f}" if result.maximum else "–",
            name=result.maximum.patch.display_name if result.maximum else "–"))
        self.observer.phase_finished(PHASE_VERIFY)
        return result

    def _live_ddc(self) -> tuple[int, int, int, int, int] | None:
        """Hardware state read from the display (for the verification's cause analysis), None if unknown."""
        if self.display.i2c_bus is None:
            return None
        try:
            s = self.ddc.read_state(self.display.i2c_bus)
        except Exception:  # noqa: BLE001 - informational only
            return None
        values = (s.brightness, s.contrast, s.red_gain, s.green_gain, s.blue_gain)
        return None if any(v is None for v in values) else values  # type: ignore[return-value]

    def run_verification(
        self, target_xy: tuple[float, float] = (D65_X, D65_Y), profile_label: str = "",
        white_offset: tuple[float, float] = (0.0, 0.0),
    ) -> VerificationResult:
        """Measures the sRGB test patches with the currently active profile (no ColorGuard: the profile
        under test must stay active) and evaluates them against their sRGB expectation."""
        try:
            self._wait_for_placement()
            with self.sensor_factory(self.ccss_path) as sensor:
                result = self._verify(sensor, target_xy, profile_label)
            result.white_offset = white_offset
            return result
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
                recovery.note_ddc(self.display.connector, self.display.i2c_bus, initial)
                try:
                    # spotread must release the instrument before dispread opens it.
                    with self.sensor_factory(self.ccss_path) as sensor:
                        contrast = self._contrast(sensor, contrast_config)
                        whitepoint = self._whitepoint(sensor, target_luminance, whitepoint_xy)
                        whitepoint = self._final_check(sensor, contrast_config, target_luminance,
                                                       whitepoint_xy, whitepoint)
                        contrast.optimal_contrast = self.display.ddc.contrast or contrast.optimal_contrast
                except BaseException:
                    self._restore_hw(initial)
                    raise
                profiling = self._profiling(guard, profile_config)
            return FullCalibrationResult(contrast=contrast, whitepoint=whitepoint, profiling=profiling)
        finally:
            self.patch_display.close()
            self._sync_compositor_brightness()

    def run_batch(
        self,
        items: list[BatchItem],
        contrast_config: ContrastOptimizationConfig,
        verify: bool = True,
    ) -> list[BatchItemResult]:
        """Calibrates several targets one after another without user interaction.

        The sensor is placed once. Phase 1a runs once (its contrast is the starting point of every
        target; 1c lowers it where needed), then per target 1b → 1c → 2 → 3 → optional verification
        with the new profile → save profile + sidecar. Outliers are re-measured automatically. A failing
        target is recorded and skipped; cancelling stops the batch. At the end the display gets back
        its previous profile and DDC values: the profiles are meant to be combined into presets.
        """
        self._require_ddc()
        initial = self._initial_hw()
        results: list[BatchItemResult] = []
        reviewer, self.reviewer = self.reviewer, (lambda _check, _attempt: REVIEW_REMEASURE)
        bus = self._require_ddc()
        base_contrast: int | None = None
        try:
            self._wait_for_placement()
            for index, item in enumerate(items, start=1):
                self.cancel.checkpoint()
                self.observer.batch_item_started(index, len(items), item.label)
                self.observer.status(translate("Controller", "Batch {index}/{total}: {label}").format(
                    index=index, total=len(items), label=item.label))
                res = BatchItemResult(item)
                started = time.monotonic()
                try:
                    with self.compositor.calibration_guard(self.display.connector) as guard:
                        recovery.note_ddc(self.display.connector, bus, self._initial_hw())
                        with self.sensor_factory(self.ccss_path) as sensor:
                            if base_contrast is None:
                                base_contrast = self._contrast(sensor, contrast_config).optimal_contrast
                            else:
                                self.ddc.set_contrast(bus, base_contrast)
                                self.display.ddc.contrast = base_contrast
                            wp = self._whitepoint(sensor, item.target_luminance, item.whitepoint_xy)
                            wp = self._final_check(sensor, contrast_config, item.target_luminance,
                                                   item.whitepoint_xy, wp)
                        res.white = wp.final_measurement
                        res.ddc = (wp.brightness, self.display.ddc.contrast or base_contrast, wp.red_gain,
                                   wp.green_gain, wp.blue_gain)
                        profiling = self._profiling(guard, item.profile_config)
                        guard.keep_new_profile = False   # back to the previous profile after this target
                        res.inspection = profiling.inspection
                        staged = profiling.staged
                        try:
                            if verify:
                                with self.sensor_factory(self.ccss_path) as sensor:
                                    res.verification = self._verify(
                                        sensor, item.whitepoint_xy or (D65_X, D65_Y),
                                        staged.suggested_output_path.name)
                                    res.verification.white_offset = item.white_offset
                            res.profile_path = staged.save_to()
                        finally:
                            staged.cleanup()
                    write_profile_meta(res.profile_path, res.ddc, self.display.connector,
                                       self.display.edid_hash, item.key, item.target_luminance,
                                       item.whitepoint_label, item.whitepoint_xy, item.white_offset,
                                       self.ccss_path, self.display_type, self.display_type_label)
                    self.observer.status(translate("Controller", "✓ Batch {index}/{total}: {label} → {file}").format(
                        index=index, total=len(items), label=item.label, file=res.profile_path.name))
                except CalibrationCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001 - one failing target must not stop the batch
                    if self.cancel.cancelled:
                        raise CalibrationCancelled() from exc
                    res.error = str(exc) or type(exc).__name__
                    self.observer.status(translate("Controller", "⚠ Batch {index}/{total}: {label} failed: {error}")
                                         .format(index=index, total=len(items), label=item.label, error=res.error))
                    self.patch_display.close()
                res.seconds = time.monotonic() - started
                results.append(res)
                self.observer.batch_item_finished(res)
            return results
        finally:
            self.reviewer = reviewer
            self.patch_display.close()
            self._restore_hw(initial)
            self._sync_compositor_brightness()
