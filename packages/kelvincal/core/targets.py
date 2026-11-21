"""Calibration targets ("Einsatzzweck") offered in the simple mode.

A target bundles luminance, whitepoint, reference tone curve and patch count. In the hardware DDC/CI
workflow (`ddc`), whitepoint and luminance are regulated in the display hardware (Phase 1b) and the tone
curve serves as the reference in the profile inspector. In the software workflow (`software`), 1D `vcgt`
calibration curves are measured via `dispcal` (Phase 1s) to calibrate both whitepoint and tone response.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from kelvincal.argyll.instruments import is_slow_sensor
from kelvincal.core.i18n import QT_TRANSLATE_NOOP, translate
from kelvincal.core.models import D65_X, D65_Y

SECONDS_PER_PATCH = 2.2           # dispread via Wayland patch hook with i1Display-class colorimeter
SLOW_SECONDS_PER_PATCH = 4.5      # slower colorimeters (e.g. Spyder family on dark patches)
HARDWARE_PHASES_SECONDS = 90      # Phase 1a + 1b (DDC contrast + whitepoint/luminance)
SOFTWARE_PHASE_SECONDS = 240      # Phase 1s (dispcal -ql ~112 patches across 4 passes, fast sensor)
SLOW_SOFTWARE_PHASE_SECONDS = 540 # Phase 1s (dispcal -ql on slower colorimeters)

WORKFLOW_DDC = "ddc"
WORKFLOW_SOFTWARE = "software"
WORKFLOW_PROFILE = "profile"
WORKFLOWS = (WORKFLOW_DDC, WORKFLOW_SOFTWARE, WORKFLOW_PROFILE)

PATCH_FAST = 79
PATCH_STANDARD = 175
PATCH_HIGH = 403

TONE_GAMMA = "gamma"
TONE_SRGB = "srgb"
TONE_BT1886 = "bt1886"
TONE_LSTAR = "lstar"


@dataclass(frozen=True)
class PatchPreset:
    key: str                   # "fast", "standard", "high", "custom"
    title: str                 # untranslated source text (context "Targets")
    patch_count: int | None    # None for "custom"
    description: str           # untranslated source text (context "Targets")

    @property
    def display_title(self) -> str:
        return translate("Targets", self.title)

    @property
    def display_description(self) -> str:
        return translate("Targets", self.description)


PATCH_PRESETS: tuple[PatchPreset, ...] = (
    PatchPreset(
        "fast",
        QT_TRANSLATE_NOOP("Targets", "Fast"),
        PATCH_FAST,
        QT_TRANSLATE_NOOP("Targets", "Gray ramp + primaries + 3×3×3 grid · quick check & slow sensors"),
    ),
    PatchPreset(
        "standard",
        QT_TRANSLATE_NOOP("Targets", "Standard"),
        PATCH_STANDARD,
        QT_TRANSLATE_NOOP("Targets", "Balanced grid + spread patches · recommended for most displays"),
    ),
    PatchPreset(
        "high",
        QT_TRANSLATE_NOOP("Targets", "High"),
        PATCH_HIGH,
        QT_TRANSLATE_NOOP("Targets", "Dense grid for LUT profiles · photography, softproof & video"),
    ),
    PatchPreset(
        "custom",
        QT_TRANSLATE_NOOP("Targets", "Custom"),
        None,
        QT_TRANSLATE_NOOP("Targets", "Free patch count (50–2000)"),
    ),
)


def preset_for_count(count: int) -> str:
    for p in PATCH_PRESETS:
        if p.patch_count == count:
            return p.key
    return "custom"


def parse_patch_arg(value: str | int) -> int:
    """Resolves a CLI/preset patch specification ('fast', 'standard', 'high', or integer 50..2000)."""
    if isinstance(value, int):
        return max(50, min(2000, value))
    text = str(value).strip().lower()
    for p in PATCH_PRESETS:
        if p.key == text and p.patch_count is not None:
            return p.patch_count
    count = int(text)
    if not 50 <= count <= 2000:
        raise ValueError(f"patch count must be 50..2000 or fast/standard/high, got {value!r}")
    return count


def estimate_duration_minutes(
    patch_count: int,
    workflow: str = WORKFLOW_DDC,
    instrument_name: str = "",
) -> int:
    """Estimated total runtime in minutes for the given patch count, workflow, and sensor."""
    slow = is_slow_sensor(instrument_name)
    sec_per_patch = SLOW_SECONDS_PER_PATCH if slow else SECONDS_PER_PATCH
    cal_sec = 0
    if workflow == WORKFLOW_DDC:
        cal_sec = HARDWARE_PHASES_SECONDS * (2 if slow else 1)
    elif workflow == WORKFLOW_SOFTWARE:
        cal_sec = SLOW_SOFTWARE_PHASE_SECONDS if slow else SOFTWARE_PHASE_SECONDS
    return max(1, round((patch_count * sec_per_patch + cal_sec) / 60))


@dataclass(frozen=True)
class CalibrationTarget:
    key: str
    title: str                 # untranslated source text (context "Targets")
    luminance: float           # cd/m²
    cct: int                   # whitepoint colour temperature; 6504 = exact D65
    tone_curve: str = TONE_GAMMA
    gamma: float = 2.2
    patch_count: int = PATCH_STANDARD
    allow_d50: bool = False    # offers a D65/D50 switch
    custom_luminance: bool = False

    @property
    def display_title(self) -> str:
        return translate("Targets", self.title)

    @property
    def is_d50(self) -> bool:
        return self.allow_d50 and self.cct == 5003

    @property
    def variant_key(self) -> str:
        """Key including the whitepoint variant ("photo", "photo_d50"): batch selection, CLI, file names."""
        return f"{self.key}_d50" if self.is_d50 else self.key

    @property
    def variant_title(self) -> str:
        """Translated title, with the whitepoint for the D50 variant (batch lists both variants)."""
        return f"{self.display_title} · D50" if self.is_d50 else self.display_title

    @property
    def whitepoint_xy(self) -> tuple[float, float]:
        return cct_to_xy(self.cct)

    @property
    def whitepoint_label(self) -> str:
        if self.cct == 6504:
            return "D65"
        if self.cct == 5003:
            return "D50"
        return f"{self.cct} K"

    @property
    def tone_label(self) -> str:
        gamma = _num(self.gamma)
        if self.tone_curve == TONE_SRGB:
            return translate("Targets", "sRGB curve")
        if self.tone_curve == TONE_BT1886:
            return f"BT.1886 γ {gamma}"
        if self.tone_curve == TONE_LSTAR:
            return translate("Targets", "L* curve")
        return f"γ {gamma}"

    @property
    def recommended_preset(self) -> str:
        if self.patch_count >= PATCH_HIGH:
            return "high"
        if self.patch_count <= PATCH_FAST:
            return "fast"
        return "standard"

    @property
    def recommended_preset_label(self) -> str:
        preset = next((p for p in PATCH_PRESETS if p.key == self.recommended_preset), PATCH_PRESETS[1])
        return f"{preset.display_title} ({self.patch_count})"

    def estimated_minutes(self, workflow: str = WORKFLOW_DDC, instrument_name: str = "") -> int:
        return estimate_duration_minutes(self.patch_count, workflow=workflow, instrument_name=instrument_name)

    def with_d50(self, enabled: bool) -> CalibrationTarget:
        return replace(self, cct=5003 if enabled else 6504)

    def with_luminance(self, luminance: float) -> CalibrationTarget:
        return replace(self, luminance=luminance)

    def with_patches(self, patch_count: int) -> CalibrationTarget:
        return replace(self, patch_count=patch_count)


def _num(value: float) -> str:
    try:
        from PySide6.QtCore import QLocale

        return QLocale().toString(value, "f", 1)
    except ImportError:  # pragma: no cover
        return f"{value:.1f}"


# CIE daylight illuminant (D65 / D50) chromaticity shifts (dx, dy) relative to CIE 1931 2° when integrated
# under alternative observers (computed via ArgyllCMS `spec2cie -i D65/D50 -o <observer>`).
_OBSERVER_D65_XY: dict[str, tuple[float, float]] = {
    "1931_2": (D65_X, D65_Y),
    "2015_2": (0.31345, 0.33080),
    "2015_10": (0.31379, 0.33127),
    "1964_10": (0.31382, 0.33100),
}
_OBSERVER_D50_XY: dict[str, tuple[float, float]] = {
    "1931_2": (0.34570, 0.35854),
    "2015_2": (0.34848, 0.36086),
    "2015_10": (0.34817, 0.35959),
    "1964_10": (0.34775, 0.35954),
}


def adapt_whitepoint_for_observer(
    whitepoint_xy: tuple[float, float] | None,
    observer: str | None,
) -> tuple[float, float] | None:
    """Translates a CIE 1931 2° target whitepoint (plus any visual offset) into the chosen observer's space."""
    if whitepoint_xy is None or not observer or observer == "1931_2" or observer not in _OBSERVER_D65_XY:
        return whitepoint_xy
    x, y = whitepoint_xy
    # Interpolate observer shift between D50 (x ≈ 0.3457) and D65 (x ≈ 0.3127) so visual offsets are preserved
    d65_1931 = _OBSERVER_D65_XY["1931_2"]
    d50_1931 = _OBSERVER_D50_XY["1931_2"]
    d65_obs = _OBSERVER_D65_XY[observer]
    d50_obs = _OBSERVER_D50_XY[observer]
    if abs(x - d50_1931[0]) < abs(x - d65_1931[0]):
        dx = d50_obs[0] - d50_1931[0]
        dy = d50_obs[1] - d50_1931[1]
    else:
        dx = d65_obs[0] - d65_1931[0]
        dy = d65_obs[1] - d65_1931[1]
    return (round(x + dx, 5), round(y + dy, 5))


