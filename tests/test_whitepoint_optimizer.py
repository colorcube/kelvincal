"""Phase 1b controller: ends close to the target (Δu′v′) and reports the state that is actually applied."""

from __future__ import annotations

import random
import unittest

from kcal_core.models import ColorMeasurement
from kcal_ddc.whitepoint_optimizer import WhitepointOptimizer

# primaries (xy) of a P3-like WLED panel, native white well above D65
PRIMARIES = ((0.6792, 0.3146), (0.2789, 0.6507), (0.1533, 0.0401))
NATIVE_Y = (0.215, 0.70, 0.105)        # luminance share per channel at gain 100 → bluish native white


class Panel:
    def __init__(self, noise: float = 0.0) -> None:
        self.state = (80, 100, 100, 100)
        self.noise = noise
        self.rng = random.Random(1)

    def apply(self, b: int, r: int, g: int, bl: int) -> None:
        self.state = (b, r, g, bl)

    def measure(self) -> ColorMeasurement:
        b, *gains = self.state
        X = Y = Z = 0.0
        for (x, y), share, gain in zip(PRIMARIES, NATIVE_Y, gains):
            lum = 3.0 * b * share * (gain / 100.0) ** 2.2      # gamma-like gain response
            X += x / y * lum
            Y += lum
            Z += (1 - x - y) / y * lum
        n = 1 + self.rng.gauss(0, self.noise) if self.noise else 1
        return ColorMeasurement((255, 255, 255), X * n, Y, Z)


class WhitepointOptimizerTest(unittest.TestCase):
    def run_panel(self, panel: Panel):  # noqa: ANN201
        applied: list[tuple[int, int, int, int]] = []

        def apply(*p: int) -> None:
            applied.append(p)
            panel.apply(*p)

        opt = WhitepointOptimizer(target_luminance_cdm2=140.0)
        res = opt.run(80, (100, 100, 100), apply, panel.measure)
        return opt, res, applied

    def test_refinement_reaches_fine_tolerance(self) -> None:
        opt, res, applied = self.run_panel(Panel())
        # one gain step moves this panel by ~0.001–0.002 Δu′v′; the closest combination must be chosen
        self.assertLessEqual(opt.uv_error(res.final_measurement), 0.0008)
        self.assertEqual(opt.uv_error(res.final_measurement),
                         min(opt.uv_error(m) for m in res.history if abs(m.Y - 140.0) <= 1.5))
        self.assertLess(abs(res.final_measurement.Y - 140.0), 4.0)
        self.assertEqual(applied[-1], (res.brightness, res.red_gain, res.green_gain, res.blue_gain))
        self.assertEqual(max(res.red_gain, res.green_gain, res.blue_gain), 100)

    def test_reported_state_is_applied_and_measured(self) -> None:
        panel = Panel(noise=0.0005)
        opt, res, applied = self.run_panel(panel)
        self.assertEqual(panel.state, (res.brightness, res.red_gain, res.green_gain, res.blue_gain))
        self.assertIn(res.final_measurement, res.history)
        self.assertLessEqual(len(res.history), opt.max_iterations + 18 * opt.refine_rounds)

    def test_no_oscillation_between_measured_states(self) -> None:
        # one brightness step (~2.7 cd/m²) is wider than the tolerance band (46 ↔ 47): the loop must not ping-pong
        panel = Panel()
        applied: list[tuple[int, int, int, int]] = []

        def apply(*p: int) -> None:
            applied.append(p)
            panel.apply(*p)

        opt = WhitepointOptimizer(target_luminance_cdm2=130.0, luminance_tolerance_cdm2=0.5)
        res = opt.run(80, (100, 100, 100), apply, panel.measure)
        measured = applied[:len(res.history)]
        self.assertEqual(len(measured), len(set(measured)))
        self.assertEqual(panel.state, (res.brightness, res.red_gain, res.green_gain, res.blue_gain))


if __name__ == "__main__":
    unittest.main()
