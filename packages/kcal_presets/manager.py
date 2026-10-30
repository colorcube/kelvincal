"""Management of multi-monitor presets (DDC/CI hardware state + ICC profiles) for KelvinCal."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil

from kcal_core.compositor import CompositorBackend, get_compositor_backend
from kcal_core.discovery import discover_displays
from kcal_core.i18n import translate
from kcal_core.models import DisplayInfo, DisplayPresetEntry, Preset
from kcal_ddc.ddc_client import (
    DDCClient,
    VCP_BLUE_GAIN,
    VCP_BRIGHTNESS,
    VCP_CONTRAST,
    VCP_GREEN_GAIN,
    VCP_RED_GAIN,
)


DEFAULT_PRESETS_PATH = Path.home() / ".config" / "kelvincal" / "presets.json"
# Legacy location used by early development builds (repository root). Only read for one-time migration.
LEGACY_WORKSPACE_PRESETS_PATH = Path(__file__).resolve().parents[2] / "presets.json"


def resolve_default_presets_path() -> Path:
    """Resolves the storage path for presets ($KELVINCAL_PRESETS_PATH or ~/.config/kelvincal/presets.json).

    If the config file does not exist yet but a legacy presets.json exists in the repository root,
    it is copied (not moved) to the config location once.
    """
    env_path = os.environ.get("KELVINCAL_PRESETS_PATH")
    if env_path:
        return Path(env_path)
    if not DEFAULT_PRESETS_PATH.exists() and LEGACY_WORKSPACE_PRESETS_PATH.exists():
        try:
            DEFAULT_PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(LEGACY_WORKSPACE_PRESETS_PATH, DEFAULT_PRESETS_PATH)
        except OSError:
            return LEGACY_WORKSPACE_PRESETS_PATH
    return DEFAULT_PRESETS_PATH


class PresetManager:
    """Loads, saves, and activates multi-monitor presets."""

    def __init__(
        self,
        config_path: Path | None = None,
        compositor: CompositorBackend | None = None,
        ddc_client: DDCClient | None = None,
    ) -> None:
        self.config_path = config_path or resolve_default_presets_path()
        self.compositor = compositor or get_compositor_backend()
        self.ddc_client = ddc_client or DDCClient(settle_seconds=0.1)

    def load_all(self) -> tuple[str, list[Preset]]:
        """Loads the active preset name and the list of all saved presets."""
        if not self.config_path.exists():
            return ("", [])
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ("", [])

        active_name = str(raw.get("active_preset", ""))
        presets = [Preset.from_dict(p) for p in raw.get("presets", [])]
        return (active_name, presets)

    def save_all(self, presets: list[Preset], active_preset: str = "") -> None:
        """Atomically writes the preset list to the JSON configuration file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_preset": active_preset,
            "presets": [p.to_dict() for p in presets],
        }
        tmp_path = self.config_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.config_path)

    def upsert_preset(self, preset: Preset, mark_active: bool = False) -> None:
        """Inserts a new preset or updates an existing preset with the same name."""
        active, presets = self.load_all()
        updated = False
        for idx, existing in enumerate(presets):
            if existing.name == preset.name:
                presets[idx] = preset
                updated = True
                break
        if not updated:
            presets.append(preset)
        if mark_active:
            active = preset.name
        self.save_all(presets, active_preset=active)

    def capture_current_state(
        self,
        name: str,
        description: str = "",
        displays: list[DisplayInfo] | None = None,
        mark_active: bool = True,
    ) -> Preset:
        """Reads the live state of all connected monitors (DDC + ICC) and saves it as a preset."""
        current_displays = (
            displays
            if displays is not None
            else discover_displays(compositor=self.compositor, include_ddc_values=True)
        )
        entries: list[DisplayPresetEntry] = []
        for d in current_displays:
            entries.append(
                DisplayPresetEntry(
                    edid_hash=d.edid_hash,
                    connector=d.connector,
                    model=d.model or d.edid_identifier,
                    serial=d.serial,
                    ddc_brightness=d.ddc.brightness,
                    ddc_contrast=d.ddc.contrast,
                    ddc_red_gain=d.ddc.red_gain,
                    ddc_green_gain=d.ddc.green_gain,
                    ddc_blue_gain=d.ddc.blue_gain,
                    icc_profile=d.icc_profile_path,
                    color_profile_source=d.color_profile_source or "ICC",
                    compositor_brightness=d.compositor_brightness,
                )
            )

        preset = Preset(name=name, description=description, displays=entries)
        self.upsert_preset(preset, mark_active=mark_active)
        return preset

    def apply_preset(
        self,
        name: str,
        displays: list[DisplayInfo] | None = None,
        apply_compositor: bool = True,
    ) -> Preset:
        """Activates a preset in parallel across all monitors (DDC/CI + compositor ICC profile)."""
        _, presets = self.load_all()
        target = next((p for p in presets if p.name == name), None)
        if target is None:
            raise ValueError(translate("Errors", "Preset '{name}' was not found in {path}.").format(
                name=name, path=self.config_path))

        live_displays = (
            displays
            if displays is not None
            else discover_displays(compositor=self.compositor, include_ddc_values=False)
        )

        # Match primarily by edid_hash, falling back to connector name
        by_edid = {d.edid_hash: d for d in live_displays if d.edid_hash}
        by_con = {d.connector: d for d in live_displays if d.connector}

        ddc_tasks: list[tuple[int, dict[str, int]]] = []
        comp_updates: list[dict[str, object]] = []

        for entry in target.displays:
            disp = by_edid.get(entry.edid_hash) or by_con.get(entry.connector)
            if disp is None:
                continue

            if disp.i2c_bus is not None:
                # Always write every value: `displays` may come from a cache (GUI) that no longer matches the
                # hardware – e.g. KWin restored its own brightness, or the user changed it in the monitor OSD.
                vcp_map = {
                    vcp: value
                    for (entry_attr, ddc_attr), vcp in zip(PRESET_DDC_FIELDS, (VCP_BRIGHTNESS, VCP_CONTRAST,
                                                                             VCP_RED_GAIN, VCP_GREEN_GAIN,
                                                                             VCP_BLUE_GAIN))
                    if (value := getattr(entry, entry_attr)) is not None
                }
                for entry_attr, ddc_attr in PRESET_DDC_FIELDS:
                    if getattr(entry, entry_attr) is not None:
                        setattr(disp.ddc, ddc_attr, getattr(entry, entry_attr))
                if vcp_map:
                    ddc_tasks.append((disp.i2c_bus, vcp_map))

            if apply_compositor and disp.connector:
                if (
                    entry.icc_profile != disp.icc_profile_path
                    or entry.color_profile_source != disp.color_profile_source
                ):
                    # Pass brightness=None so KWin does not contend with ddcutil on the I²C bus
                    comp_updates.append(
                        {
                            "connector": disp.connector,
                            "icc_profile_path": entry.icc_profile,
                            "color_profile_source": entry.color_profile_source,
                            "brightness": None,
                        }
                    )
                    disp.icc_profile_path = entry.icc_profile
                    disp.color_profile_source = entry.color_profile_source

        # 1. Switch compositor ICC profiles atomically (~25 ms in KWin)
        if apply_compositor and comp_updates:
            self.compositor.apply_batch(comp_updates)

        # 2. Write changed DDC registers in parallel across affected I²C buses (~200 ms)
        if ddc_tasks:
            def _run_ddc(task: tuple[int, dict[str, int]]) -> None:
                bus, vcp_dict = task
                self.ddc_client.set_vcp_values(bus, vcp_dict, verify=False, settle=False)

            with ThreadPoolExecutor(max_workers=len(ddc_tasks)) as pool:
                list(pool.map(_run_ddc, ddc_tasks))

        # 3. KWin controls VCP 0x10 itself: give it the preset's brightness, or it restores its own later
        brightness = {
            disp.connector: entry.ddc_brightness
            for entry in target.displays
            if entry.ddc_brightness is not None
            and (disp := by_edid.get(entry.edid_hash) or by_con.get(entry.connector)) is not None
            and disp.i2c_bus is not None
        }
        if apply_compositor and brightness:
            self.compositor.sync_brightness(brightness)

        # 4. Record active preset
        self.save_all(presets, active_preset=target.name)
        return target

    # ------------------------------------------------------------------ editing

    def _edit(self, fn) -> None:  # noqa: ANN001
        active, presets = self.load_all()
        active = fn(presets, active)
        self.save_all(presets, active_preset=active)

    def rename_preset(self, old_name: str, new_name: str) -> None:
        """Renames a preset (keeps it active if it was). Raises ValueError on unknown or duplicate names."""
        new_name = new_name.strip()

        def fn(presets: list[Preset], active: str) -> str:
            if not new_name or any(p.name == new_name for p in presets):
                raise ValueError(_name_taken(new_name))
            target = _find(presets, old_name)
            target.name = new_name
            return new_name if active == old_name else active

        self._edit(fn)

    def duplicate_preset(self, name: str, new_name: str) -> None:
        def fn(presets: list[Preset], active: str) -> str:
            if not new_name.strip() or any(p.name == new_name for p in presets):
                raise ValueError(_name_taken(new_name))
            copy = Preset.from_dict(_find(presets, name).to_dict())
            copy.name = new_name.strip()
            presets.append(copy)
            return active

        self._edit(fn)

    def update_display(self, name: str, display: DisplayInfo, icc_profile: str) -> None:
        """Overwrites (or adds) the entry of one display in preset `name` with its live DDC values and
        `icc_profile`; the other displays of the preset stay untouched."""
        def fn(presets: list[Preset], active: str) -> str:
            preset = _find(presets, name)
            entry = next((e for e in preset.displays if match_display(e, [display]) is display), None)
            if entry is None:
                entry = DisplayPresetEntry(edid_hash=display.edid_hash)
                preset.displays.append(entry)
            entry.edid_hash = display.edid_hash or entry.edid_hash
            entry.connector = display.connector
            entry.model = display.model or display.edid_identifier
            entry.serial = display.serial
            for entry_attr, ddc_attr in PRESET_DDC_FIELDS:
                setattr(entry, entry_attr, getattr(display.ddc, ddc_attr))
            entry.icc_profile = icc_profile
            entry.color_profile_source = "ICC"
            return active

        self._edit(fn)

    def delete_preset(self, name: str) -> None:
        def fn(presets: list[Preset], active: str) -> str:
            presets.remove(_find(presets, name))
            return "" if active == name else active

        self._edit(fn)