def cct_to_xy(cct: float, observer: str | None = None) -> tuple[float, float]:
    """CIE daylight locus chromaticity for 4000–25000 K (CIE 15); 6504 K returns the exact D65 constant."""
    if round(cct) == 6504:
        base = (D65_X, D65_Y)
    else:
        t = float(cct)
        if t <= 7000:
            x = -4.6070e9 / t**3 + 2.9678e6 / t**2 + 0.09911e3 / t + 0.244063
        else:
            x = -2.0064e9 / t**3 + 1.9018e6 / t**2 + 0.24748e3 / t + 0.237040
        y = -3.000 * x * x + 2.870 * x - 0.275
        base = (x, y)
    return adapt_whitepoint_for_observer(base, observer) or base


TARGETS: tuple[CalibrationTarget, ...] = (
    CalibrationTarget("photo", QT_TRANSLATE_NOOP("Targets", "Photography & Prepress"), 120.0, 6504,
                      patch_count=PATCH_HIGH, allow_d50=True),
    CalibrationTarget("office", QT_TRANSLATE_NOOP("Targets", "Office, Web & Everyday"), 140.0, 6504),
    CalibrationTarget("srgb", QT_TRANSLATE_NOOP("Targets", "sRGB"), 120.0, 6504, tone_curve=TONE_SRGB),
    CalibrationTarget("softproof", QT_TRANSLATE_NOOP("Targets", "Softproof"), 160.0, 5800,
                      tone_curve=TONE_LSTAR, patch_count=PATCH_HIGH),
    CalibrationTarget("video", QT_TRANSLATE_NOOP("Targets", "Video / Rec.709"), 100.0, 6504,
                      tone_curve=TONE_BT1886, gamma=2.4, patch_count=PATCH_HIGH),
    CalibrationTarget("evening", QT_TRANSLATE_NOOP("Targets", "Evening / Dark Room"), 90.0, 6504),
    CalibrationTarget("custom", QT_TRANSLATE_NOOP("Targets", "Custom Luminance"), 110.0, 6504,
                      custom_luminance=True),
)


def batch_targets(targets: list[CalibrationTarget] | tuple[CalibrationTarget, ...] = TARGETS
                  ) -> list[CalibrationTarget]:
    """Targets for a batch run: a target with a D65/D50 switch is offered in both variants."""
    result = []
    for t in targets:
        if t.allow_d50:
            result += [t.with_d50(False), t.with_d50(True)]
        else:
            result.append(t)
    return result


def target_by_key(key: str) -> CalibrationTarget:
    return next((t for t in TARGETS if t.key == key), TARGETS[0])
