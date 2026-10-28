"""Component 1/2 (Phase 1): Automated DDC whitepoint (RGB gain) and luminance (brightness) controller."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from kcal_core.models import ColorMeasurement, D65_X, D65_Y


@dataclass
class WhitepointOptimizationResult:
    """Result of the hardware whitepoint and luminance regulation loop."""

    brightness: int
    red_gain: int
    green_gain: int
    blue_gain: int
    final_measurement: ColorMeasurement
    iterations: int
    history: list[ColorMeasurement] = field(default_factory=list)


class WhitepointOptimizer:
    """Regulates DDC RGB gains (0x16/0x18/0x1A) to D65 and brightness (0x10) to target cd/m²."""

    def __init__(
        self,
        target_luminance_cdm2: float = 140.0,
        target_x: float = D65_X,
        target_y: float = D65_Y,
        max_gain: int = 100,
        min_gain: int = 50,
        max_iterations: int = 8,
        xy_tolerance: float = 0.0015,
        luminance_tolerance_cdm2: float = 1.5,
    ) -> None:
        self.target_luminance_cdm2 = target_luminance_cdm2
        self.target_x = target_x
        self.target_y = target_y
        self.max_gain = max_gain
        self.min_gain = min_gain
        self.max_iterations = max_iterations
        self.xy_tolerance = xy_tolerance
        self.luminance_tolerance_cdm2 = luminance_tolerance_cdm2

    def run(
        self,
        initial_brightness: int,
        initial_gains: tuple[int, int, int],
        apply_ddc_fn: Callable[[int, int, int, int], None],
        measure_white_fn: Callable[[], ColorMeasurement],
    ) -> WhitepointOptimizationResult:
        """Iteratively regulates RGB gains and brightness while keeping the dominant channel anchored at max_gain."""
        brightness = max(0, min(100, initial_brightness))
        r_gain, g_gain, b_gain = initial_gains
        history: list[ColorMeasurement] = []

        # Normalize initial gains so the highest channel starts at max_gain
        peak_g = max(r_gain, g_gain, b_gain, 1)
        scale_init = self.max_gain / float(peak_g)
        r_gain = min(self.max_gain, max(self.min_gain, round(r_gain * scale_init)))
        g_gain = min(self.max_gain, max(self.min_gain, round(g_gain * scale_init)))
        b_gain = min(self.max_gain, max(self.min_gain, round(b_gain * scale_init)))

        last_m: ColorMeasurement | None = None
        for _step in range(1, self.max_iterations + 1):
            apply_ddc_fn(brightness, r_gain, g_gain, b_gain)
            m = measure_white_fn()
            history.append(m)
            last_m = m

            cur_x, cur_y = m.xy
            err_x = self.target_x - cur_x
            err_y = self.target_y - cur_y
            err_lum = self.target_luminance_cdm2 - m.Y

            if (
                abs(err_x) <= self.xy_tolerance
                and abs(err_y) <= self.xy_tolerance
                and abs(err_lum) <= self.luminance_tolerance_cdm2
            ):
                break

            # 2-DoF tristimulus ratio control relative to Green (Y), then normalized to max_gain = 100
            cur_z = max(1.0 - cur_x - cur_y, 0.05)
            target_z = 1.0 - self.target_x - self.target_y

            target_x_over_y = self.target_x / self.target_y
            cur_x_over_y = max(cur_x / max(cur_y, 0.05), 0.05)

            target_z_over_y = target_z / self.target_y
            cur_z_over_y = max(cur_z / max(cur_y, 0.05), 0.05)

            kp = 0.60
            r_ratio = 1.0 + kp * ((target_x_over_y / cur_x_over_y) - 1.0)
            g_ratio = 1.0
            b_ratio = 1.0 + kp * ((target_z_over_y / cur_z_over_y) - 1.0)

            raw_r = r_gain * r_ratio
            raw_g = g_gain * g_ratio
            raw_b = b_gain * b_ratio

            prev_params = (brightness, r_gain, g_gain, b_gain)

            # Anchor highest channel at max_gain to prevent contrast loss
            max_raw = max(raw_r, raw_g, raw_b, 1e-6)
            norm = self.max_gain / max_raw
            r_gain = max(self.min_gain, min(self.max_gain, round(raw_r * norm)))
            g_gain = max(self.min_gain, min(self.max_gain, round(raw_g * norm)))
            b_gain = max(self.min_gain, min(self.max_gain, round(raw_b * norm)))

            # Proportional backlight brightness step (VCP 0x10)
            if m.Y > 1.0 and abs(err_lum) > self.luminance_tolerance_cdm2:
                slope = max(m.Y / max(brightness, 12), 1.8)
                step_adjust = round(0.85 * (err_lum / slope))
                if step_adjust == 0:
                    step_adjust = 1 if err_lum > 0 else -1
                step_adjust = max(-35, min(35, step_adjust))
                brightness = max(0, min(100, brightness + step_adjust))

            # Stop early if integer quantization (0..100) means no DDC register changed
            if (brightness, r_gain, g_gain, b_gain) == prev_params:
                break

        assert last_m is not None
        return WhitepointOptimizationResult(
            brightness=brightness,
            red_gain=r_gain,
            green_gain=g_gain,
            blue_gain=b_gain,
            final_measurement=last_m,
            iterations=len(history),
            history=history,
        )
