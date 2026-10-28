"""Hardware and display discovery: Links DRM sysfs (EDID MD5, model, S/N, I²C bus) and compositor in < 1 ms."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import re
import shutil
import subprocess

from .compositor import CompositorBackend, get_compositor_backend
from .models import DisplayInfo


EMPTY_MD5 = "d41d8cd98f00b204e9800998ecf8427e"


def parse_edid_bytes(edid_bytes: bytes) -> dict[str, str]:
    """Extracts 3-letter manufacturer ID, model name (0xFC), and ASCII serial (0xFF) from raw 128-byte EDID."""
    if len(edid_bytes) < 128:
        return {"manufacturer": "", "model": "", "serial": ""}

    mfg_word = (edid_bytes[8] << 8) | edid_bytes[9]
    mfg = "".join(chr(((mfg_word >> shift) & 0x1F) + 64) for shift in (10, 5, 0))

    model = ""
    serial = ""
    for offset in (54, 72, 90, 108):
        desc = edid_bytes[offset : offset + 18]
        if len(desc) == 18 and desc[:3] == b"\x00\x00\x00":
            tag = desc[3]
            text = desc[5:18].decode("ascii", errors="ignore").split("\n")[0].strip()
            if tag == 0xFC:
                model = text
            elif tag == 0xFF:
                serial = text

    return {"manufacturer": mfg, "model": model, "serial": serial}


def resolve_sysfs_i2c_bus(card_dir: Path) -> int | None:
    """Resolves the DDC/CI I²C bus number (/dev/i2c-X) directly from the DRM connector directory in sysfs."""
    # 1. DisplayPort AUX channel exposes an i2c-<N> subdirectory inside the connector directory
    sub_i2c = sorted(card_dir.glob("i2c-*"))
    for candidate in sub_i2c:
        parts = candidate.name.split("-")
        if len(parts) == 2 and parts[1].isdigit():
            return int(parts[1])

    # 2. HDMI/DVI exposes a 'ddc' symlink pointing to '../../../i2c-<N>'
    ddc_link = card_dir / "ddc"
    if ddc_link.exists():
        try:
            target_name = ddc_link.resolve().name
            parts = target_name.split("-")
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
        except OSError:
            pass

    return None


def read_sysfs_drm_displays(drm_root: Path = Path("/sys/class/drm")) -> dict[str, dict[str, object]]:
    """Reads all connected DRM displays including EDID MD5, model, serial, and I²C bus in < 1 ms from sysfs."""
    result: dict[str, dict[str, object]] = {}
    if not drm_root.exists():
        return result

    for card_dir in sorted(drm_root.glob("card*-*")):
        edid_file = card_dir / "edid"
        if not edid_file.exists():
            continue
        try:
            edid_bytes = edid_file.read_bytes()
        except OSError:
            continue
        if len(edid_bytes) < 128:
            continue
        md5_hex = hashlib.md5(edid_bytes).hexdigest()
        if md5_hex == EMPTY_MD5:
            continue

        card_con = card_dir.name
        parts = card_con.split("-", 1)
        if len(parts) != 2:
            continue
        connector = parts[1]

        edid_meta = parse_edid_bytes(edid_bytes)
        i2c_bus = resolve_sysfs_i2c_bus(card_dir)

        result[connector] = {
            "connector": connector,
            "drm_card_connector": card_con,
            "edid_hash": md5_hex,
            "manufacturer": edid_meta["manufacturer"],
            "model": edid_meta["model"],
            "serial": edid_meta["serial"],
            "i2c_bus": i2c_bus,
        }

    return result


def parse_ddcutil_detect_output(raw_output: str) -> list[dict[str, object]]:
    """Parses the text output of `ddcutil detect --brief` (fallback when sysfs EDID is unavailable)."""
    blocks: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m_disp = re.match(r"^Display\s+(\d+)", line)
        if m_disp:
            if current:
                blocks.append(current)
            current = {"display_num": int(m_disp.group(1))}
            continue

        if current is None:
            continue

        if line.startswith("I2C bus:"):
            m_bus = re.search(r"/dev/i2c-(\d+)", line)
            if m_bus:
                current["i2c_bus"] = int(m_bus.group(1))
        elif line.startswith("DRM connector:"):
            drm_con = line.split(":", 1)[1].strip()
            current["drm_card_connector"] = drm_con
            if "-" in drm_con:
                current["connector"] = drm_con.split("-", 1)[1]
        elif line.startswith("Monitor:"):
            mon_str = line.split(":", 1)[1].strip()
            parts = mon_str.split(":")
            current["manufacturer"] = parts[0].strip() if len(parts) > 0 else ""
            current["model"] = parts[1].strip() if len(parts) > 1 else ""
            current["serial"] = parts[2].strip() if len(parts) > 2 else ""

    if current:
        blocks.append(current)

    return blocks


def run_ddcutil_detect() -> list[dict[str, object]]:
    """Runs `ddcutil detect --brief` as a fallback discovery mechanism."""
    ddc_bin = shutil.which("ddcutil")
    if not ddc_bin:
        return []
    try:
        proc = subprocess.run(
            [ddc_bin, "detect", "--brief"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10.0,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_ddcutil_detect_output(proc.stdout)


def discover_displays(
    compositor: CompositorBackend | None = None,
    include_ddc_values: bool = True,
    drm_root: Path = Path("/sys/class/drm"),
) -> list[DisplayInfo]:
    """Merges DRM sysfs (< 1 ms) and Wayland compositor state into a unified DisplayInfo list."""
    comp = compositor or get_compositor_backend()
    sysfs_map = read_sysfs_drm_displays(drm_root=drm_root)
    comp_outputs = comp.get_outputs()

    # Fall back to ddcutil detect only if sysfs did not provide I²C buses
    ddc_by_connector: dict[str, dict[str, object]] = {}
    if not sysfs_map or any(v.get("i2c_bus") is None for v in sysfs_map.values()):
        for entry in run_ddcutil_detect():
            con = str(entry.get("connector", ""))
            if con:
                ddc_by_connector[con] = entry

    all_connectors = sorted(set(sysfs_map.keys()) | set(ddc_by_connector.keys()))

    displays: list[DisplayInfo] = []
    for idx, con in enumerate(all_connectors, start=1):
        sys_info = sysfs_map.get(con, {})
        ddc_info = ddc_by_connector.get(con, {})
        comp_state = comp_outputs.get(con)

        edid_hash = str(sys_info.get("edid_hash") or (comp_state.edid_hash if comp_state else ""))
        i2c_bus = sys_info.get("i2c_bus")
        if i2c_bus is None:
            i2c_bus = ddc_info.get("i2c_bus")

        disp = DisplayInfo(
            connector=con,
            drm_card_connector=str(
                sys_info.get("drm_card_connector") or ddc_info.get("drm_card_connector", "")
            ),
            edid_hash=edid_hash,
            edid_identifier=comp_state.edid_identifier if comp_state else "",
            manufacturer=str(sys_info.get("manufacturer") or ddc_info.get("manufacturer", "")),
            model=str(sys_info.get("model") or ddc_info.get("model", "")),
            serial=str(sys_info.get("serial") or ddc_info.get("serial", "")),
            i2c_bus=i2c_bus,  # type: ignore[arg-type]
            ddc_display_num=int(ddc_info.get("display_num", idx)),  # type: ignore[arg-type]
            width=comp_state.width if comp_state else 0,
            height=comp_state.height if comp_state else 0,
            refresh_hz=comp_state.refresh_hz if comp_state else 60.0,
            scale=comp_state.scale if comp_state else 1.0,
            compositor_uuid=comp_state.uuid if comp_state else "",
            color_profile_source=comp_state.color_profile_source if comp_state else "",
            icc_profile_path=comp_state.icc_profile_path if comp_state else "",
            compositor_brightness=comp_state.brightness if comp_state else 1.0,
            hdr_enabled=comp_state.hdr_enabled if comp_state else False,
            wcg_enabled=comp_state.wcg_enabled if comp_state else False,
        )
        displays.append(disp)

    if include_ddc_values and displays:
        from kcal_ddc.ddc_client import DDCClient

        client = DDCClient()

        def _fetch_ddc(d: DisplayInfo) -> None:
            if d.i2c_bus is not None:
                d.ddc = client.read_state(d.i2c_bus)

        with ThreadPoolExecutor(max_workers=max(1, len(displays))) as pool:
            list(pool.map(_fetch_ddc, displays))

    return displays
