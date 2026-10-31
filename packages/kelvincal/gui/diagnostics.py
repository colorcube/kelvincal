"""Reproducible snapshot of the colour state of all displays (`kelvincal-cli diag`).

Collects what determines what a display shows, so that calibrations (KelvinCal, DisplayCAL, …) can be
compared under known conditions:
- system: kernel, KWin, tool versions
- per output: KWin colour settings (profile source, ICC, HDR/WCG, brightness), live DDC/CI values
- active ICC profile: white point, luminance, vcgt calibration curves, stored KelvinCal hardware state
- preset: the active preset's entry for the display and any drift
- GPU: gamma/CTM properties if `drm_info` is installed
- optional: white/black measured with the sensor in the current state (see `measure`)
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from kelvincal.argyll.instruments import detect_instruments
from kelvincal.argyll.profile_inspector import inspect_profile
from kelvincal.argyll.vcgt import read_vcgt
from kelvincal.core.compositor import get_compositor_backend
from kelvincal.core.discovery import discover_displays
from kelvincal.core.models import DisplayInfo
from kelvincal.core.profile_meta import read_profile_ddc
from kelvincal.presets.manager import PresetManager, match_display, preset_drift


def _run(cmd: list[str], timeout: float = 10.0) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or out.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def system_info() -> dict[str, Any]:
    instruments = detect_instruments()
    return {
        "kernel": platform.release(),
        "kwin": _run(["kwin_wayland", "--version"]),
        "ddcutil": _run(["ddcutil", "--version"]).splitlines()[0] if shutil.which("ddcutil") else "",
        "argyll": f"ArgyllCMS {instruments.argyll_version}" if instruments.argyll_version else "",
        "instruments": instruments.instruments,
        "drm_info": bool(shutil.which("drm_info")),
    }


def read_drm_blob(card: str, blob_id: int) -> bytes:
    """Contents of a DRM property blob (DRM_IOCTL_MODE_GETPROPBLOB; no DRM master needed)."""
    import ctypes
    import fcntl
    import struct

    request = (3 << 30) | (16 << 16) | (ord("d") << 8) | 0xAC     # _IOWR('d', 0xAC, struct drm_mode_get_blob)
    with open(card, "rb") as f:
        head = bytearray(struct.pack("IIQ", blob_id, 0, 0))
        fcntl.ioctl(f.fileno(), request, head)
        length = struct.unpack("IIQ", head)[1]
        buf = ctypes.create_string_buffer(length)
        head = bytearray(struct.pack("IIQ", blob_id, length, ctypes.addressof(buf)))
        fcntl.ioctl(f.fileno(), request, head)
        return buf.raw


def lut_summary(data: bytes) -> dict[str, Any]:
    """Summary of a `struct drm_color_lut` array (u16 R, G, B, reserved per entry)."""
    import struct

    n = len(data) // 8
    lut = [[v / 65535 for v in struct.unpack_from("<HHH", data, 8 * i)] for i in range(n)]
    dev = max((abs(v - i / (n - 1)) for i, e in enumerate(lut) for v in e), default=0.0) if n > 1 else 0.0
    return {
        "entries": n,
        "black_rgb": [round(v, 4) for v in lut[0]] if n else None,
        "mid_rgb": [round(v, 4) for v in lut[n // 2]] if n else None,
        "white_rgb": [round(v, 4) for v in lut[-1]] if n else None,
        "max_deviation_from_linear": round(dev, 4),
        "identity": dev < 0.002,
        "curves": [[e[ch] for e in lut] for ch in range(3)],   # dropped from the report, used for comparisons
    }


def _connector_names(card: str) -> dict[int, str]:
    """DRM connector id → connector name ("DP-2") from sysfs."""
    names: dict[int, str] = {}
    prefix = Path(card).name + "-"
    for entry in Path("/sys/class/drm").glob(prefix + "*"):
        try:
            names[int((entry / "connector_id").read_text().strip())] = entry.name[len(prefix):]
        except (OSError, ValueError):
            continue
    return names


def gpu_color_properties() -> dict[str, Any]:
    """GAMMA_LUT / DEGAMMA_LUT / CTM per connector from `drm_info -j` (blob id 0 = not set); the GAMMA_LUT
    contents are read directly from the kernel."""
    raw = _run(["drm_info", "-j"], timeout=20.0)
    if not raw:
        return {"available": False, "note": "drm_info not installed (Fedora: dnf install drm_info)"}
    try:
        data = json.loads(raw)
    except ValueError:
        return {"available": False, "note": "drm_info output not readable"}
    result: dict[str, Any] = {"available": True, "outputs": {}}
    for card, info in (data.items() if isinstance(data, dict) else []):
        if not isinstance(info, dict):
            continue
        names = _connector_names(card)
        crtcs = {c.get("id"): c.get("properties", {}) for c in info.get("crtcs", [])}
        for conn in info.get("connectors", []):
            crtc_id = conn.get("properties", {}).get("CRTC_ID", {}).get("raw_value")
            if not crtc_id or crtc_id not in crtcs:
                continue
            props = crtcs[crtc_id]
            value = {k: props[k].get("raw_value") for k in ("GAMMA_LUT", "DEGAMMA_LUT", "CTM") if k in props}
            entry: dict[str, Any] = {"card": card, "crtc": crtc_id, **value}
            if value.get("GAMMA_LUT"):
                try:
                    entry["gamma_lut"] = lut_summary(read_drm_blob(card, value["GAMMA_LUT"]))
                except OSError as exc:
                    entry["gamma_lut_error"] = str(exc)
            result["outputs"][names.get(conn.get("id"), str(conn.get("id")))] = entry
    return result


def compare_lut_vcgt(lut_curves: list[list[float]], vcgt) -> float:  # noqa: ANN001
    """Largest difference between the GPU gamma LUT and the profile's vcgt (interpolated)."""
    m = vcgt.size
    diff = 0.0
    for ch in range(3):
        curve, n = lut_curves[ch], len(lut_curves[ch])
        for i, value in enumerate(curve):
            pos = i / max(1, n - 1) * (m - 1)
            j = min(int(pos), m - 2)
            frac = pos - j
            expected = vcgt.curves[ch][j] * (1 - frac) + vcgt.curves[ch][j + 1] * frac
            diff = max(diff, abs(value - expected))
    return diff


