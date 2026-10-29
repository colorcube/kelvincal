"""Measurement plausibility check (.ti3) and the re-measure loop of the controller."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from kcal_argyll.ti3_check import check_measurements, parse_ti3, replace_xyz
from kcal_core.models import ColorMeasurement, DisplayInfo
from kcal_gui.controller import (
    REVIEW_ACCEPT,
    REVIEW_CANCEL,
    REVIEW_REMEASURE,
    CalibrationController,
)

# simulated wide-gamut LCD: gamma 2.2 per channel, slight non-additivity in saturated reds
PRIMARIES = ((48.0, 23.0, 1.5), (31.0, 70.0, 9.0), (16.0, 7.0, 98.0))
BLACK = (0.08, 0.085, 0.12)
LUMINANCE = 140.0


def display_xyz(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """XYZ (white Y = 100 scale) of a 0..100 RGB patch."""
    t = [(v / 100) ** 2.2 for v in rgb]
    crosstalk = 0.03 * t[0] * (1 - t[2])  # systematic, smooth: must not be reported
    return tuple(BLACK[k] + sum(PRIMARIES[c][k] * t[c] for c in range(3)) * (1 - crosstalk) for k in range(3))


def build_ti3() -> str:
    patches: list[tuple[float, float, float]] = [(100, 100, 100), (0, 0, 0)]
    for c in range(3):
        for v in (12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100):
            rgb = [0.0, 0.0, 0.0]
            rgb[c] = v
            patches.append(tuple(rgb))
    patches += [(v, v, v) for v in range(5, 100, 5)]
    steps = (0, 33.3, 66.7, 100)
    patches += [(r, g, b) for r in steps for g in steps for b in steps]
    lines = [
        "CTI3", "", 'DESCRIPTOR "test"', f'LUMINANCE_XYZ_CDM2 "133.0 {LUMINANCE} 150.0"',
        'NORMALIZED_TO_Y_100 "YES"', "", "NUMBER_OF_FIELDS 7", "BEGIN_DATA_FORMAT",
        "SAMPLE_ID RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z", "END_DATA_FORMAT", "",
        f"NUMBER_OF_SETS {len(patches)}", "BEGIN_DATA",
    ]
    for i, rgb in enumerate(patches, start=1):
        x, y, z = display_xyz(rgb)
        lines.append(f"{i} {rgb[0]:.4f} {rgb[1]:.4f} {rgb[2]:.4f} {x:.5f} {y:.5f} {z:.5f}")
    lines.append("END_DATA")
    return "\n".join(lines) + "\n"


def popup(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    """A light-grey notification covering part of the measured area."""
    return tuple(0.65 * v + 0.35 * w for v, w in zip(xyz, (80.0, 84.0, 95.0)))


class Ti3CheckTest(unittest.TestCase):
    def test_clean_data_has_no_outliers(self) -> None:
        check = check_measurements(parse_ti3(build_ti3()))
        self.assertTrue(check.ok, [(o.patch.sample_id, o.delta_e) for o in check.outliers])
        self.assertLess(max(check.scores), 2.0)

    def test_popup_is_found(self) -> None:
        text = build_ti3()
        data = parse_ti3(text)
        victims = [data.patches[30], data.patches[60]]
        bad = replace_xyz(text, {p.sample_id: popup(p.xyz) for p in victims})
        check = check_measurements(parse_ti3(bad))
        self.assertEqual(sorted(o.patch.sample_id for o in check.outliers), sorted(p.sample_id for p in victims))

    def test_disturbed_primary_does_not_break_the_model(self) -> None:
        """The full-intensity primaries anchor the tone curves; a bad one must not flag the whole set."""
        text = build_ti3()
        data = parse_ti3(text)
        red = next(p for p in data.patches if p.rgb == (100.0, 0.0, 0.0))
        other = data.patches[50]
        bad = replace_xyz(text, {red.sample_id: tuple(v * 0.8 for v in red.xyz), other.sample_id: popup(other.xyz)})
        check = check_measurements(parse_ti3(bad))
        self.assertEqual(sorted(o.patch.sample_id for o in check.outliers), sorted([red.sample_id, other.sample_id]))

    def test_replace_keeps_everything_else(self) -> None:
        text = build_ti3()
        out = replace_xyz(text, {"3": (1.0, 2.0, 3.0)})
        self.assertEqual(len(out.splitlines()), len(text.splitlines()))
        patch = parse_ti3(out).patches[2]
        self.assertEqual(patch.xyz, (1.0, 2.0, 3.0))
        self.assertEqual(parse_ti3(out).keywords["NORMALIZED_TO_Y_100"], "YES")
        self.assertAlmostEqual(parse_ti3(out).white_luminance or 0, LUMINANCE)


class _Sensor:
    """spotread stand-in: measures the simulated display in absolute cd/m²."""

    def __init__(self) -> None:
        self.measured: list[tuple[int, int, int]] = []

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        pass

    def measure_rgb(self, rgb: tuple[int, int, int]) -> ColorMeasurement:
        self.measured.append(rgb)
        x, y, z = display_xyz(tuple(v * 100 / 255 for v in rgb))
        f = LUMINANCE / 100
        return ColorMeasurement(rgb, x * f, y * f, z * f)


class _Patch:
    def show_patch(self, rgb, status, progress=None) -> None:  # noqa: ANN001
        pass


class ReviewLoopTest(unittest.TestCase):
    def _run(self, decisions: list[str]) -> tuple[str, _Sensor, list[int], BaseException | None]:
        sensor = _Sensor()
        rounds: list[int] = []

        def reviewer(check, attempt: int) -> str:  # noqa: ANN001
            rounds.append(len(check.outliers))
            return decisions[min(attempt, len(decisions) - 1)]

        ctl = CalibrationController(
            display=DisplayInfo(connector="DP-1", drm_card_connector="c", edid_hash="x", i2c_bus=1),
            compositor=None,  # type: ignore[arg-type]
            patch_display=_Patch(),  # type: ignore[arg-type]
            sensor_factory=lambda _ccss: sensor,  # type: ignore[arg-type,return-value]
            reviewer=reviewer,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.ti3"
            text = build_ti3()
            data = parse_ti3(text)
            victim = data.patches[40]
            path.write_text(replace_xyz(text, {victim.sample_id: popup(victim.xyz)}), encoding="latin-1")
            error: BaseException | None = None
            try:
                ctl._review_measurements(path)
            except BaseException as exc:  # noqa: BLE001
                error = exc
            return path.read_text(encoding="latin-1"), sensor, rounds, error

    def test_remeasure_replaces_the_outlier(self) -> None:
        text, sensor, rounds, error = self._run([REVIEW_REMEASURE])
        self.assertIsNone(error)
        self.assertEqual(rounds, [1])                      # asked once, clean afterwards
        self.assertEqual(len(sensor.measured), 1)
        self.assertTrue(check_measurements(parse_ti3(text)).ok)

    def test_accept_keeps_the_data(self) -> None:
        text, sensor, rounds, error = self._run([REVIEW_ACCEPT])
        self.assertIsNone(error)
        self.assertEqual(sensor.measured, [])
        self.assertFalse(check_measurements(parse_ti3(text)).ok)

    def test_cancel_stops_the_pipeline(self) -> None:
        _text, _sensor, _rounds, error = self._run([REVIEW_CANCEL])
        self.assertEqual(type(error).__name__, "PipelineCancelled")


if __name__ == "__main__":
    unittest.main()
