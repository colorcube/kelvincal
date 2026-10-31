"""CLI tool `kelvincal-cli` for display diagnostics, preset switching, contrast optimization, and calibration."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from kelvincal.core.compositor import get_compositor_backend
from kelvincal.core.discovery import discover_displays
from kelvincal.core.models import D65_X, D65_Y
from kelvincal.ddc.contrast_optimizer import ContrastOptimizationConfig
from kelvincal.ddc.ddc_client import DDCClient
from kelvincal.gui.controller import CalibrationController, CalibrationObserver, CancelToken
from kelvincal.presets.manager import PresetManager


def cmd_status(args: argparse.Namespace) -> int:
    displays = discover_displays(include_ddc_values=not args.no_ddc)
    if args.json:
        print(json.dumps([asdict(d) for d in displays], indent=2, ensure_ascii=False))
        return 0

    if not displays:
        print("No active displays detected.")
        return 1

    print(f"Detected Displays ({len(displays)}):")
    print("=" * 88)
    for d in displays:
        bus_str = f"/dev/i2c-{d.i2c_bus}" if d.i2c_bus is not None else "n/a"
        icc_name = Path(d.icc_profile_path).name if d.icc_profile_path else "(none)"
        print(f"• {d.display_label}")
        print(f"  EDID Hash (MD5) : {d.edid_hash}")
        print(f"  DRM / I²C Bus   : {d.drm_card_connector}  ->  {bus_str}")
        print(
            f"  Mode / Scale    : {d.width}x{d.height} @ {d.refresh_hz:.0f} Hz (Scale {d.scale})"
        )
        print(
            f"  Color Profile   : [{d.color_profile_source}] {icc_name} "
            f"(Compositor Brightness: {d.compositor_brightness * 100:.0f}%)"
        )
        if not args.no_ddc and d.ddc.brightness is not None:
            print(
                f"  DDC/CI Hardware : Brightness={d.ddc.brightness}% | "
                f"Contrast={d.ddc.contrast}% | "
                f"RGB Gain=({d.ddc.red_gain}, {d.ddc.green_gain}, {d.ddc.blue_gain})"
            )
        print("-" * 88)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from kelvincal.core.setup_check import ERROR, has_errors, run_checks

    checks = run_checks()
    if args.json:
        from dataclasses import asdict

        print(json.dumps([asdict(c) for c in checks], indent=2, ensure_ascii=False))
        return 1 if has_errors(checks) else 0
    marks = {"ok": "✓", "info": "ℹ", "warning": "⚠", "error": "✗"}
    for c in checks:
        print(f"{marks[c.status]} {c.title}")
        if c.detail and c.status != "ok":
            print(f"    {c.detail}")
        for line in c.fix.splitlines():
            print(f"    $ {line}" if c.status != "ok" and not line.endswith(".") else f"    {line}")
    if has_errors(checks):
        print(f"\n{sum(c.status == ERROR for c in checks)} problem(s) prevent KelvinCal from working.")
        return 1
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    from kelvincal.core import recovery

    entries = recovery.interrupted()
    if not entries:
        print("No interrupted measurement found.")
        return 0
    compositor = get_compositor_backend()
    for e in entries:
        profile = e.icc_profile_path if e.color_profile_source == "ICC" else e.color_profile_source
        ddc = f", DDC {'/'.join(map(str, e.ddc))}" if e.ddc else ""
        print(f"{e.connector}: interrupted {e.started} – before: {profile}{ddc}")
        if args.discard:
            recovery.discard(e)
            print("  discarded")
            continue
        recovery.restore(e, compositor, DDCClient())
        print("  restored" + (" (turn HDR on again in System Settings)" if e.hdr_enabled else ""))
    return 0


def cmd_diag(args: argparse.Namespace) -> int:
    from kelvincal.gui import diagnostics

    report = diagnostics.collect()
    for connector in args.measure or []:
        def job(ctl):  # noqa: ANN001, ANN202
            if args.display_type:
                ctl.display_type, ctl.display_type_label = args.display_type, ""
            if args.observer:
                from kelvincal.argyll.spotread_session import SpotreadSession

                ctl.sensor_factory = lambda ccss: SpotreadSession(
                    display_type=ctl.display_type, ccss_path=ccss, observer=args.observer,
                    cancel_check=lambda: ctl.cancel.cancelled)
            return ctl.run_spot_check(args.raw)

        code, res = _run_controller_job(connector, job, args.ccss, args.auto_start)
        if res is not None:
            res.update(observer=args.observer or "1931_2")
        if code != 0 or res is None:
            return code or 1
        for d in report["displays"]:
            if d["connector"] == connector:
                d["measurement"] = res
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str) if args.json \
        else diagnostics.format_text(report)
    print(text, end="" if text.endswith("\n") else "\n")
    if args.output:
        Path(args.output).write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        print(f"Saved to {args.output}")
    return 0


def cmd_list_presets(args: argparse.Namespace) -> int:
    mgr = PresetManager()
    active_name, presets = mgr.load_all()
    if args.json:
        payload = {
            "active_preset": active_name,
            "presets": [p.to_dict() for p in presets],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if not presets:
        print(f"No presets saved in {mgr.config_path} yet.")
        print("Tip: Capture your current setup with:")
        print('  kelvincal-cli capture-preset "Current Setup (Backup)"')
        return 0

    print(f"Saved Presets ({mgr.config_path}):")
    for p in presets:
        marker = "[●]" if p.name == active_name else "[○]"
        desc = f" – {p.description}" if p.description else ""
        print(f"  {marker} {p.name}{desc} ({len(p.displays)} displays)")
        for entry in p.displays:
            icc_short = Path(entry.icc_profile).name if entry.icc_profile else "sRGB"
            print(
                f"      ├─ {entry.connector or entry.edid_hash[:8]} ({entry.model}): "
                f"Bri={entry.ddc_brightness}%, Con={entry.ddc_contrast}%, "
                f"RGB=({entry.ddc_red_gain},{entry.ddc_green_gain},{entry.ddc_blue_gain}), "
                f"ICC={icc_short}"
            )
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    """Presets plus the state of every display and its drift from the active preset (for the plasmoid)."""
    from kelvincal.presets.manager import preset_drift

    mgr = PresetManager()
    active_name, presets = mgr.load_all()
    displays = discover_displays(include_ddc_values=True)
    active = next((p for p in presets if p.name == active_name), None)
    drift = preset_drift(active, displays) if active else {}
    reached, status = _running_gui("Status")
    gui = json.loads(status) if reached and status else {}
    payload = {
        "active_preset": active_name,
        "presets": [{"name": p.name, "description": p.description, "displays": len(p.displays)} for p in presets],
        "displays": [{
            "connector": d.connector,
            "model": d.model,
            "icc": Path(d.icc_profile_path).name if d.color_profile_source == "ICC" and d.icc_profile_path
            else d.color_profile_source or "sRGB",
            "brightness": d.ddc.brightness,
            "ddc": d.i2c_bus is not None,
            "drift": drift.get(d.connector, []),
        } for d in displays],
        "gui": {"running": reached, "busy": bool(gui.get("busy"))},
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"Active preset: {active_name or '-'}" + (" (GUI running, measuring)" if payload["gui"]["busy"] else ""))
    for d in payload["displays"]:
        state = f"drift: {', '.join(d['drift'])}" if d["drift"] else "ok"
        print(f"  {d['connector']:10} {d['model']:16} {d['icc']:50} brightness {d['brightness']}  {state}")
    return 0


def cmd_capture_preset(args: argparse.Namespace) -> int:
    mgr = PresetManager()
    preset = mgr.capture_current_state(
        name=args.name,
        description=args.description or "",
        mark_active=True,
    )
    print(
        f"Preset '{preset.name}' with {len(preset.displays)} displays saved to {mgr.config_path}."
    )
    return 0


def _running_gui(method: str, *call_args: str) -> tuple[bool, str]:
    """Calls the D-Bus interface of a running KelvinCal GUI (see kelvincal.gui.dbus_service)."""
    from PySide6.QtCore import QCoreApplication

    from kelvincal.gui.dbus_service import call_running

    _app = QCoreApplication.instance() or QCoreApplication([])
    return call_running(method, *call_args)


def cmd_apply_preset(args: argparse.Namespace) -> int:
    # A running GUI applies it itself: it refuses while it measures and keeps its view up to date.
    if not args.ddc_only:
        reached, error = _running_gui("ApplyPreset", args.name)
        if reached:
            if error:
                print(error, file=sys.stderr)
                return 1
            print(f"Preset '{args.name}' applied by the running KelvinCal.")
            return 0
    mgr = PresetManager()
    preset = mgr.apply_preset(
        name=args.name,
        apply_compositor=not args.ddc_only,
    )
    print(f"Preset '{preset.name}' applied successfully.")
    return 0


class _PrintObserver(CalibrationObserver):
    """Prints controller progress to stdout (called from the worker thread)."""

    def status(self, message: str) -> None:
        print(message, flush=True)

    def contrast_step(self, step) -> None:  # noqa: ANN001
        state = "CLIPPING" if step.clipped else "OK"
        print(
            f"  Contrast {step.contrast:3d}% -> "
            f"Y_255={step.m_high.Y:6.2f} cd/m² | "
            f"ΔL={step.delta_l_cdm2:5.2f} cd/m² ({step.rel_gain * 100:4.2f}%) | "
            f"Δu'v'={step.delta_uv:.4f} => [{state}] {step.reason}",
            flush=True,
        )

    def whitepoint_reading(self, m, ddc, target_xy=(D65_X, D65_Y)) -> None:  # noqa: ANN001
        x, y = m.xy
        print(
            f"  DDC {tuple(ddc)} -> Y={m.Y:6.2f} cd/m² | xy=({x:.4f}, {y:.4f}) | "
            f"CCT={m.cct_kelvin:.0f} K | Δu'v'(target)={m.delta_uv_to_xy(*target_xy):.4f}",
            flush=True,
        )


def _run_controller_job(connector: str, job, ccss: str | None = None,  # noqa: ANN001, ANN202
                        auto_start: float | None = None):
    """Runs `job(controller)` for `connector` in a worker thread with a Qt patch window.

    Returns (exit_code, result). Ctrl+C cancels the run (DDC values are restored).
    """
    import signal

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QGuiApplication

    from kelvincal.gui.workers import CalibrationThread, QtPatchDisplay

    displays = discover_displays(include_ddc_values=True)
    target = next((d for d in displays if d.connector == connector), None)
    if target is None or target.i2c_bus is None:
        print(f"Display '{connector}' or its I²C bus was not found.", file=sys.stderr)
        return 1, None

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setOrganizationName("kelvincal")   # same settings as the GUI (corrections, visual offsets)
    app.setApplicationName("kelvincal")
    from kelvincal.argyll.instruments import detect_instruments
    from kelvincal.gui.pages.correction import correction_for, measurement_mode, set_instrument

    set_instrument(detect_instruments())   # which corrections and -y modes the instrument offers
    mode, mode_label = measurement_mode(target)
    if ccss is None:
        ccss = correction_for(target)
    elif ccss.lower() == "none":
        ccss = None
    print(f"Spectral correction: {Path(ccss).name if ccss else 'none (instrument default)'}")
    if mode:
        print(f"Measurement mode: {mode_label or '?'} (-y {mode})")
    cancel = CancelToken()
    try:
        patch = QtPatchDisplay(target.connector, cancel, auto_confirm=auto_start)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1, None

    controller = CalibrationController(
        display=target,
        compositor=get_compositor_backend(),
        patch_display=patch,
        observer=_PrintObserver(),
        cancel=cancel,
        ccss_path=ccss,
        display_type=mode,
        display_type_label=mode_label,
    )
    thread = CalibrationThread(controller, job)
    outcome: dict = {"code": 1, "result": None}

    def ok(res) -> None:  # noqa: ANN001
        outcome.update(code=0, result=res)

    thread.succeeded.connect(ok)
    thread.failed.connect(lambda msg: print(f"Error: {msg}", file=sys.stderr))
    thread.cancelled.connect(lambda: print("Cancelled by user."))
    thread.finished.connect(app.quit)

    # Ctrl+C, SIGTERM and SIGHUP cancel the run (the display is restored)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: cancel.cancel())
    # Let the Python interpreter run periodically so the SIGINT handler can fire during app.exec().
    tick = QTimer()
    tick.start(200)
    tick.timeout.connect(lambda: None)

    if auto_start is None:
        print(f"Place the sensor on {target.display_label} and press Space in the patch window (Esc cancels).")
    else:
        print(f"Measuring on {target.display_label} in {auto_start:g} s (sensor must already be placed).")
    thread.start()
    app.exec()
    thread.wait()
    patch.dispose()
    return outcome["code"], outcome["result"]


def cmd_optimize_contrast(args: argparse.Namespace) -> int:
    cfg = ContrastOptimizationConfig(
        min_contrast=args.min_contrast,
        max_contrast=args.max_contrast,
        low_level=args.low_level,
    )
    code, res = _run_controller_job(args.connector, lambda ctl: ctl.run_contrast(cfg), args.ccss, args.auto_start)
    if res is not None:
        print("=" * 72)
        print(
            f"Optimal contrast for {args.connector}: {res.optimal_contrast}% "
            f"(Peak luminance: {res.peak_luminance_cdm2:.1f} cd/m²)"
        )
    return code


def cmd_optimize_whitepoint(args: argparse.Namespace) -> int:
    code, res = _run_controller_job(args.connector, lambda ctl: ctl.run_whitepoint(args.luminance), args.ccss,
                                    args.auto_start)
    if res is not None:
        print("=" * 72)
        print(
            f"Result for {args.connector} after {res.iterations} steps:\n"
            f"  DDC Brightness : {res.brightness}%\n"
            f"  DDC RGB Gains  : R={res.red_gain}, G={res.green_gain}, B={res.blue_gain}\n"
            f"  Luminance / CCT: {res.final_measurement.Y:.2f} cd/m² / {res.final_measurement.cct_kelvin:.0f} K"
        )
    return code


def cmd_batch(args: argparse.Namespace) -> int:
    from kelvincal.argyll.profile_pipeline import ProfileConfig
    from kelvincal.core.targets import batch_targets
    from kelvincal.gui.controller import BatchItem

    keys = [k.strip() for k in args.targets.split(",") if k.strip()]
    known = {t.variant_key: t for t in batch_targets()}
    unknown = [k for k in keys if k not in known]
    if unknown or not keys:
        print(f"Unknown target(s): {', '.join(unknown) or '-'}; available: {', '.join(known)}", file=sys.stderr)
        return 2
    targets = [known[k] for k in keys]
    try:
        given = tuple(float(v) for v in args.white_offset.split(",")) if args.white_offset else None
        if given is not None and len(given) != 2:
            raise ValueError
    except ValueError:
        print(f"--white-offset expects DX,DY (e.g. 0.0026,-0.0062), got '{args.white_offset}'", file=sys.stderr)
        return 2

    def job(ctl: CalibrationController):  # noqa: ANN202
        from kelvincal.gui.white_offset import offset_correction_mismatch, white_offset_for

        d = ctl.display
        # without --white-offset the offset stored by the visual whitepoint matching (GUI) applies
        dx, dy = given if given is not None else white_offset_for(d)
        if (dx, dy) != (0.0, 0.0):
            source = "--white-offset" if given is not None else "stored"
            ctl.observer.status(f"Visual whitepoint offset ({source}): dx {dx:+.4f}, dy {dy:+.4f}")
            if given is None and offset_correction_mismatch(d, ctl.ccss_path):
                ctl.observer.status("WARNING: the stored offset was matched with a different spectral correction.")
        items = [BatchItem(t.key, t.title + (" · D50" if t.is_d50 else ""), t.luminance,
                           (t.whitepoint_xy[0] + dx, t.whitepoint_xy[1] + dy),
                           ProfileConfig(monitor_name=f"{d.connector}_{d.model}_{t.variant_key}", patch_count=t.patch_count,
                                         gamma=t.gamma), t.whitepoint_label, (dx, dy)) for t in targets]
        return ctl.run_batch(items, ContrastOptimizationConfig(), verify=not args.no_verify)

    code, results = _run_controller_job(args.connector, job, args.ccss, args.auto_start)
    if results:
        print("=" * 72)
        for r in results:
            if not r.ok:
                print(f"{r.item.key:10} FAILED: {r.error}")
                continue
            ve = f" · ΔE00 mean {r.verification.mean:.2f} max {r.verification.maximum.delta_e:.2f}" \
                if r.verification and r.verification.maximum else ""
            print(f"{r.item.key:10} DDC {'/'.join(map(str, r.ddc))} · {r.white.cct_kelvin:.0f} K "
                  f"{r.white.Y:.1f} cd/m²{ve}\n{'':10} {r.profile_path}")
        if not all(r.ok for r in results):
            code = 1
    return code


def cmd_make_ccss(args: argparse.Namespace) -> int:
    """Own colorimeter correction (.ccss) for a display, measured with a spectrometer (e.g. i1 Pro)."""
    from kelvincal.argyll.ccss_maker import default_ccss_path
    from kelvincal.argyll.instruments import detect_instruments

    port = args.instrument
    if port is None:
        spectros = detect_instruments().spectrometers()
        if not spectros:
            print("No spectrometer found (connected instruments: see 'spotread -?').", file=sys.stderr)
            return 1
        port, name = spectros[0]
        print(f"Spectrometer: {name} (port {port})")
    if args.output:
        output = Path(args.output)
    else:
        display = next((d for d in discover_displays() if d.connector == args.connector), None)
        output = default_ccss_path(args.connector, display.model if display else "")
    print("The patch window asks for each step: calibration (tile/cap), then placing the instrument on the "
          "screen – confirm with Space there.")
    code, res = _run_controller_job(args.connector, lambda ctl: ctl.run_ccss(port, output, args.technology))
    if res is not None:
        print(f"Saved: {res}\nSpectra: {res.with_suffix('.ti3')}")
    return code


def cmd_verify(args: argparse.Namespace) -> int:
    """ΔE00 verification of whatever profile is active on the display (sRGB test patches)."""
    from kelvincal.core.verification import TOL_GRAY_CHROMA, TOL_MAX, TOL_MEAN, TOL_WHITE_DUV, grade, report_html

    state = get_compositor_backend().get_outputs().get(args.connector)
    label = Path(state.icc_profile_path).name if state and state.icc_profile_path else \
        (state.color_profile_source if state else "?")

    def job(ctl: CalibrationController):  # noqa: ANN202
        from kelvincal.core.profile_meta import read_profile_meta
        from kelvincal.gui.white_offset import white_offset_for

        # target: what the active profile was calibrated to (sidecar), else D65 plus the stored visual offset
        meta = read_profile_meta(state.icc_profile_path) if state and state.icc_profile_path else None
        if meta is not None and meta.whitepoint_xy is not None:
            target, offset = meta.whitepoint_xy, meta.white_offset
        else:
            offset = white_offset_for(ctl.display)
            target = (D65_X + offset[0], D65_Y + offset[1])
        ctl.observer.status(f"Target whitepoint: x {target[0]:.4f}, y {target[1]:.4f}")
        return ctl.run_verification(target, label, offset)

    code, res = _run_controller_job(args.connector, job, args.ccss, args.auto_start)
    if res is None:
        return code or 1
    worst = res.maximum
    summary = {
        "profile": label,
        "mean_de00": round(res.mean, 2),
        "max_de00": round(worst.delta_e, 2) if worst else None,
        "max_patch": worst.patch.display_name if worst else "",
        "gray_chroma_max": round(res.gray_chroma_max, 2),
        "white_cct_k": round(res.white_cct),
        "white_cdm2": round(res.white_xyz[1], 1),
        "target_xy": [round(v, 4) for v in res.target_xy],
        "white_duv_to_target": round(res.white_duv, 4),
        "correction": res.correction,
        "contrast": round(res.contrast) if res.contrast else None,
        "grades": {
            "mean": grade(res.mean, TOL_MEAN), "max": grade(worst.delta_e, TOL_MAX) if worst else "",
            "gray": grade(res.gray_chroma_max, TOL_GRAY_CHROMA), "white": grade(res.white_duv, TOL_WHITE_DUV),
        },
    }
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print("=" * 72)
        print(f"{args.connector} · {label}\n"
              f"  ΔE00 mean {summary['mean_de00']} · max {summary['max_de00']} ({summary['max_patch']})\n"
              f"  gray cast max Δa*b* {summary['gray_chroma_max']}\n"
              f"  white {summary['white_cct_k']} K · {summary['white_cdm2']} cd/m² · Δu′v′ to target "
              f"{summary['white_duv_to_target']} · contrast {summary['contrast']}:1")
    if args.output:
        Path(args.output).write_text(report_html(res), encoding="utf-8")
        print(f"Report saved to {args.output}")
    return code


def cmd_inspect_profile(args: argparse.Namespace) -> int:
    from kelvincal.argyll.profile_inspector import inspect_profile

    insp = inspect_profile(args.profile, ti3_path=args.ti3)
    if args.json:
        payload = {
            "profile_path": str(insp.profile_path),
            "description": insp.description,
            "luminance_cdm2": insp.luminance_cdm2,
            "black_luminance_cdm2": insp.black_luminance_cdm2,
            "contrast_ratio": insp.contrast_ratio,
            "white_cct_kelvin": insp.white_cct_kelvin,
            "white_delta_uv_d65": insp.white_delta_uv_d65,
            "effective_gamma": insp.effective_gamma,
            "total_measured_patches": insp.total_measured_patches,
            "gray_ramp_points": len(insp.gray_ramp),
            "is_clean": insp.is_clean,
            "kinks": [asdict(k) for k in insp.kinks],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"ICC Profile Inspection: {insp.description} ({insp.profile_path.name})")
    print("=" * 72)
    print(
        f"  White Luminance : {insp.luminance_cdm2:.2f} cd/m²"
        if insp.luminance_cdm2 is not None
        else "  White Luminance : n/a"
    )
    print(
        f"  Black Luminance : {insp.black_luminance_cdm2:.4f} cd/m²"
        if insp.black_luminance_cdm2 is not None
        else "  Black Luminance : n/a"
    )
    print(
        f"  Static Contrast : {insp.contrast_ratio:.0f} : 1"
        if insp.contrast_ratio is not None
        else "  Static Contrast : n/a"
    )
    if insp.white_cct_kelvin is not None and insp.white_delta_uv_d65 is not None:
        print(
            f"  Whitepoint      : {insp.white_cct_kelvin:.0f} K (Δu'v' to D65 = {insp.white_delta_uv_d65:.4f})"
        )
    if insp.effective_gamma is not None:
        print(
            f"  Effective Gamma : γ ≈ {insp.effective_gamma:.2f} ({insp.total_measured_patches} patches)"
        )
    if insp.is_clean:
        print("  Curve Check     : ✓ Smooth & monotonic (no kinks detected)")
    else:
        print(f"  Curve Check     : ⚠ {len(insp.kinks)} anomaly/kink(s) detected:")
        for k in insp.kinks:
            print(f"    - [{k.severity.upper()}] {k.message}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kelvincal-cli",
        description="KelvinCal CLI – Wayland display calibration, DDC hardware optimizer, and preset switcher",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show detected displays, DDC registers, and ICC profiles")
    p_status.add_argument("--json", action="store_true", help="Output in JSON format")
    p_status.add_argument("--no-ddc", action="store_true", help="Skip reading live DDC/CI registers")
    p_status.set_defaults(func=cmd_status)

    p_check = sub.add_parser("check", help="Check the setup (ArgyllCMS, ddcutil, I²C and USB access, KWin) "
                             "and show how to fix problems")
    p_check.add_argument("--json", action="store_true", help="Output in JSON format")
    p_check.set_defaults(func=cmd_check)

    p_rec = sub.add_parser("recover", help="Restore displays left in measurement state by an interrupted run")
    p_rec.add_argument("--discard", action="store_true", help="Forget the saved state instead of restoring it")
    p_rec.set_defaults(func=cmd_recover)

    p_diag = sub.add_parser(
        "diag", help="Snapshot of the colour state: KWin settings, DDC values, active ICC (vcgt, white), presets"
    )
    p_diag.add_argument("--measure", action="append", metavar="CONNECTOR",
                        help="Also measure white/black on this display with the sensor (repeatable)")
    p_diag.add_argument("--ccss", default=None, help="Colorimeter correction for --measure")
    p_diag.add_argument("--display-type", default=None, metavar="Y",
                        help="spotread -y display type for --measure (default: the mode chosen for the display in the GUI)")
    p_diag.add_argument("--observer", default=None,
                        help="spotread -Q observer for --measure (needs --ccss), e.g. 2015_2, 1964_10")
    p_diag.add_argument("--raw", action="store_true",
                        help="Measure under ColorGuard (no ICC profile: hardware state only)")
    p_diag.add_argument("--json", action="store_true", help="Output in JSON format")
    p_diag.add_argument("-o", "--output", default=None, help="Also write the report to this file")
    p_diag.set_defaults(func=cmd_diag)

    p_over = sub.add_parser("overview", help="Presets, display states and drift from the active preset")
    p_over.add_argument("--json", action="store_true", help="Output in JSON format (used by the plasmoid)")
    p_over.set_defaults(func=cmd_overview)

    p_list = sub.add_parser("list-presets", help="List all saved display presets")
    p_list.add_argument("--json", action="store_true", help="Output in JSON format")
    p_list.set_defaults(func=cmd_list_presets)

    p_cap = sub.add_parser(
        "capture-preset",
        help="Capture the live state of all connected displays (DDC + ICC) as a preset",
    )
    p_cap.add_argument("name", help="Preset name, e.g. 'Photography (140 cd/m²)'")
    p_cap.add_argument("-d", "--description", default="", help="Optional description")
    p_cap.set_defaults(func=cmd_capture_preset)

    p_apply = sub.add_parser("apply-preset", help="Activate a saved display preset")
    p_apply.add_argument("name", help="Name of the preset to activate")
    p_apply.add_argument(
        "--ddc-only",
        action="store_true",
        help="Apply only DDC hardware values without switching compositor ICC profiles",
    )
    p_apply.set_defaults(func=cmd_apply_preset)

    p_opt_c = sub.add_parser(
        "optimize-contrast",
        help="Find highest unclipped DDC contrast via binary search",
    )
    p_opt_c.add_argument("-c", "--connector", required=True, help="Display connector, e.g. DP-2")
    p_opt_c.add_argument("--ccss", default=None, help="Colorimeter correction (.ccss/.ccmx) passed to spotread -X; "
                         "default: the one assigned to the display in the GUI, 'none' = instrument default")
    p_opt_c.add_argument("--min-contrast", type=int, default=40, help="Minimum contrast (default: 40)")
    p_opt_c.add_argument("--max-contrast", type=int, default=90, help="Maximum contrast (default: 90)")
    p_opt_c.add_argument("--low-level", type=int, default=248, help="Near-white patch level (default: 248)")
    p_opt_c.set_defaults(func=cmd_optimize_contrast)

    p_opt_wp = sub.add_parser(
        "optimize-whitepoint",
        help="Regulate DDC RGB gains and brightness to D65 and target luminance",
    )
    p_opt_wp.add_argument("-c", "--connector", required=True, help="Display connector, e.g. DP-2")
    p_opt_wp.add_argument("--ccss", default=None, help="Colorimeter correction (.ccss/.ccmx) passed to spotread -X; "
                         "default: the one assigned to the display in the GUI, 'none' = instrument default")
    p_opt_wp.add_argument("-l", "--luminance", type=float, default=140.0, help="Target luminance in cd/m²")
    p_opt_wp.set_defaults(func=cmd_optimize_whitepoint)

    p_batch = sub.add_parser(
        "batch",
        help="Calibrate several targets one after another (sensor placed once); profiles are saved with their "
             "DDC values, the display is restored afterwards",
    )
    p_batch.add_argument("-c", "--connector", required=True, help="Display connector, e.g. DP-2")
    p_batch.add_argument("-t", "--targets", required=True,
                         help="Comma-separated target keys: photo, photo_d50, office, srgb, softproof, video, evening, custom")
    p_batch.add_argument("--no-verify", action="store_true", help="Skip the ΔE00 verification of each profile")
    p_batch.add_argument("--ccss", default=None, help="Colorimeter correction (.ccss/.ccmx); "
                         "default: the one assigned to the display in the GUI, 'none' = instrument default")
    p_batch.add_argument("--white-offset", default=None, metavar="DX,DY",
                         help="Visual whitepoint offset in xy added to every target's whitepoint for this display "
                              "(e.g. found by matching it to another display by eye); the target keeps its label. "
                              "Default: the offset stored by the visual whitepoint matching in the GUI; 0,0 disables it")
    p_batch.set_defaults(func=cmd_batch)

    p_verify = sub.add_parser("verify", help="ΔE00 verification of the active profile (sRGB test patches)")
    p_verify.add_argument("-c", "--connector", required=True, help="Display connector, e.g. DP-2")
    p_verify.add_argument("--ccss", default=None, help="Colorimeter correction (.ccss/.ccmx)")
    p_verify.add_argument("--json", action="store_true", help="Output in JSON format")
    p_verify.add_argument("-o", "--output", default=None, help="Write the HTML report to this file")
    p_verify.set_defaults(func=cmd_verify)

    p_ccss = sub.add_parser(
        "make-ccss",
        help="Own colorimeter correction (.ccss) for a display, measured with a spectrometer (e.g. i1 Pro); "
             "use it afterwards with --ccss",
    )
    p_ccss.add_argument("-c", "--connector", required=True, help="Display connector, e.g. DP-2")
    p_ccss.add_argument("--instrument", type=int, default=None,
                        help="Port number of the spectrometer (spotread -?); default: the first spectrometer")
    p_ccss.add_argument("-t", "--technology", default="u", help="ccxxmake -t display technology code (label only)")
    p_ccss.add_argument("-o", "--output", default=None,
                        help="Output .ccss (default: ~/.local/share/ArgyllCMS/KelvinCal_<connector>_<model>_<date>.ccss)")
    p_ccss.set_defaults(func=cmd_make_ccss)

    for p in (p_diag, p_opt_c, p_opt_wp, p_batch, p_verify):
        p.add_argument("--auto-start", type=float, default=None, metavar="SECONDS",
                       help="Unattended: start measuring after SECONDS without waiting for Space "
                            "(sensor must already be placed)")

    p_insp = sub.add_parser(
        "inspect-profile",
        help="Inspect an ICC profile (and optional .ti3 file) for tone curves, contrast, and kinks",
    )
    p_insp.add_argument("profile", help="Path to the .icc profile")
    p_insp.add_argument("--ti3", default=None, help="Optional path to external .ti3 file")
    p_insp.add_argument("--json", action="store_true", help="Output in JSON format")
    p_insp.set_defaults(func=cmd_inspect_profile)

    return parser


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtCore import QLocale

    QLocale.setDefault(QLocale.c())   # the CLI stays English, numbers with a decimal point
    from kelvincal.core import recovery

    recovery.enable()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