def _find(presets: list[Preset], name: str) -> Preset:
    for p in presets:
        if p.name == name:
            return p
    raise ValueError(translate("Errors", "Preset '{name}' was not found.").format(name=name))


def _name_taken(name: str) -> str:
    return translate("Errors", "Preset name '{name}' is empty or already used.").format(name=name)


PRESET_DDC_FIELDS = (
    ("ddc_brightness", "brightness"),
    ("ddc_contrast", "contrast"),
    ("ddc_red_gain", "red_gain"),
    ("ddc_green_gain", "green_gain"),
    ("ddc_blue_gain", "blue_gain"),
)


def match_display(entry: DisplayPresetEntry, displays: list[DisplayInfo]) -> DisplayInfo | None:
    """Finds the live display for a preset entry (EDID hash first, connector as fallback)."""
    for d in displays:
        if entry.edid_hash and d.edid_hash == entry.edid_hash:
            return d
    return next((d for d in displays if entry.connector and d.connector == entry.connector), None)


def preset_drift(preset: Preset, displays: list[DisplayInfo]) -> dict[str, list[str]]:
    """Returns {connector: [differing fields]} where live DDC values or the ICC profile differ from `preset`.

    Field names are the `DisplayPresetEntry` attribute names (e.g. "ddc_blue_gain", "icc_profile").
    Displays without DDC readings are only compared by ICC profile.
    """
    drift: dict[str, list[str]] = {}
    for entry in preset.displays:
        disp = match_display(entry, displays)
        if disp is None:
            continue
        fields = [
            entry_attr for entry_attr, ddc_attr in PRESET_DDC_FIELDS
            if getattr(entry, entry_attr) is not None
            and getattr(disp.ddc, ddc_attr) is not None
            and getattr(entry, entry_attr) != getattr(disp.ddc, ddc_attr)
        ]
        if (entry.icc_profile or "") != (disp.icc_profile_path or "") and entry.color_profile_source == "ICC":
            fields.append("icc_profile")
        if fields:
            drift[disp.connector] = fields
    return drift
