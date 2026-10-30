"""Own colorimeter correction (.ccss) for one display, measured with a spectrometer on that display.

The generic corrections (e.g. "WLED family") describe an average panel. Two displays with different
backlights/phosphors can measure identical with a colorimeter and still look different side by side. A
spectrometer (e.g. i1 Pro) measures the real spectra of white, red, green and blue; `ccxxmake -S` turns
them into a .ccss with which the colorimeter (i1 DisplayPro) measures this display like the spectrometer.

dispread measures the patches through KelvinCal's patch window (`dispread_runner`); ArgyllCMS'
`ccxxmake -f` then builds the .ccss from the spectral .ti3.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable

from kcal_argyll.dispread_runner import run_dispread
from kcal_core.i18n import translate

# White, red, green, blue at full drive (RGB in %, XYZ = sRGB approximation as dispread expects it)
CCSS_TI1 = """CTI1

DESCRIPTOR "Argyll Calibration Target chart information 1"
ORIGINATOR "KelvinCal"
APPROX_WHITE_POINT "95.106486 100.000000 108.844025"
COLOR_REP "RGB"

NUMBER_OF_FIELDS 7
BEGIN_DATA_FORMAT
SAMPLE_ID RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z
END_DATA_FORMAT

NUMBER_OF_SETS 4
BEGIN_DATA
1 100.0000 100.0000 100.0000 95.10649 100.0000 108.8440
2 100.0000 0.00000 0.00000 41.83017 22.05217 2.913230
3 0.00000 100.0000 0.00000 36.40521 71.80052 12.80184
4 0.00000 0.00000 100.0000 18.87111 8.147314 95.12896
END_DATA
"""
PATCH_COUNT = 4


def make_ccss(
    instrument: int,
    output: Path,
    display_name: str,
    update_patch_fn: Callable[[tuple[int, int, int], int, int], None],
    on_prompt: Callable[[str, str], bool],
    technology: str = "u",
    on_status_fn: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Path:
    """Measures the spectra with spectrometer port `instrument` and writes `output` (.ccss).

    The spectral measurement is kept next to it as `<output>.ti3` (for later analysis, e.g. other observers).
    `technology` is a `ccxxmake -t` code (u = unknown); it only labels the file.
    """
    for tool in ("dispread", "ccxxmake"):
        if not shutil.which(tool):
            raise RuntimeError(translate("Errors", "ArgyllCMS tool '{tool}' was not found in PATH.").format(tool=tool))
    staging = Path(tempfile.mkdtemp(prefix="kelvincal_ccss_"))
    try:
        base = staging / "ccss"
        base.with_suffix(".ti1").write_text(CCSS_TI1, encoding="utf-8")
        if on_status_fn:
            on_status_fn(translate("Pipeline", "Measuring the spectra of white, red, green and blue..."))
        # -H: high resolution spectrum (narrow LED/phosphor peaks), -s: keep the spectra in the .ti3
        # no -Y p: dispread asks for the calibration (tile/cap) first, then for placing the instrument
        run_dispread(base, ["-c", str(instrument), "-H", "-s"], PATCH_COUNT, update_patch_fn,
                     on_status_fn, cancel_check, on_prompt)
        ti3 = base.with_suffix(".ti3")
        output.parent.mkdir(parents=True, exist_ok=True)
        description = f"KelvinCal {display_name} ({datetime.now():%Y-%m-%d %H:%M})"
        proc = subprocess.run(
            ["ccxxmake", "-S", "-f", str(ti3), "-t", technology, "-I", display_name, "-E", description,
             str(output)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0 or not output.exists():
            raise RuntimeError(translate("Errors", "{tool} failed (exit code {code}):\n{output}").format(
                tool="ccxxmake", code=proc.returncode, output=proc.stdout + proc.stderr))
        shutil.copy2(ti3, output.with_suffix(".ti3"))
        return output
    finally:
        shutil.rmtree(staging, ignore_errors=True)
