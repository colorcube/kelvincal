"""kelvincal.core: Shared data models, colorimetry math, display discovery, and compositor abstraction."""

from .i18n import translate
from .models import (
    ColorMeasurement,
    ContrastStepResult,
    DDCState,
    DisplayInfo,
    DisplayPresetEntry,
    Preset,
)

__all__ = [
    "ColorMeasurement",
    "ContrastStepResult",
    "DDCState",
    "DisplayInfo",
    "DisplayPresetEntry",
    "Preset",
    "translate",
]
