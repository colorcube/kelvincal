"""Renders the screenshots for the README and the manual (docs/images/) from the real widgets.

Runs offscreen with simulated displays, instrument, presets and measurements, so the pictures can be
regenerated after every UI change and never show the data of the machine they are made on:

    tools/screenshots.py [--profile some.icc] [--lang en|de] [--out docs/images]

`--profile` shows a real KelvinCal profile in the inspector instead of a synthetic one.
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QEventLoop, QRect, QSettings, QTimer  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

SIZE = (1280, 800)
USAGE = """Measure spot values, Version 3.4.1
 -c listno            Set instrument port from the following list (default 1)
    1 = '/dev/bus/usb/003/112 (X-Rite i1 DisplayPro, ColorMunki Display)'
 -y n                  i1D3: Non-Refresh display [Default,CB1]
    r|c                i1D3: Refresh display [CB2]
 -I illum             Set simulated instrument illumination
"""


def spin(ms: int = 150) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def save(widget: QWidget, out: Path, name: str) -> None:
    spin()
    path = out / f"{name}.png"
    widget.grab().save(str(path))
    print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def sample_displays(**_kw):  # noqa: ANN201, ANN003
    from kelvincal.core.models import DDCState, DisplayInfo

    return [
        DisplayInfo(connector="DP-1", drm_card_connector="card1-DP-1", edid_hash="1d0c", manufacturer="DEL",
                    model="DELL U2723QE", i2c_bus=7, ddc=DDCState(32, 75, 100, 96, 93), width=3840, height=2160,
                    color_profile_source="ICC", icc_profile_path="/icc/KelvinCal_DP-1_DELL_U2723QE_office.icc"),
        DisplayInfo(connector="DP-2", drm_card_connector="card1-DP-2", edid_hash="2e1d", manufacturer="ENC",
                    model="EIZO CS2740", i2c_bus=8, ddc=DDCState(28, 70, 98, 100, 95), width=3840, height=2160,
                    color_profile_source="ICC", icc_profile_path="/icc/KelvinCal_DP-2_EIZO_CS2740_office.icc"),
        DisplayInfo(connector="HDMI-A-1", drm_card_connector="card1-HDMI-A-1", edid_hash="3f2e", model="LG TV",
                    width=1920, height=1080, color_profile_source="sRGB"),
    ]


def sample_geometries() -> dict[str, QRect]:
    return {"DP-1": QRect(0, 0, 2560, 1440), "DP-2": QRect(2560, 0, 2560, 1440),
            "HDMI-A-1": QRect(5120, 360, 1920, 1080)}


def write_presets(path: Path) -> None:
    from kelvincal.core.models import DisplayPresetEntry, Preset
    from kelvincal.presets.manager import PresetManager

    def entries(b1: int, b2: int, icc: str) -> list[DisplayPresetEntry]:
        return [DisplayPresetEntry("1d0c", "DP-1", "DELL U2723QE", "", b1, 75, 100, 96, 93,
                                   f"/icc/KelvinCal_DP-1_DELL_U2723QE_{icc}.icc"),
                DisplayPresetEntry("2e1d", "DP-2", "EIZO CS2740", "", b2, 70, 98, 100, 95,
                                   f"/icc/KelvinCal_DP-2_EIZO_CS2740_{icc}.icc")]

    presets = [
        Preset("Office, web & everyday · 140 cd/m² · D65", "KelvinCal", entries(32, 28, "office")),
        Preset("Photo editing · 120 cd/m² · D65", "KelvinCal", entries(24, 21, "photo")),
        Preset("Print soft proof · 80 cd/m² · D50", "KelvinCal", entries(12, 10, "softproof")),
        Preset("Evening · 80 cd/m² · 5000 K", "KelvinCal", entries(10, 9, "evening")),
    ]
    PresetManager(config_path=path).save_all(presets, presets[0].name)


class FakeCompositor:
    name = "kwin"

    def get_outputs(self) -> dict:
        return {}

    def __getattr__(self, _name: str):  # noqa: ANN204 - every other call does nothing
        return lambda *a, **k: []


def sample_verification(profile_label: str):  # noqa: ANN201
    """A well calibrated display: small, deterministic deviations from sRGB (grays nearly neutral)."""
    from kelvincal.core.verification import evaluate, srgb_to_xyz, test_patches

    def measured(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
        x, y, z = srgb_to_xyz(rgb)
        gray = max(rgb) - min(rgb) <= 2
        wobble = (0.003 if gray else 0.009) * math.sin(rgb[0] * 0.07 + rgb[1] * 0.03 + rgb[2] * 0.05)
        return (x * 120 * (1 + wobble), y * 120, z * 120 * (1 - wobble))

    patches = test_patches()
    black = (0.0475, 0.05, 0.0545)   # neutral, 2400 : 1
    return evaluate(patches, [measured(p.rgb) for p in patches], measured((255,) * 3), black,
                    (0.3127, 0.3290), profile_label, "DP-2")


def simulate_run(page) -> None:  # noqa: ANN001
    """A full calibration in phase 2: contrast search and whitepoint iterations done, patches running."""
    from kelvincal.core.models import ColorMeasurement, ContrastStepResult

    page.begin("DP-2 · EIZO CS2740 · Photo editing · 120 cd/m² · D65", "DP-2", ("1a", "1b", "2", "3"), (0, 100))
    page.on_phase_started("1a")
    for contrast, clipped in ((50, False), (75, False), (88, True), (81, True), (78, False), (79, True)):
        hi = ColorMeasurement((255,) * 3, 114.0, 120.0 + contrast / 10, 130.0)
        lo = ColorMeasurement((248,) * 3, 108.0, 113.0, 123.0)
        page.on_contrast_step(ContrastStepResult(contrast, lo, hi, hi.Y - lo.Y, (hi.Y - lo.Y) / hi.Y, 0.001,
                                                 clipped, ""))
    page.on_phase_finished("1a")
    page.on_phase_started("1b")
    for b, r, g, bl, x, y, lum in ((40, 100, 100, 100, 0.3050, 0.3270, 151.0), (31, 100, 96, 94, 0.3110, 0.3300, 128.4),
                                   (29, 98, 95, 93, 0.3124, 0.3292, 121.2), (28, 98, 95, 92, 0.3127, 0.3290, 120.1)):
        page.on_whitepoint(ColorMeasurement((255,) * 3, x / y * lum, lum, (1 - x - y) / y * lum), (b, r, g, bl))
    page.on_phase_finished("1b")
    page.on_phase_started("2")
    for i in range(1, 112):
        v = (i * 37) % 256
        page.on_patch((v, (v * 3) % 256, (v * 7) % 256), i, 175)
        page.on_progress("2", i, 175)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", type=Path, help="ICC profile shown in the inspector")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "images")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    os.environ["KELVINCAL_LANG"] = args.lang

    tmp = tempfile.TemporaryDirectory()
    os.environ["KELVINCAL_PRESETS_PATH"] = str(Path(tmp.name) / "presets.json")
    os.environ["XDG_DATA_HOME"] = str(Path(tmp.name) / "data")   # no profiles/corrections of this machine
    app = QApplication(sys.argv)
    app.setApplicationName("kelvincal")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tmp.name)
    QSettings().setValue("setup/check_on_start", False)

    from kelvincal.argyll.instruments import parse_spotread_usage
    from kelvincal.argyll.profile_inspector import inspect_profile
    from kelvincal.core.i18n import translate
    from kelvincal.core.setup_check import OK, Check
    from kelvincal.core.targets import TARGETS
    import kelvincal.gui.main_window as mw
    import kelvincal.gui.pages.monitors_simple as simple
    from kelvincal.gui.i18n_setup import install_translators
    from kelvincal.gui.inspector import InspectorDialog
    from kelvincal.gui.setup_dialog import SetupCheckDialog
    from kelvincal.gui.theme import ThemeManager

    app._translators = install_translators(app)  # type: ignore[attr-defined]
    write_presets(Path(os.environ["KELVINCAL_PRESETS_PATH"]))
    if args.profile:
        profile = args.profile
    else:
        from test_profile_inspector import _build_minimal_icc_bytes, _build_synthetic_ti3

        profile = Path(tmp.name) / "KelvinCal_DP-2_EIZO_CS2740_photo.icc"
        profile.write_bytes(_build_minimal_icc_bytes(_build_synthetic_ti3()))

    status = parse_spotread_usage(USAGE)
    with mock.patch.object(mw, "discover_displays", sample_displays), \
            mock.patch.object(mw, "detect_instruments", lambda: status), \
            mock.patch.object(mw, "get_compositor_backend", FakeCompositor), \
            mock.patch.object(simple, "screen_geometries", sample_geometries):
        theme = ThemeManager(app)
        win = mw.KelvinCalMainWindow(theme)
        win.resize(*SIZE)
        win.show()
        spin(600)
        win.select_display("DP-2")
        for scheme, icons in (("BreezeLight", "breeze"), ("BreezeDark", "breeze-dark")):
            theme.apply(scheme, save=False)
            QIcon.setThemeName(icons)
            suffix = "dark" if scheme == "BreezeDark" else "light"
            win._show_nav(mw.NAV_MONITORS)
            win.set_mode(0)
            photo = next((t for t in TARGETS if t.key == "photo"), None)
            if photo is not None and hasattr(win.page_simple, "select_target"):
                win.page_simple.select_target(photo.key)
            save(win, args.out, f"simple-{suffix}")
            win.set_mode(1)
            save(win, args.out, f"expert-{suffix}")
            win._show_nav(mw.NAV_PRESETS)
            save(win, args.out, f"presets-{suffix}")
            win._show_nav(mw.NAV_MONITORS)   # as _start_job does: title, running page, navigation locked
            simulate_run(win.page_running)
            win.page_title.setText(translate("MainWindow", "Calibration"))
            win.stack.setCurrentWidget(win.page_running)
            win._set_job_running(True)
            save(win, args.out, f"running-{suffix}")
            win._set_job_running(False)

            dlg = InspectorDialog(inspect_profile(profile), connector="DP-2",
                                  display=sample_displays()[1], parent=win)
            dlg.resize(1180, 780)
            dlg.show()
            save(dlg, args.out, f"inspector-{suffix}")
            dlg.verification.set_result(sample_verification(profile.name))
            dlg.seg_page.setCurrentIndex(1)
            save(dlg, args.out, f"verification-{suffix}")
            dlg.reject()

            checks = [Check("argyll", OK, "ArgyllCMS 3.4.1"), Check("ddcutil", OK, "ddcutil 2.2.1"),
                      Check("i2c", OK, "DDC/CI works on 2 display(s)"),
                      Check("instrument", OK, "Measuring instrument: X-Rite i1 DisplayPro"),
                      Check("compositor", OK, "KWin 6.7.5"), Check("desktop", OK, "Desktop entry installed")]
            setup = SetupCheckDialog(checks, parent=win)
            setup.resize(560, 380)
            setup.show()
            save(setup, args.out, f"setup-check-{suffix}")
            setup.close()
        win._tasks.clear()
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
