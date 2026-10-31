"""Compositor abstraction layer for Wayland color management (KDE KWin 6, GNOME Mutter prepared)."""

from __future__ import annotations

import os

from .base import CalibrationColorGuard, CompositorBackend, CompositorOutputState
from .kwin import KWinBackend
from .mutter import MutterBackend


def get_compositor_backend(prefer: str | None = None) -> CompositorBackend:
    """Automatically selects the appropriate compositor backend based on the active desktop environment."""
    choice = (prefer or os.environ.get("XDG_CURRENT_DESKTOP", "")).lower()
    if "gnome" in choice or "mutter" in choice:
        return MutterBackend()
    return KWinBackend()


__all__ = [
    "CalibrationColorGuard",
    "CompositorBackend",
    "CompositorOutputState",
    "KWinBackend",
    "MutterBackend",
    "get_compositor_backend",
]