def profile_info(path: str, display: DisplayInfo | None) -> dict[str, Any]:
    if not path:
        return {"path": "", "note": "no ICC profile active"}
    p = Path(path)
    info: dict[str, Any] = {"path": path, "exists": p.is_file()}
    if not p.is_file():
        return info
    try:
        insp = inspect_profile(p)
        info.update(
            description=insp.description,
            white_cct_k=round(insp.white_cct_kelvin or 0),
            white_xy=[round(v, 4) for v in insp.white_xy] if insp.white_xy else None,
            white_duv_d65=round(insp.white_delta_uv_d65 or 0, 4),
            luminance_cdm2=round(insp.luminance_cdm2 or 0, 1),
            effective_gamma=round(insp.effective_gamma or 0, 3),
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must not fail
        info["error"] = str(exc)
    vcgt = read_vcgt(p)
    info["vcgt"] = None if vcgt is None else {
        "entries": vcgt.size,
        "white_rgb": [round(v, 4) for v in vcgt.white],
        "max_deviation_from_linear": round(vcgt.max_deviation, 4),
        "identity": vcgt.is_identity,
    }
    stored = read_profile_ddc(p)
    info["kelvincal_ddc"] = list(stored) if stored else None
    if stored and display is not None:
        live = [display.ddc.brightness, display.ddc.contrast, display.ddc.red_gain, display.ddc.green_gain,
                display.ddc.blue_gain]
        info["ddc_matches_profile"] = live == list(stored)
    return info


def collect() -> dict[str, Any]:
    """Everything except sensor measurements; reads only, changes nothing."""
    compositor = get_compositor_backend()
    displays = discover_displays(compositor=compositor, include_ddc_values=True)
    try:
        outputs = compositor.get_outputs()
    except Exception as exc:  # noqa: BLE001
        outputs = {}
        compositor_error = str(exc)
    else:
        compositor_error = ""
    active_name, presets = PresetManager().load_all()
    active = next((p for p in presets if p.name == active_name), None)
    drift = preset_drift(active, displays) if active else {}
    report: dict[str, Any] = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "system": system_info(),
        "compositor": {"name": compositor.name, "error": compositor_error},
        "active_preset": active_name,
        "gpu": gpu_color_properties(),
        "displays": [],
    }
    for d in displays:
        state = outputs.get(d.connector)
        entry = None
        if active:
            entry = next((e for e in active.displays if match_display(e, [d]) is d), None)
        report["displays"].append({
            "connector": d.connector,
            "model": d.model,
            "serial": d.serial,
            "edid_hash": d.edid_hash,
            "i2c_bus": d.i2c_bus,
            "mode": f"{d.width}x{d.height}@{d.refresh_hz:g}Hz scale {d.scale:g}",
            "kwin": asdict(state) if state else None,
            "ddc": {"brightness": d.ddc.brightness, "contrast": d.ddc.contrast, "red_gain": d.ddc.red_gain,
                    "green_gain": d.ddc.green_gain, "blue_gain": d.ddc.blue_gain},
            "profile": profile_info(report_profile_path(d), d),
            "preset_entry": None if entry is None else {
                "ddc": [entry.ddc_brightness, entry.ddc_contrast, entry.ddc_red_gain, entry.ddc_green_gain,
                        entry.ddc_blue_gain],
                "icc": entry.icc_profile,
                "source": entry.color_profile_source,
            },
            "preset_drift": drift.get(d.connector, []),
            "gpu": _gpu_for(report["gpu"], d.connector, report_profile_path(d)),
        })
    for out in report["gpu"].get("outputs", {}).values():
        if "gamma_lut" in out:
            out["gamma_lut"].pop("curves", None)
    return report


