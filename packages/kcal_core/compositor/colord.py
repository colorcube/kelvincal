"""Helper functions for optional ICC profile synchronization with colord (legacy/XWayland apps & GNOME)."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


def sync_profile_to_colord(icc_path: Path) -> bool:
    """Imports an ICC profile into colord via colormgr if not already registered."""
    colormgr = shutil.which("colormgr")
    if not colormgr or not icc_path.is_file():
        return False

    try:
        subprocess.run(
            [colormgr, "import-profile", str(icc_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False
