"""Management of multi-monitor presets (DDC/CI hardware state + ICC profiles) for KelvinCal."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path

from kcal_core.compositor import CompositorBackend, get_compositor_backend
from kcal_core.discovery import discover_displays
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
WORKSPACE_PRESETS_PATH = Path(__file__).resolve().parents[2] / "presets.json"


def resolve_default_presets_path() -> Path:
    """Resolves the storage path for presets (workspace presets.json or ~/.config/kelvincal/presets.json)."""
    env_path = os.environ.get("KELVINCAL_PRESETS_PATH")
    if env_path:
        return Path(env_path)
    if WORKSPACE_PRESETS_PATH.exists():
        return WORKSPACE_PRESETS_PATH
    try:
        DEFAULT_PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if os.access(DEFAULT_PRESETS_PATH.parent, os.W_OK):
            return DEFAULT_PRESETS_PATH
    except OSError:
        pass
    if DEFAULT_PRESETS_PATH.exists():
        return DEFAULT_PRESETS_PATH
    return WORKSPACE_PRESETS_PATH


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
            raise ValueError(f"Preset '{name}' was not found in {self.config_path}.")

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
                vcp_map: dict[str, int] = {}
                if entry.ddc_brightness is not None and entry.ddc_brightness != disp.ddc.brightness:
                    vcp_map[VCP_BRIGHTNESS] = entry.ddc_brightness
                    disp.ddc.brightness = entry.ddc_brightness
                if entry.ddc_contrast is not None and entry.ddc_contrast != disp.ddc.contrast:
                    vcp_map[VCP_CONTRAST] = entry.ddc_contrast
                    disp.ddc.contrast = entry.ddc_contrast
                if entry.ddc_red_gain is not None and entry.ddc_red_gain != disp.ddc.red_gain:
                    vcp_map[VCP_RED_GAIN] = entry.ddc_red_gain
                    disp.ddc.red_gain = entry.ddc_red_gain
                if entry.ddc_green_gain is not None and entry.ddc_green_gain != disp.ddc.green_gain:
                    vcp_map[VCP_GREEN_GAIN] = entry.ddc_green_gain
                    disp.ddc.green_gain = entry.ddc_green_gain
                if entry.ddc_blue_gain is not None and entry.ddc_blue_gain != disp.ddc.blue_gain:
                    vcp_map[VCP_BLUE_GAIN] = entry.ddc_blue_gain
                    disp.ddc.blue_gain = entry.ddc_blue_gain
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

        # 3. Record active preset
        self.save_all(presets, active_preset=target.name)
        return target