def report_profile_path(d: DisplayInfo) -> str:
    return d.icc_profile_path if d.color_profile_source == "ICC" else ""


def _gpu_for(gpu: dict[str, Any], connector: str, icc: str) -> dict[str, Any] | None:
    out = gpu.get("outputs", {}).get(connector)
    if out is None:
        return None
    result = {k: v for k, v in out.items() if k != "gamma_lut"}
    lut = out.get("gamma_lut")
    if lut:
        result["gamma_lut"] = {k: v for k, v in lut.items() if k != "curves"}
        vcgt = read_vcgt(icc) if icc and Path(icc).is_file() else None
        if vcgt is not None:
            result["gamma_lut"]["max_diff_to_vcgt"] = round(compare_lut_vcgt(lut["curves"], vcgt), 4)
    return result


def format_text(report: dict[str, Any]) -> str:
    """Human-readable version of `collect()` (+ optional measurement)."""
    lines: list[str] = []
    add = lines.append
    sysinfo = report["system"]
    add(f"KelvinCal diagnostics · {report['created']}")
    add(f"Kernel {sysinfo['kernel']} · {sysinfo['kwin'] or 'KWin ?'} · {sysinfo['ddcutil'] or 'ddcutil ?'}")
    add(f"{sysinfo['argyll'] or 'ArgyllCMS ?'} · sensor: {', '.join(sysinfo['instruments']) or 'none'} · "
        f"compositor backend: {report['compositor']['name']}"
        + (f" (error: {report['compositor']['error']})" if report["compositor"]["error"] else ""))
    add(f"Active preset: {report['active_preset'] or '–'}")
    gpu = report["gpu"]
    if not gpu.get("available"):
        add(f"GPU colour pipeline: {gpu.get('note')}")
    for d in report["displays"]:
        add("")
        add(f"== {d['connector']} · {d['model']} · SN {d['serial'] or '–'} · {d['mode']}")
        k = d["kwin"]
        if k:
            add(f"   KWin   : source {k['color_profile_source']} · ICC {Path(k['icc_profile_path']).name or '–'} · "
                f"HDR {'on' if k['hdr_enabled'] else 'off'} · WCG {'on' if k['wcg_enabled'] else 'off'} · "
                f"brightness {k['brightness']:.2f} · SDR brightness {k['sdr_brightness']} · "
                f"DDC allowed {'yes' if k['allow_ddc_ci'] else 'no'}")
            if k["allow_ddc_ci"] and d["ddc"]["brightness"] is not None \
                    and round(k["brightness"] * 100) == d["ddc"]["brightness"]:
                add("            note: KWin's brightness equals DDC brightness – KWin controls VCP 0x10 itself and "
                    "may overwrite values set by a calibration")
        ddc = d["ddc"]
        add(f"   DDC    : brightness {ddc['brightness']} · contrast {ddc['contrast']} · "
            f"RGB {ddc['red_gain']}/{ddc['green_gain']}/{ddc['blue_gain']}"
            + ("" if d["i2c_bus"] is not None else " (no DDC/CI)"))
        pr = d["profile"]
        if pr.get("path"):
            add(f"   Profile: {Path(pr['path']).name}" + ("" if pr.get("exists") else " (FILE MISSING)"))
            if "white_cct_k" in pr:
                add(f"            white in profile {pr['white_cct_k']} K · xy {pr['white_xy']} · "
                    f"Δu′v′ to D65 {pr['white_duv_d65']} · γ {pr['effective_gamma']}")
            v = pr.get("vcgt")
            if v is None:
                add("            vcgt: none")
            else:
                add(f"            vcgt: {v['entries']} entries · white RGB {v['white_rgb']} · max deviation "
                    f"{v['max_deviation_from_linear']} {'(identity)' if v['identity'] else ''}")
            if pr.get("kelvincal_ddc"):
                match = pr.get("ddc_matches_profile")
                add(f"            measured with DDC {pr['kelvincal_ddc']} → live DDC "
                    + ("MATCHES" if match else "DIFFERS (profile does not describe the current hardware state)"))
        else:
            add(f"   Profile: {pr.get('note')}")
        g = d.get("gpu")
        if g:
            lut = g.get("gamma_lut")
            parts = [f"CRTC {g['crtc']}"]
            if lut:
                parts.append(f"GAMMA_LUT {lut['entries']} entries · black {lut['black_rgb']} · mid {lut['mid_rgb']} · "
                             f"white {lut['white_rgb']} · max deviation {lut['max_deviation_from_linear']}"
                             + (" (identity)" if lut["identity"] else ""))
                if "max_diff_to_vcgt" in lut:
                    parts.append(f"differs from the profile's vcgt by {lut['max_diff_to_vcgt']}"
                                 + (" (= vcgt)" if lut["max_diff_to_vcgt"] < 0.003 else " (not the vcgt)"))
            else:
                parts.append("GAMMA_LUT not set" if not g.get("gamma_lut_error") else
                             f"GAMMA_LUT unreadable: {g['gamma_lut_error']}")
            parts.append(f"DEGAMMA_LUT {'set' if g.get('DEGAMMA_LUT') else 'not set'} · "
                         f"CTM {'set' if g.get('CTM') else 'not set'}")
            add("   GPU    : " + " · ".join(parts))
        pe = d["preset_entry"]
        if pe:
            add(f"   Preset : DDC {pe['ddc']} · ICC {Path(pe['icc']).name or '–'}"
                + (f" · DRIFT {', '.join(d['preset_drift'])}" if d["preset_drift"] else " · no drift"))
        m = d.get("measurement")
        if m:
            add(f"   Sensor : white {m['white_cdm2']} cd/m² · {m['white_cct_k']} K · xy {m['white_xy']} · "
                f"Δu′v′ to D65 {m['white_duv_d65']} · black {m['black_cdm2']} cd/m² · contrast {m['contrast']}:1")
    return "\n".join(lines) + "\n"
