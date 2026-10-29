"""Shared filesystem locations for KelvinCal."""

from __future__ import annotations

import os
from pathlib import Path


def user_icc_dir() -> Path:
    """Per-user ICC profile directory ($XDG_DATA_HOME/icc, default ~/.local/share/icc)."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "icc"
