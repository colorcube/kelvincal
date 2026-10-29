"""Profile inspector (mockup 1g/1j): dialog, plot base and plots."""

from .dialog import InspectorDialog
from .plots import VIEW_GAMMA, VIEW_KNICK, VIEW_TRC, CurvePlot, GamutPlot

__all__ = ["CurvePlot", "GamutPlot", "InspectorDialog", "VIEW_GAMMA", "VIEW_KNICK", "VIEW_TRC"]
