"""Post-calibration verification (mockup 1j): sRGB test patches shown with the profile active,
measured, and compared with their expected colour (CIEDE2000, relative to the measured white).

The patches are displayed like any application content, i.e. as sRGB that KWin colour-manages with
the active ICC profile – so the whole chain (profile + compositor) is verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import html
import math
import statistics

from kelvincal.core.color import Lab, delta_e2000, xyz_to_lab
from kelvincal.core.i18n import QT_TRANSLATE_NOOP, format_number, translate

# Approximate sRGB renderings of the 24 ColorChecker colours (common published values; here they only
# serve as realistic test colours – the reference is the sRGB definition, not the physical chart).
COLORCHECKER: tuple[tuple[str, tuple[int, int, int]], ...] = (
    (QT_TRANSLATE_NOOP("Verification", "Dark skin"), (115, 82, 68)),
    (QT_TRANSLATE_NOOP("Verification", "Light skin"), (194, 150, 130)),
    (QT_TRANSLATE_NOOP("Verification", "Blue sky"), (98, 122, 157)),
    (QT_TRANSLATE_NOOP("Verification", "Foliage"), (87, 108, 67)),
    (QT_TRANSLATE_NOOP("Verification", "Blue flower"), (133, 128, 177)),
    (QT_TRANSLATE_NOOP("Verification", "Bluish green"), (103, 189, 170)),
    (QT_TRANSLATE_NOOP("Verification", "Orange"), (214, 126, 44)),
    (QT_TRANSLATE_NOOP("Verification", "Purplish blue"), (80, 91, 166)),
    (QT_TRANSLATE_NOOP("Verification", "Moderate red"), (193, 90, 99)),
    (QT_TRANSLATE_NOOP("Verification", "Purple"), (94, 60, 108)),
    (QT_TRANSLATE_NOOP("Verification", "Yellow green"), (157, 188, 64)),
    (QT_TRANSLATE_NOOP("Verification", "Orange yellow"), (224, 163, 46)),
    (QT_TRANSLATE_NOOP("Verification", "Blue"), (56, 61, 150)),
    (QT_TRANSLATE_NOOP("Verification", "Green"), (70, 148, 73)),
    (QT_TRANSLATE_NOOP("Verification", "Red"), (175, 54, 60)),
    (QT_TRANSLATE_NOOP("Verification", "Yellow"), (231, 199, 31)),
    (QT_TRANSLATE_NOOP("Verification", "Magenta"), (187, 86, 149)),
    (QT_TRANSLATE_NOOP("Verification", "Cyan"), (8, 133, 161)),
    (QT_TRANSLATE_NOOP("Verification", "White 9.5"), (243, 243, 242)),
    (QT_TRANSLATE_NOOP("Verification", "Neutral 8"), (200, 200, 200)),
    (QT_TRANSLATE_NOOP("Verification", "Neutral 6.5"), (160, 160, 160)),
    (QT_TRANSLATE_NOOP("Verification", "Neutral 5"), (122, 122, 121)),
    (QT_TRANSLATE_NOOP("Verification", "Neutral 3.5"), (85, 85, 85)),
    (QT_TRANSLATE_NOOP("Verification", "Black 2"), (52, 52, 52)),
)
GRAY_LEVELS = (5, 10, 20, 30, 40, 50, 60, 70, 80, 90)  # % signal; white is measured as reference
PRIMARIES = (
    (QT_TRANSLATE_NOOP("Verification", "Red 100 %"), (255, 0, 0)),
    (QT_TRANSLATE_NOOP("Verification", "Green 100 %"), (0, 255, 0)),
    (QT_TRANSLATE_NOOP("Verification", "Blue 100 %"), (0, 0, 255)),
    (QT_TRANSLATE_NOOP("Verification", "Cyan 100 %"), (0, 255, 255)),
    (QT_TRANSLATE_NOOP("Verification", "Magenta 100 %"), (255, 0, 255)),
    (QT_TRANSLATE_NOOP("Verification", "Yellow 100 %"), (255, 255, 0)),
)

# Tolerances (recommended / nominal), in the spirit of common display verification reports
TOL_MEAN = (1.0, 1.5)
TOL_MAX = (3.0, 4.0)
TOL_GRAY_CHROMA = (1.0, 2.0)      # max a*b* cast of the gray patches (relative to the measured white)
TOL_WHITE_DUV = (0.003, 0.006)    # Δu′v′ of the measured white to the target whitepoint

SRGB_WHITE_XYZ = (0.95047, 1.0, 1.08883)


@dataclass(frozen=True)
class TestPatch:
    name: str               # untranslated source text (context "Verification") or "Gray 50 %"
    rgb: tuple[int, int, int]
    gray: bool = False

    @property
    def display_name(self) -> str:
        if not self.name:
            return translate("Verification", "Gray {level} %").format(level=round(self.rgb[0] * 100 / 255))
        return translate("Verification", self.name)


def test_patches() -> list[TestPatch]:
    neutrals = len(COLORCHECKER) - 6  # the last row of the chart is the gray scale
    patches = [TestPatch(name, rgb, gray=i >= neutrals) for i, (name, rgb) in enumerate(COLORCHECKER)]
    patches += [TestPatch("", (round(v * 2.55),) * 3, gray=True) for v in GRAY_LEVELS]
    patches += [TestPatch(name, rgb) for name, rgb in PRIMARIES]
    return patches


def srgb_to_xyz(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """IEC 61966-2-1 sRGB (8 bit) → XYZ with Y(white) = 1, D65."""
    def lin(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in rgb)
    return (0.4124 * r + 0.3576 * g + 0.1805 * b,
            0.2126 * r + 0.7152 * g + 0.0722 * b,
            0.0193 * r + 0.1192 * g + 0.9505 * b)


def xy_of(xyz: tuple[float, float, float]) -> tuple[float, float]:
    s = sum(xyz)
    return (xyz[0] / s, xyz[1] / s) if s > 0 else (0.0, 0.0)


def duv(xy1: tuple[float, float], xy2: tuple[float, float]) -> float:
    def uv(x: float, y: float) -> tuple[float, float]:
        d = -2 * x + 12 * y + 3
        return 4 * x / d, 9 * y / d

    (u1, v1), (u2, v2) = uv(*xy1), uv(*xy2)
    return math.hypot(u1 - u2, v1 - v2)


@dataclass
class PatchResult:
    patch: TestPatch
    measured_xyz: tuple[float, float, float]   # cd/m²
    expected_lab: Lab
    measured_lab: Lab
    delta_e: float

    @property
    def chroma(self) -> float:
        """Colour cast: distance in the a*b* plane between measured and expected (gray balance)."""
        return math.hypot(self.measured_lab[1] - self.expected_lab[1], self.measured_lab[2] - self.expected_lab[2])


@dataclass
class VerificationResult:
    patches: list[PatchResult]
    white_xyz: tuple[float, float, float]
    black_xyz: tuple[float, float, float]
    target_xy: tuple[float, float]
    profile_label: str = ""
    display_label: str = ""
    created: datetime = field(default_factory=datetime.now)
    ddc: tuple[int, int, int, int, int] | None = None   # live hardware state (B, C, R, G, B gain) while measuring
    correction: str = ""                                 # spectral correction (.ccss/.ccmx) of the instrument
    display_type: str = ""                               # instrument measurement mode, e.g. "LCD White LED IPS (-y e)"
    white_offset: tuple[float, float] = (0.0, 0.0)       # visual whitepoint offset contained in target_xy

    @property
    def mean(self) -> float:
        return statistics.fmean(p.delta_e for p in self.patches) if self.patches else 0.0

    @property
    def maximum(self) -> PatchResult | None:
        return max(self.patches, key=lambda p: p.delta_e, default=None)

    @property
    def gray(self) -> list[PatchResult]:
        return sorted((p for p in self.patches if p.patch.gray), key=lambda p: p.patch.rgb[0])

    @property
    def gray_chroma_max(self) -> float:
        return max((p.chroma for p in self.gray), default=0.0)

    @property
    def white_luminance(self) -> float:
        return self.white_xyz[1]

    @property
    def white_duv(self) -> float:
        return duv(xy_of(self.white_xyz), self.target_xy)

    @property
    def white_cct(self) -> float:
        """Correlated colour temperature of the measured white (McCamy's approximation)."""
        x, y = xy_of(self.white_xyz)
        n = (x - 0.3320) / (0.1858 - y)
        return 449 * n ** 3 + 3525 * n ** 2 + 6823.3 * n + 5520.33

    @property
    def contrast(self) -> float | None:
        return self.white_xyz[1] / self.black_xyz[1] if self.black_xyz[1] > 0 else None


def grade(value: float, tolerance: tuple[float, float]) -> str:
    """"ok" (≤ recommended), "warning" (≤ nominal) or "error"."""
    return "ok" if value <= tolerance[0] else "warning" if value <= tolerance[1] else "error"


def overall_grade(result: VerificationResult) -> str:
    """Worst grade of the ΔE and gray balance figures ("ok", "warning", "error")."""
    grades = [grade(result.mean, TOL_MEAN), grade(result.gray_chroma_max, TOL_GRAY_CHROMA)]
    if result.maximum is not None:
        grades.append(grade(result.maximum.delta_e, TOL_MAX))
    return "error" if "error" in grades else "warning" if "warning" in grades else "ok"


# Deviations from the profile that point to a display state the profile was not measured in.
LUMINANCE_DEVIATION = 0.10   # relative white luminance difference
WHITE_DUV_DEVIATION = 0.004  # Δu′v′ between measured and profiled white
_DDC_FIELDS = (QT_TRANSLATE_NOOP("Verification", "brightness"), QT_TRANSLATE_NOOP("Verification", "contrast"),
               QT_TRANSLATE_NOOP("Verification", "red gain"), QT_TRANSLATE_NOOP("Verification", "green gain"),
               QT_TRANSLATE_NOOP("Verification", "blue gain"))


def likely_causes(result: VerificationResult, profile_white_y: float | None = None,
                  profile_white_xy: tuple[float, float] | None = None,
                  profile_ddc: tuple[int, int, int, int, int] | None = None) -> list[str]:
    """Possible reasons why the display does not match the profile, most specific first.

    `profile_*` describe the state the profile was measured in (white from the profile, DDC values from
    its sidecar); every one of them is optional.
    """
    causes = []
    if profile_ddc is not None and result.ddc is not None and tuple(result.ddc) != tuple(profile_ddc):
        diffs = ", ".join(translate("Verification", "{field} {live} instead of {profile}").format(
            field=translate("Verification", name), live=live, profile=prof)
            for name, live, prof in zip(_DDC_FIELDS, result.ddc, profile_ddc) if live != prof)
        causes.append(translate(
            "Verification", "The display settings (DDC) differ from those the profile was measured with: "
            "{diffs}. Apply the preset again or switch the preview to this profile.").format(diffs=diffs))
    if profile_white_y and abs(result.white_luminance / profile_white_y - 1) > LUMINANCE_DEVIATION:
        causes.append(translate(
            "Verification", "White measures {live} cd/m², the profile was made at {profile} cd/m² – the "
            "brightness was changed (e.g. by the KWin brightness slider).").format(
            live=format_number(result.white_luminance), profile=format_number(profile_white_y)))
    if profile_white_xy is not None:
        shift = duv(xy_of(result.white_xyz), profile_white_xy)
        if shift > WHITE_DUV_DEVIATION:
            causes.append(translate(
                "Verification", "White has moved away from the profile's white (Δu′v′ {value}) – RGB gains or "
                "the display's colour mode were changed.").format(value=format_number(shift, 4)))
    if not causes:
        causes.append(translate(
            "Verification", "No changed display setting found. Check that the profile is active in KWin, that "
            "the sensor lay flat and did not move, and that the display had warmed up (about 30 min)."))
    return causes


def evaluate(
    patches: list[TestPatch],
    measured: list[tuple[float, float, float]],
    white_xyz: tuple[float, float, float],
    black_xyz: tuple[float, float, float],
    target_xy: tuple[float, float],
    profile_label: str = "",
    display_label: str = "",
) -> VerificationResult:
    """Compares measured XYZ (cd/m²) with the sRGB expectation, both relative to their own white."""
    results = []
    for patch, xyz in zip(patches, measured):
        expected = xyz_to_lab(srgb_to_xyz(patch.rgb), SRGB_WHITE_XYZ)
        actual = xyz_to_lab(xyz, white_xyz)
        results.append(PatchResult(patch, xyz, expected, actual, delta_e2000(expected, actual)))
    return VerificationResult(results, white_xyz, black_xyz, target_xy, profile_label, display_label)


def report_html(result: VerificationResult) -> str:
    """Self-contained HTML report (opens in any browser, prints to PDF)."""
    def fmt(v: float, d: int = 2) -> str:
        return format_number(v, d)

    colours = {"ok": "#1b8548", "warning": "#c45a00", "error": "#bf2a39"}

    def kpi(label: str, value: str, state: str) -> str:
        return (f'<td><div class="l">{html.escape(label)}</div>'
                f'<div class="v" style="color:{colours[state]}">{html.escape(value)}</div></td>')

    worst = result.maximum
    rows = []
    for i, p in enumerate(result.patches, start=1):
        r, g, b = p.patch.rgb
        state = grade(p.delta_e, (2.0, 3.0))
        el, ml = p.expected_lab, p.measured_lab
        rows.append(
            f"<tr><td>{i}</td><td>{html.escape(p.patch.display_name)}</td>"
            f'<td><span class="sw" style="background:rgb({r},{g},{b})"></span>{r} {g} {b}</td>'
            f"<td>{fmt(el[0], 1)} {fmt(el[1], 1)} {fmt(el[2], 1)}</td>"
            f"<td>{fmt(ml[0], 1)} {fmt(ml[1], 1)} {fmt(ml[2], 1)}</td>"
            f'<td style="color:{colours[state]}">{fmt(p.delta_e)}</td></tr>')
    title = translate("Verification", "KelvinCal verification report")
    labels = {
        "display": translate("Verification", "Display"),
        "profile": translate("Verification", "Profile"),
        "date": translate("Verification", "Date"),
        "mean": translate("Verification", "Mean ΔE00"),
        "max": translate("Verification", "Max ΔE00"),
        "gray": translate("Verification", "Gray balance (max Δa*b*)"),
        "white": translate("Verification", "Whitepoint Δu′v′"),
        "lum": translate("Verification", "White / black"),
        "patch": translate("Verification", "Patch"),
        "nominal": translate("Verification", "sRGB (8 bit)"),
        "expected": translate("Verification", "Lab expected"),
        "measured": translate("Verification", "Lab measured"),
        "target": translate("Verification", "Target whitepoint"),
        "offset": translate("Verification", "visual offset"),
        "correction": translate("Verification", "Spectral correction"),
        "mode": translate("Verification", "Measurement mode"),
        "none": translate("Verification", "none"),
        "note": translate("Verification", "Patches shown as sRGB with the profile active in the compositor; "
                                          "ΔE00 relative to the measured white. Green: recommended, orange: "
                                          "nominal tolerance."),
    }
    contrast = f" · {fmt(result.contrast, 0)}:1" if result.contrast else ""
    target = f"x {fmt(result.target_xy[0], 4)} · y {fmt(result.target_xy[1], 4)}"
    if result.white_offset != (0.0, 0.0):
        target += (f" ({labels['offset']} Δx {fmt(result.white_offset[0], 4)} · "
                   f"Δy {fmt(result.white_offset[1], 4)})")
    correction = result.correction.rsplit("/", 1)[-1] if result.correction else labels["none"]
    mode = f" · {labels['mode']}: {html.escape(result.display_type)}" if result.display_type else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:sans-serif;margin:24px;color:#232629}}table{{border-collapse:collapse}}
.k td{{padding:8px 18px 8px 0}}.l{{color:#6b7075;font-size:12px}}.v{{font-size:20px;font-weight:600}}
.p td,.p th{{padding:3px 10px;border-bottom:1px solid #ddd;text-align:left;font-size:13px}}
.sw{{display:inline-block;width:22px;height:12px;margin-right:6px;border:1px solid #999;vertical-align:middle}}
.meta{{color:#6b7075}}</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="meta">{labels['display']}: {html.escape(result.display_label)} · {labels['profile']}:
{html.escape(result.profile_label)} · {labels['date']}: {result.created:%Y-%m-%d %H:%M}<br>
{labels['target']}: {html.escape(target)} · {labels['correction']}: {html.escape(correction)}{mode}</p>
<table class="k"><tr>
{kpi(labels['mean'], fmt(result.mean), grade(result.mean, TOL_MEAN))}
{kpi(labels['max'], fmt(worst.delta_e) if worst else '–', grade(worst.delta_e, TOL_MAX) if worst else 'ok')}
{kpi(labels['gray'], fmt(result.gray_chroma_max), grade(result.gray_chroma_max, TOL_GRAY_CHROMA))}
{kpi(labels['white'], f"{fmt(result.white_cct, 0)} K · {fmt(result.white_duv, 4)}", grade(result.white_duv, TOL_WHITE_DUV))}
{kpi(labels['lum'], f"{fmt(result.white_luminance, 1)} / {fmt(result.black_xyz[1], 3)} cd/m²{contrast}", 'ok')}
</tr></table>
<p class="meta">{html.escape(labels['note'])}</p>
<table class="p"><tr><th>#</th><th>{labels['patch']}</th><th>{labels['nominal']}</th><th>{labels['expected']}</th>
<th>{labels['measured']}</th><th>ΔE00</th></tr>
{''.join(rows)}
</table></body></html>
"""
