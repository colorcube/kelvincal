import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from kcal_argyll.profile_pipeline import targen_layout


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


if __name__ == "__main__":
    unittest.main()
