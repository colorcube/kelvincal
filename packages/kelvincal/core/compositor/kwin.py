"""KDE Plasma 6 (KWin Wayland) compositor backend via kwinoutputconfig.json and kscreen-doctor."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from kelvincal.core.i18n import translate
from .base import CompositorBackend, CompositorOutputState
from .colord import sync_profile_to_colord


class KWinBackend(CompositorBackend):
    """Controls KWin 6 color profiles via kscreen-doctor and reads kwinoutputconfig.json."""

    def __init__(
        self,
        config_path: Path | None = None,
        sync_colord: bool = False,
    ) -> None:
        self.config_path = config_path or (
            Path.home() / ".config" / "kwinoutputconfig.json"
        )
        self.sync_colord = sync_colord

    @property
    def name(self) -> str:
        return "kwin"

    @staticmethod
    def _has_wayland_socket() -> bool:
        """Checks whether the current process has access to the active Wayland display socket.

        Prevents kscreen-doctor from aborting with qFatal/SIGABRT in headless or sandboxed environments.
        """
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
        socket_path = Path(runtime_dir) / wayland_display
        return socket_path.exists()

    def get_outputs(self) -> dict[str, CompositorOutputState]:
        """Reads the current output configuration from ~/.config/kwinoutputconfig.json."""
        result: dict[str, CompositorOutputState] = {}
        if not self.config_path.exists():
            return result

        try:
            sections = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return result

        for section in sections:
            if section.get("name") != "outputs":
                continue
            for item in section.get("data", []):
                connector = str(item.get("connectorName", ""))
                if not connector:
                    continue
                mode = item.get("mode", {}) or {}
                refresh_mhz = float(mode.get("refreshRate", 60000))
                result[connector] = CompositorOutputState(
                    connector=connector,
                    edid_hash=str(item.get("edidHash", "")),
                    edid_identifier=str(item.get("edidIdentifier", "")),
                    uuid=str(item.get("uuid", "")),
                    color_profile_source=str(item.get("colorProfileSource", "sRGB")),
                    icc_profile_path=str(item.get("iccProfilePath", "")),
                    brightness=float(item.get("brightness", 1.0)),
                    sdr_brightness=int(item.get("sdrBrightness", 200)),
                    hdr_enabled=bool(item.get("highDynamicRange", False)),
                    wcg_enabled=bool(item.get("wideColorGamut", False)),
                    allow_ddc_ci=bool(item.get("allowDdcCi", True)),
                    width=int(mode.get("width", 0)),
                    height=int(mode.get("height", 0)),
                    refresh_hz=round(refresh_mhz / 1000.0, 2),
                    scale=float(item.get("scale", 1.0)),
                )
        return result

    def _build_kscreen_args_for_update(self, upd: dict[str, object]) -> list[str]:
        connector = str(upd["connector"])
        source = str(upd.get("color_profile_source", "ICC"))
        icc_path = str(upd.get("icc_profile_path", ""))
        brightness = upd.get("brightness")
        disable_hdr_wcg = bool(upd.get("disable_hdr_wcg", False))

        args: list[str] = []
        if icc_path or source == "ICC":
            args.append(f"output.{connector}.iccprofile.{icc_path}")
            args.append(f"output.{connector}.colorProfileSource.ICC")
        else:
            args.append(f"output.{connector}.colorProfileSource.{source}")

        if brightness is not None:
            pct = max(0, min(100, round(float(brightness) * 100)))
            args.append(f"output.{connector}.brightness.{pct}")

        if disable_hdr_wcg:
            args.append(f"output.{connector}.hdr.disable")
            args.append(f"output.{connector}.wcg.disable")

        return args

    def apply_output_profile(
        self,
        connector: str,
        icc_profile_path: str = "",
        color_profile_source: str = "ICC",
        brightness: float | None = None,
        disable_hdr_wcg: bool = False,
    ) -> None:
        self.apply_batch(
            [
                {
                    "connector": connector,
                    "icc_profile_path": icc_profile_path,
                    "color_profile_source": color_profile_source,
                    "brightness": brightness,
                    "disable_hdr_wcg": disable_hdr_wcg,
                }
            ]
        )

    def sync_brightness(self, values: dict[str, int]) -> list[str]:
        """KWin brightness = DDC brightness / 100 for outputs whose DDC/CI KWin controls (see base class)."""
        outputs = self.get_outputs()
        changed = [
            c for c, v in values.items()
            if c in outputs and outputs[c].allow_ddc_ci and round(outputs[c].brightness * 100) != v
        ]
        if changed:
            self._kscreen([f"output.{c}.brightness.{max(0, min(100, int(values[c])))}" for c in changed])
        return changed

    def _kscreen(self, kscreen_args: list[str]) -> None:
        kscreen_bin = shutil.which("kscreen-doctor")
        if not kscreen_bin:
            raise RuntimeError(translate("Errors", "kscreen-doctor was not found in PATH (package: kscreen)."))
        if not self._has_wayland_socket():
            raise RuntimeError(translate(
                "Errors", "No access to the Wayland socket ($XDG_RUNTIME_DIR/$WAYLAND_DISPLAY). "
                "kscreen-doctor must be executed inside an active Wayland session."))
        subprocess.run([kscreen_bin, *kscreen_args], check=True, capture_output=True, text=True)

    def apply_batch(self, updates: list[dict[str, object]]) -> None:
        """Applies all output updates in a single atomic kscreen-doctor invocation."""
        if not updates:
            return

        args: list[str] = []
        for upd in updates:
            args.extend(self._build_kscreen_args_for_update(upd))
        self._kscreen(args)

        if self.sync_colord:
            for upd in updates:
                icc_path = str(upd.get("icc_profile_path", ""))
                if icc_path and Path(icc_path).is_file():
                    sync_profile_to_colord(Path(icc_path))
