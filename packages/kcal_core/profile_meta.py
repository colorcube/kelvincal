"""Sidecar metadata of KelvinCal profiles: the display hardware state (DDC) the profile was measured in.

An ICC profile only describes the display in the state it was measured in. KelvinCal sets that state in
hardware (brightness, contrast, RGB gains), so it stores those values next to the profile as
`<name>.kelvincal.json` to be able to restore them later (inspector A/B preview, verification).
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

DdcValues = tuple[int, int, int, int, int]  # brightness, contrast, red, green, blue gain
_KEYS = ("brightness", "contrast", "red_gain", "green_gain", "blue_gain")


def meta_path(icc_path: str | Path) -> Path:
    p = Path(icc_path)
    return p.with_name(p.stem + ".kelvincal.json")


def write_profile_meta(icc_path: str | Path, ddc: DdcValues, connector: str = "", edid_hash: str = "",
                       target: str = "") -> Path:
    data = {
        "ddc": dict(zip(_KEYS, ddc)),
        "connector": connector,
        "edid_hash": edid_hash,
        "target": target,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    path = meta_path(icc_path)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def read_profile_ddc(icc_path: str | Path) -> DdcValues | None:
    """DDC values stored for a profile, or None (no sidecar or incomplete)."""
    try:
        data = json.loads(meta_path(icc_path).read_text(encoding="utf-8"))
        values = tuple(int(data["ddc"][k]) for k in _KEYS)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return values  # type: ignore[return-value]


def connector_of(icc_path: str | Path) -> str:
    """Connector stored in the sidecar ("" if unknown)."""
    try:
        return str(json.loads(meta_path(icc_path).read_text(encoding="utf-8")).get("connector", ""))
    except (OSError, ValueError, AttributeError):
        return ""
