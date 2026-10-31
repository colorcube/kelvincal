"""Presets from calibrations: one preset per target, using the newest matching profile of every display.

Every profile KelvinCal saves gets a sidecar (`kelvincal.core.profile_meta`) with the DDC values it was
measured with, the display (EDID hash, connector) and the target (key, luminance, whitepoint). That is
everything a preset entry needs, so after calibrating the targets on all displays (e.g. by batch) the
presets can be assembled automatically instead of capturing them by hand.

Profiles are grouped by target key + luminance + whitepoint (two "Office" runs at 140 and 120 cd/m²
give two presets). Displays without a profile for a group are left out of a new preset (applying it
does not touch them); an existing preset of the same name keeps its entries for them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kelvincal.core.models import DisplayInfo, DisplayPresetEntry, Preset
from kelvincal.core.profile_meta import ProfileMeta
from kelvincal.core.targets import TARGETS

GroupKey = tuple[str, float | None, str]   # target key, luminance, whitepoint label


@dataclass
class PresetProposal:
    group: GroupKey
    name: str
    profiles: dict[str, ProfileMeta] = field(default_factory=dict)   # connector → newest profile
    exists: bool = False

    @property
    def target_key(self) -> str:
        return self.group[0]


def _display_for(meta: ProfileMeta, displays: list[DisplayInfo]) -> DisplayInfo | None:
    """Same matching as presets: EDID hash first, connector as fallback (only if the sidecar has no hash)."""
    if meta.edid_hash:
        return next((d for d in displays if d.edid_hash == meta.edid_hash), None)
    return next((d for d in displays if meta.connector and d.connector == meta.connector), None)


def preset_name(group: GroupKey, titles: dict[str, str] | None = None) -> str:
    """"Office, Web & Everyday · 140 cd/m² · D65" (`titles` maps target keys to translated titles)."""
    key, luminance, whitepoint = group
    default = {t.key: t.title for t in TARGETS}
    parts = [(titles or {}).get(key) or default.get(key, key)]
    if luminance is not None:
        parts.append(f"{luminance:.0f} cd/m²")
    if whitepoint:
        parts.append(whitepoint)
    return " · ".join(parts)


def propose_presets(metas: list[ProfileMeta], displays: list[DisplayInfo], existing: list[Preset],
                    titles: dict[str, str] | None = None) -> list[PresetProposal]:
    """One proposal per target group that has a profile for at least one connected display.

    Profiles without a target (expert runs) are ignored. Order: as in `TARGETS`, then luminance.
    """
    proposals: dict[GroupKey, PresetProposal] = {}
    for meta in metas:
        if not meta.target:
            continue
        disp = _display_for(meta, displays)
        if disp is None:
            continue
        group = (meta.target, round(meta.luminance) if meta.luminance is not None else None, meta.whitepoint)
        prop = proposals.setdefault(group, PresetProposal(group, preset_name(group, titles)))
        current = prop.profiles.get(disp.connector)
        if current is None or meta.created > current.created:
            prop.profiles[disp.connector] = meta
    names = {p.name for p in existing}
    order = {t.key: i for i, t in enumerate(TARGETS)}
    result = sorted(proposals.values(),
                    key=lambda p: (order.get(p.group[0], len(order)), -(p.group[1] or 0), p.group[2]))
    for p in result:
        p.exists = p.name in names
    return result


def build_preset(proposal: PresetProposal, displays: list[DisplayInfo], existing: Preset | None = None) -> Preset:
    """The preset for `proposal`; entries of displays without a profile are kept from `existing`."""
    preset = Preset.from_dict(existing.to_dict()) if existing else Preset(name=proposal.name)
    preset.name = proposal.name
    if not preset.description:
        preset.description = "KelvinCal"
    for connector, meta in proposal.profiles.items():
        disp = next(d for d in displays if d.connector == connector)
        entry = next((e for e in preset.displays
                      if (e.edid_hash and e.edid_hash == disp.edid_hash)
                      or (not e.edid_hash and e.connector == disp.connector)), None)
        if entry is None:
            entry = DisplayPresetEntry(edid_hash=disp.edid_hash)
            preset.displays.append(entry)
        entry.edid_hash = disp.edid_hash or entry.edid_hash
        entry.connector = disp.connector
        entry.model = disp.model or disp.edid_identifier
        entry.serial = disp.serial
        (entry.ddc_brightness, entry.ddc_contrast, entry.ddc_red_gain, entry.ddc_green_gain,
         entry.ddc_blue_gain) = meta.ddc
        entry.icc_profile = str(meta.icc_path)
        entry.color_profile_source = "ICC"
        entry.compositor_brightness = 1.0
    return preset
