"""Component 1/2 (Phase 1): Automated DDC whitepoint (RGB gain) and luminance (brightness) controller."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from kcal_core.models import ColorMeasurement, D65_X, D65_Y

Params = tuple[int, int, int, int]   # brightness, red, green, blue gain


def xy_to_uv(x: float, y: float) -> tuple[float, float]:
    d = -2.0 * x + 12.0 * y + 3.0
    return 4.0 * x / d, 9.0 * y / d


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
    """Regulates DDC RGB gains (0x16/0x18/0x1A) to D65 and brightness (0x10) to target cd/m².

    1. Control loop: ratio control of the gains (highest channel anchored at max_gain) plus a proportional
       brightness step, until the white is within `uv_tolerance` (Δu′v′) and `luminance_tolerance_cdm2`.
    2. Refinement: one gain step changes the white by roughly 0.0005–0.001 Δu′v′, so the loop can stop on
       either side of the target – two displays may then differ visibly (≈ 0.003). Neighbouring gain
       combinations (±1 per channel) are measured and the closest one is kept (hill climbing) until it is
       within `fine_uv_tolerance` or nothing improves.
    The returned DDC values are always the ones applied when `final_measurement` was taken, and they are
    applied again at the end.
    """

    def __init__(
        self,
        target_luminance_cdm2: float = 140.0,
        target_x: float = D65_X,
        target_y: float = D65_Y,
        max_gain: int = 100,
        min_gain: int = 50,
        max_iterations: int = 8,
        uv_tolerance: float = 0.0015,
        luminance_tolerance_cdm2: float = 1.5,
        fine_uv_tolerance: float = 0.0005,
        refine_rounds: int = 3,
    ) -> None:
        self.target_luminance_cdm2 = target_luminance_cdm2
        self.target_x = target_x
        self.target_y = target_y
        self.max_gain = max_gain
        self.min_gain = min_gain
        self.max_iterations = max_iterations
        self.uv_tolerance = uv_tolerance
        self.luminance_tolerance_cdm2 = luminance_tolerance_cdm2
        self.fine_uv_tolerance = fine_uv_tolerance
        self.refine_rounds = refine_rounds
        self.target_uv = xy_to_uv(target_x, target_y)

    def uv_error(self, m: ColorMeasurement) -> float:
        u, v = xy_to_uv(*m.xy)
        return ((u - self.target_uv[0]) ** 2 + (v - self.target_uv[1]) ** 2) ** 0.5

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

        measured: dict[Params, ColorMeasurement] = {}

        def measure(params: Params) -> ColorMeasurement:
            apply_ddc_fn(*params)
            m = measure_white_fn()
            history.append(m)
            measured[params] = m
            return m

        for _step in range(1, self.max_iterations + 1):
            m = measure((brightness, r_gain, g_gain, b_gain))

            cur_x, cur_y = m.xy
            err_lum = self.target_luminance_cdm2 - m.Y

            if self.uv_error(m) <= self.uv_tolerance and abs(err_lum) <= self.luminance_tolerance_cdm2:
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

            # Stop if integer quantization (0..100) leaves the registers unchanged or the loop would return to a
            # state it already measured (e.g. one brightness step is wider than the luminance tolerance: 32 ↔ 33)
            next_params = (brightness, r_gain, g_gain, b_gain)
            if next_params == prev_params or next_params in measured:
                break

        best = self._refine(self._best(measured), measured, measure)
        if history and measured[best] is not history[-1]:
            apply_ddc_fn(*best)          # the hardware must end in the state that was reported
        b, r, g, bl = best
        return WhitepointOptimizationResult(
            brightness=b,
            red_gain=r,
            green_gain=g,
            blue_gain=bl,
            final_measurement=measured[best],
            iterations=len(history),
            history=history,
        )

    def _score(self, m: ColorMeasurement) -> float:
        """Chromaticity first; luminance only counts once it leaves its tolerance."""
        lum_excess = max(0.0, abs(self.target_luminance_cdm2 - m.Y) - self.luminance_tolerance_cdm2)
        return self.uv_error(m) + 0.0005 * lum_excess

    def _best(self, measured: dict[Params, ColorMeasurement]) -> Params:
        return min(measured, key=lambda p: self._score(measured[p]))

    def _refine(self, start: Params, measured: dict[Params, ColorMeasurement],
                measure: Callable[[Params], ColorMeasurement]) -> Params:
        best = start
        for _round in range(self.refine_rounds):
            if self.uv_error(measured[best]) <= self.fine_uv_tolerance:
                break
            improved = False
            for moves in (1, 2):        # single-channel steps first, pairs only if they do not help
                for cand in self._neighbours(best, moves):
                    if cand not in measured:
                        measure(cand)
                new_best = self._best(measured)
                if new_best != best:
                    best, improved = new_best, True
                    break
            if not improved:
                break
        return best

    def _neighbours(self, params: Params, moves: int) -> list[Params]:
        """Gain combinations that differ by ±1 in `moves` channels; the highest gain stays (near) max_gain."""
        from itertools import combinations, product

        b, *gains = params
        result: list[Params] = []
        for channels in combinations(range(3), moves):
            for deltas in product((-1, 1), repeat=moves):
                g = list(gains)
                for ch, d in zip(channels, deltas):
                    g[ch] += d
                if all(self.min_gain <= v <= self.max_gain for v in g) and max(g) >= self.max_gain - 1:
                    result.append((b, g[0], g[1], g[2]))
        return result
