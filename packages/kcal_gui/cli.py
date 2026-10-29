"""CLI tool `kcal-cli` for display diagnostics, preset switching, contrast optimization, and calibration."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from kcal_core.compositor import get_compositor_backend
from kcal_core.discovery import discover_displays
from kcal_ddc.contrast_optimizer import ContrastOptimizationConfig
from kcal_gui.controller import CalibrationController, CalibrationObserver, CancelToken
from kcal_presets.manager import PresetManager


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
        print('  kcal-cli capture-preset "Current Setup (Backup)"')
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


def cmd_apply_preset(args: argparse.Namespace) -> int:
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

    def whitepoint_reading(self, m, ddc) -> None:  # noqa: ANN001
        x, y = m.xy
        print(
            f"  DDC {tuple(ddc)} -> Y={m.Y:6.2f} cd/m² | xy=({x:.4f}, {y:.4f}) | "
            f"CCT={m.cct_kelvin:.0f} K | Δu'v'(D65)={m.delta_uv_to_d65():.4f}",
            flush=True,
        )


def _run_controller_job(connector: str, job):  # noqa: ANN001, ANN202
    """Runs `job(controller)` for `connector` in a worker thread with a Qt patch window.

    Returns (exit_code, result). Ctrl+C cancels the run (DDC values are restored).
    """
    import signal

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QGuiApplication

    from kcal_gui.workers import CalibrationThread, QtPatchDisplay

    displays = discover_displays(include_ddc_values=True)
    target = next((d for d in displays if d.connector == connector), None)
    if target is None or target.i2c_bus is None:
        print(f"Display '{connector}' or its I²C bus was not found.", file=sys.stderr)
        return 1, None

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    cancel = CancelToken()
    try:
        patch = QtPatchDisplay(target.connector, cancel)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1, None

    controller = CalibrationController(
        display=target,
        compositor=get_compositor_backend(),
        patch_display=patch,
        observer=_PrintObserver(),
        cancel=cancel,
    )
    thread = CalibrationThread(controller, job)
    outcome: dict = {"code": 1, "result": None}

    def ok(res) -> None:  # noqa: ANN001
        outcome.update(code=0, result=res)

    thread.succeeded.connect(ok)
    thread.failed.connect(lambda msg: print(f"Error: {msg}", file=sys.stderr))
    thread.cancelled.connect(lambda: print("Cancelled by user."))
    thread.finished.connect(app.quit)

    signal.signal(signal.SIGINT, lambda *_: cancel.cancel())
    # Let the Python interpreter run periodically so the SIGINT handler can fire during app.exec().
    tick = QTimer()
    tick.start(200)
    tick.timeout.connect(lambda: None)

    print(f"Place the sensor on {target.display_label} and press Space in the patch window (Esc cancels).")
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
    code, res = _run_controller_job(args.connector, lambda ctl: ctl.run_contrast(cfg))
    if res is not None:
        print("=" * 72)
        print(
            f"Optimal contrast for {args.connector}: {res.optimal_contrast}% "
            f"(Peak luminance: {res.peak_luminance_cdm2:.1f} cd/m²)"
        )
    return code


def cmd_optimize_whitepoint(args: argparse.Namespace) -> int:
    code, res = _run_controller_job(args.connector, lambda ctl: ctl.run_whitepoint(args.luminance))
    if res is not None:
        print("=" * 72)
        print(
            f"Result for {args.connector} after {res.iterations} steps:\n"
            f"  DDC Brightness : {res.brightness}%\n"
            f"  DDC RGB Gains  : R={res.red_gain}, G={res.green_gain}, B={res.blue_gain}\n"
            f"  Luminance / CCT: {res.final_measurement.Y:.2f} cd/m² / {res.final_measurement.cct_kelvin:.0f} K"
        )
    return code


def cmd_inspect_profile(args: argparse.Namespace) -> int:
    from kcal_argyll.profile_inspector import inspect_profile

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
            print(f"    - [{k.severity.upper()}] {k.message_en}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kcal-cli",
        description="KelvinCal CLI – Wayland display calibration, DDC hardware optimizer, and preset switcher",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show detected displays, DDC registers, and ICC profiles")
    p_status.add_argument("--json", action="store_true", help="Output in JSON format")
    p_status.add_argument("--no-ddc", action="store_true", help="Skip reading live DDC/CI registers")
    p_status.set_defaults(func=cmd_status)

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
    p_opt_c.add_argument("--min-contrast", type=int, default=40, help="Minimum contrast (default: 40)")
    p_opt_c.add_argument("--max-contrast", type=int, default=90, help="Maximum contrast (default: 90)")
    p_opt_c.add_argument("--low-level", type=int, default=248, help="Near-white patch level (default: 248)")
    p_opt_c.set_defaults(func=cmd_optimize_contrast)

    p_opt_wp = sub.add_parser(
        "optimize-whitepoint",
        help="Regulate DDC RGB gains and brightness to D65 and target luminance",
    )
    p_opt_wp.add_argument("-c", "--connector", required=True, help="Display connector, e.g. DP-2")
    p_opt_wp.add_argument("-l", "--luminance", type=float, default=140.0, help="Target luminance in cd/m²")
    p_opt_wp.set_defaults(func=cmd_optimize_whitepoint)

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
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
