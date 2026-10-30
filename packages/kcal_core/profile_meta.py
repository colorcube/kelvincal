"""Sidecar metadata of KelvinCal profiles: the display hardware state (DDC) the profile was measured in.

An ICC profile only describes the display in the state it was measured in. KelvinCal sets that state in
hardware (brightness, contrast, RGB gains), so it stores those values next to the profile as
`<name>.kelvincal.json` to be able to restore them later (inspector A/B preview, verification).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

DdcValues = tuple[int, int, int, int, int]  # brightness, contrast, red, green, blue gain
_KEYS = ("brightness", "contrast", "red_gain", "green_gain", "blue_gain")


def meta_path(icc_path: str | Path) -> Path:
    p = Path(icc_path)
    return p.with_name(p.stem + ".kelvincal.json")


@dataclass(frozen=True)
class ProfileMeta:
    icc_path: Path
    ddc: DdcValues
    connector: str = ""
    edid_hash: str = ""
    target: str = ""              # target key (kcal_core.targets), "" for expert runs without a target
    luminance: float | None = None
    whitepoint: str = ""          # label, e.g. "D65", "D50", "5800 K"
    created: str = ""             # ISO timestamp


def write_profile_meta(icc_path: str | Path, ddc: DdcValues, connector: str = "", edid_hash: str = "",
                       target: str = "", luminance: float | None = None, whitepoint: str = "") -> Path:
    data = {
        "ddc": dict(zip(_KEYS, ddc)),
        "connector": connector,
        "edid_hash": edid_hash,
        "target": target,
        "luminance": luminance,
        "whitepoint": whitepoint,
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


def read_profile_meta(icc_path: str | Path) -> ProfileMeta | None:
    """Complete sidecar of a profile, or None (no sidecar or no complete DDC values)."""
    ddc = read_profile_ddc(icc_path)
    if ddc is None:
        return None
    try:
        data = json.loads(meta_path(icc_path).read_text(encoding="utf-8"))
        lum = data.get("luminance")
        return ProfileMeta(
            icc_path=Path(icc_path), ddc=ddc, connector=str(data.get("connector", "")),
            edid_hash=str(data.get("edid_hash", "")), target=str(data.get("target", "")),
            luminance=float(lum) if lum is not None else None, whitepoint=str(data.get("whitepoint", "")),
            created=str(data.get("created", "")))
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def list_profile_meta(icc_dir: str | Path) -> list[ProfileMeta]:
    """All profiles in `icc_dir` that have a sidecar (profiles whose .icc was deleted are skipped)."""
    result = []
    for sidecar in sorted(Path(icc_dir).glob("*.kelvincal.json")):
        stem = sidecar.name[: -len(".kelvincal.json")]
        icc = next((p for p in (sidecar.with_name(stem + ext) for ext in (".icc", ".icm")) if p.is_file()), None)
        meta = read_profile_meta(icc) if icc else None
        if meta is not None:
            result.append(meta)
    return result

