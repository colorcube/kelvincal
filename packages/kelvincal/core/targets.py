"""Calibration targets ("Einsatzzweck") offered in the simple mode.

A target bundles luminance, whitepoint, reference tone curve and patch count. The whitepoint and luminance
are applied in hardware (Phase 1b); the tone curve is currently only the reference for the profile
inspection (no calibration curves are generated yet).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from kelvincal.core.i18n import QT_TRANSLATE_NOOP, translate
from kelvincal.core.models import D65_X, D65_Y

SECONDS_PER_PATCH = 1.25      # dispread with an i1Display-class colorimeter incl. settle time
HARDWARE_PHASES_SECONDS = 60  # Phase 1a + 1b

TONE_GAMMA = "gamma"
TONE_SRGB = "srgb"
TONE_BT1886 = "bt1886"
TONE_LSTAR = "lstar"


@dataclass(frozen=True)
class CalibrationTarget:
    key: str
    title: str                 # untranslated source text (context "Targets")
    luminance: float           # cd/m²
    cct: int                   # whitepoint colour temperature; 6504 = exact D65
    tone_curve: str = TONE_GAMMA
    gamma: float = 2.2
    patch_count: int = 275
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

    def estimated_minutes(self) -> int:
        return round((self.patch_count * SECONDS_PER_PATCH + HARDWARE_PHASES_SECONDS) / 60)

    def with_d50(self, enabled: bool) -> CalibrationTarget:
        return replace(self, cct=5003 if enabled else 6504)

    def with_luminance(self, luminance: float) -> CalibrationTarget:
        return replace(self, luminance=luminance)


def _num(value: float) -> str:
    try:
        from PySide6.QtCore import QLocale

        return QLocale().toString(value, "f", 1)
    except ImportError:  # pragma: no cover
        return f"{value:.1f}"


def cct_to_xy(cct: float) -> tuple[float, float]:
    """CIE daylight locus chromaticity for 4000–25000 K (CIE 15); 6504 K returns the exact D65 constant."""
    if round(cct) == 6504:
        return D65_X, D65_Y
    t = float(cct)
    if t <= 7000:
        x = -4.6070e9 / t**3 + 2.9678e6 / t**2 + 0.09911e3 / t + 0.244063
    else:
        x = -2.0064e9 / t**3 + 1.9018e6 / t**2 + 0.24748e3 / t + 0.237040
    y = -3.000 * x * x + 2.870 * x - 0.275
    return x, y


TARGETS: tuple[CalibrationTarget, ...] = (
    CalibrationTarget("photo", QT_TRANSLATE_NOOP("Targets", "Photography & Prepress"), 120.0, 6504,
                      patch_count=875, allow_d50=True),
    CalibrationTarget("office", QT_TRANSLATE_NOOP("Targets", "Office, Web & Everyday"), 140.0, 6504),
    CalibrationTarget("srgb", QT_TRANSLATE_NOOP("Targets", "sRGB"), 120.0, 6504, tone_curve=TONE_SRGB),
    CalibrationTarget("softproof", QT_TRANSLATE_NOOP("Targets", "Softproof"), 160.0, 5800,
                      tone_curve=TONE_LSTAR, patch_count=875),
    CalibrationTarget("video", QT_TRANSLATE_NOOP("Targets", "Video / Rec.709"), 100.0, 6504,
                      tone_curve=TONE_BT1886, gamma=2.4, patch_count=500),
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
