"""Reproducible snapshot of the colour state of all displays (`kcal-cli diag`).

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

from kcal_argyll.instruments import detect_instruments
from kcal_argyll.profile_inspector import inspect_profile
from kcal_argyll.vcgt import read_vcgt
from kcal_core.compositor import get_compositor_backend
from kcal_core.discovery import discover_displays
from kcal_core.models import DisplayInfo
from kcal_core.profile_meta import read_profile_ddc
from kcal_presets.manager import PresetManager, match_display, preset_drift


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


def gpu_color_properties() -> dict[str, Any]:
    """GAMMA_LUT / DEGAMMA_LUT / CTM per CRTC from `drm_info -j` (blob id 0 = not set)."""
    raw = _run(["drm_info", "-j"], timeout=20.0)
    if not raw:
        return {"available": False, "note": "drm_info not installed (Fedora: dnf install drm_info)"}
    try:
        data = json.loads(raw)
    except ValueError:
        return {"available": False, "note": "drm_info output not readable"}
    result: dict[str, Any] = {"available": True, "crtcs": []}
    for card, info in (data.items() if isinstance(data, dict) else []):
        for crtc in info.get("crtcs", []) if isinstance(info, dict) else []:
            props = crtc.get("properties", {})
            picked = {k: props[k].get("value") if isinstance(props.get(k), dict) else props.get(k)
                      for k in ("GAMMA_LUT", "DEGAMMA_LUT", "CTM", "GAMMA_LUT_SIZE") if k in props}
            result["crtcs"].append({"card": card, "id": crtc.get("id"), **picked})
    return result


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
            "profile": profile_info(d.icc_profile_path if d.color_profile_source == "ICC" else "", d),
            "preset_entry": None if entry is None else {
                "ddc": [entry.ddc_brightness, entry.ddc_contrast, entry.ddc_red_gain, entry.ddc_green_gain,
                        entry.ddc_blue_gain],
                "icc": entry.icc_profile,
                "source": entry.color_profile_source,
            },
            "preset_drift": drift.get(d.connector, []),
        })
    return report


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
    if gpu.get("available"):
        for c in gpu["crtcs"]:
            add(f"GPU {c['card']} CRTC {c['id']}: GAMMA_LUT={c.get('GAMMA_LUT')} DEGAMMA_LUT={c.get('DEGAMMA_LUT')} "
                f"CTM={c.get('CTM')} (0 = not set)")
    else:
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
        pe = d["preset_entry"]
        if pe:
            add(f"   Preset : DDC {pe['ddc']} · ICC {Path(pe['icc']).name or '–'}"
                + (f" · DRIFT {', '.join(d['preset_drift'])}" if d["preset_drift"] else " · no drift"))
        m = d.get("measurement")
        if m:
            add(f"   Sensor : white {m['white_cdm2']} cd/m² · {m['white_cct_k']} K · xy {m['white_xy']} · "
                f"Δu′v′ to D65 {m['white_duv_d65']} · black {m['black_cdm2']} cd/m² · contrast {m['contrast']}:1")
    return "\n".join(lines) + "\n"
