"""Reusable widgets for the KelvinCal main window (palette-based, no style sheets)."""

from .basic import (
    Card,
    ClickableLabel,
    ElidedLabel,
    KpiRow,
    MessageBanner,
    SecondaryLabel,
    SectionHeader,
    SegmentedControl,
    Separator,
    StatusDot,
    mix,
    mono_font,
    title_font,
)
from .arrangement import ArrangedDisplay, DisplayArrangement
from .log_panel import LogPanel
from .run_views import ContrastSearchView, DdcBars, PatchSwatch, PhaseStepper, SwatchStrip

__all__ = [
    "ArrangedDisplay",
    "DisplayArrangement",
    "Card",
    "ClickableLabel",
    "ElidedLabel",
    "ContrastSearchView",
    "DdcBars",
    "LogPanel",
    "MessageBanner",
    "PatchSwatch",
    "PhaseStepper",
    "SecondaryLabel",
    "SectionHeader",
    "SegmentedControl",
    "StatusDot",
    "SwatchStrip",
    "mix",
    "mono_font",
    "title_font",
]
