import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from kelvincal.argyll.profile_pipeline import (
    FIT_ERROR_WARN_THRESHOLD,
    PROFILE_TYPE_CLUT,
    PROFILE_TYPE_MATRIX,
    PROFILE_TYPE_SHAPER,
    PROFILE_TYPES,
    ProfileConfig,
    colprof_command,
    evaluate_fit,
    parse_fit_error,
    targen_layout,
)

# Real colprof -v tail on a QD-OLED: the same .ti3 fits cleanly with -a s and badly with -a m.
GOOD_FIT_OUTPUT = """\
colprof -v -qh -as -D KelvinCal DP-1 (2026-11-17) -O out.icc base
...
Profile check complete, peak err = 1.234567, avg err = 0.720000, RMS = 0.840000
"""
BAD_FIT_OUTPUT = """\
Profile check complete, peak err = 52.100000, avg err = 31.800000, RMS = 35.400000
"""
DOTS_FIT_OUTPUT = """\
Profile check complete, errors(CIEDE2000): max. = 2.500000, avg. = 1.250000, RMS = 1.500000
"""


def _read_ti1_rgb(path: Path) -> list[tuple[float, float, float]]:
    """Reads the RGB columns of the first data table of a .ti1 file."""
    rows: list[tuple[float, float, float]] = []
    in_data = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("BEGIN_DATA") and not line.startswith("BEGIN_DATA_FORMAT"):
            in_data = True
            continue
        if line.startswith("END_DATA") and not line.startswith("END_DATA_FORMAT"):
            break
        if in_data and line.strip():
            parts = line.split()
            rows.append((float(parts[1]), float(parts[2]), float(parts[3])))
    return rows


class TestTargenLayout(unittest.TestCase):
    def test_fixed_share_leaves_spread_budget(self) -> None:
        for count in (50, 100, 175, 400, 875):
            _single, gray, multi = targen_layout(count)
            fixed = gray + multi**3
            self.assertLessEqual(fixed, count, f"fixed patches exceed budget at {count}")
        _single, gray, multi = targen_layout(175)
        self.assertEqual((gray, multi), (35, 3))

    @unittest.skipUnless(shutil.which("targen"), "ArgyllCMS targen not installed")
    def test_real_targen_run_has_spread_patches(self) -> None:
        count = 175
        single, gray, multi = targen_layout(count)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "t"
            subprocess.run(
                ["targen", "-d", "3", "-G", "-e", "4", "-B", "1",
                 "-s", str(single), "-g", str(gray), "-m", str(multi), "-f", str(count), str(base)],
                check=True, capture_output=True, text=True,
            )
            rows = _read_ti1_rgb(base.with_suffix(".ti1"))

        grid = {round(100 * i / (multi - 1), 3) for i in range(multi)}
        spread = [
            r for r in rows
            if not (r[0] == r[1] == r[2]) and not all(round(c, 3) in grid for c in r)
        ]
        # Old layout (-g 52 -m 5) left only ~6 spread patches at 175; require a substantial share now.
        self.assertGreaterEqual(len(spread), count * 0.4)


class TestProfileTypes(unittest.TestCase):
    def test_three_types_in_ui_order(self) -> None:
        self.assertEqual(PROFILE_TYPES, ("X", "s", "m"))
        self.assertEqual((PROFILE_TYPE_CLUT, PROFILE_TYPE_SHAPER, PROFILE_TYPE_MATRIX), ("X", "s", "m"))

    def test_default_is_clut(self) -> None:
        self.assertEqual(ProfileConfig(monitor_name="DP-1").profile_type, PROFILE_TYPE_CLUT)

    def test_colprof_command_passes_type_and_verbose(self) -> None:
        for code in PROFILE_TYPES:
            config = ProfileConfig(monitor_name="DP-1", profile_type=code, profile_quality="h")
            argv = colprof_command(config, Path("/tmp/out.icc"), Path("/tmp/base"), "2026-11-17_10-00")
            self.assertEqual(argv[0], "colprof")
            # -v is required for the fit summary that evaluate_fit parses.
            self.assertIn("-v", argv)
            self.assertIn(f"-a{code}", argv)
            self.assertIn("-qh", argv)
            self.assertEqual(argv[-1], "/tmp/base")
            self.assertEqual(argv[argv.index("-O") + 1], "/tmp/out.icc")


class TestFitErrorParsing(unittest.TestCase):
    def test_parses_peak_err_line(self) -> None:
        fit = parse_fit_error(GOOD_FIT_OUTPUT)
        self.assertIsNotNone(fit)
        assert fit is not None
        self.assertAlmostEqual(fit.peak, 1.234567)
        self.assertAlmostEqual(fit.avg, 0.72)
        self.assertAlmostEqual(fit.rms, 0.84)

    def test_parses_max_avg_spelling(self) -> None:
        fit = parse_fit_error(DOTS_FIT_OUTPUT)
        assert fit is not None
        self.assertAlmostEqual(fit.avg, 1.25)

    def test_uses_last_summary_when_repeated(self) -> None:
        fit = parse_fit_error(BAD_FIT_OUTPUT + GOOD_FIT_OUTPUT)
        assert fit is not None
        self.assertAlmostEqual(fit.avg, 0.72)

    def test_returns_none_without_summary(self) -> None:
        self.assertIsNone(parse_fit_error("colprof: wrote out.icc\n"))
        self.assertIsNone(parse_fit_error(""))


class TestEvaluateFit(unittest.TestCase):
    def test_no_warning_below_threshold(self) -> None:
        statuses: list[str] = []
        fit, warning = evaluate_fit(GOOD_FIT_OUTPUT, statuses.append)
        self.assertIsNotNone(fit)
        self.assertIsNone(warning)
        self.assertEqual(statuses, [])

    def test_warns_above_threshold(self) -> None:
        statuses: list[str] = []
        fit, warning = evaluate_fit(BAD_FIT_OUTPUT, statuses.append)
        assert fit is not None and warning is not None
        self.assertAlmostEqual(fit.avg, 31.8)
        self.assertIn("31.80", warning)
        self.assertIn(f"{FIT_ERROR_WARN_THRESHOLD:.1f}", warning)
        self.assertEqual(statuses, [warning])

    def test_threshold_boundary_is_not_a_warning(self) -> None:
        at_limit = f"Profile check complete, peak err = 4.0, avg err = {FIT_ERROR_WARN_THRESHOLD}, RMS = 3.5"
        self.assertIsNone(evaluate_fit(at_limit)[1])

    def test_no_summary_means_no_warning(self) -> None:
        self.assertEqual(evaluate_fit("no fit line here"), (None, None))


if __name__ == "__main__":
    unittest.main()
