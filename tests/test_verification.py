"""Verification: sRGB expectation, evaluation of a simulated display, controller run, HTML report."""

from __future__ import annotations

import unittest

from kelvincal.core.models import ColorMeasurement, DisplayInfo
from kelvincal.core.verification import (
    SRGB_WHITE_XYZ,
    evaluate,
    grade,
    likely_causes,
    overall_grade,
    report_html,
    srgb_to_xyz,
    test_patches,
)
from kelvincal.gui.controller import CalibrationController


def ideal(rgb: tuple[int, int, int], luminance: float = 120.0) -> tuple[float, float, float]:
    """A perfect sRGB display at `luminance` cd/m² (with a tiny black level)."""
    x, y, z = srgb_to_xyz(rgb)
    return (x * luminance + 0.05, y * luminance + 0.05, z * luminance + 0.06)


def tinted(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Same display with a green cast in the mid-tones (gray balance error)."""
    x, y, z = ideal(rgb)
    mid = 4 * (rgb[1] / 255) * (1 - rgb[1] / 255)
    return (x * (1 - 0.03 * mid), y, z * (1 - 0.05 * mid))


class VerificationTest(unittest.TestCase):
    def test_likely_causes(self) -> None:
        patches = test_patches()
        good = evaluate(patches, [ideal(p.rgb) for p in patches], ideal((255,) * 3), ideal((0,) * 3),
                        (0.3127, 0.3290))
        self.assertEqual(overall_grade(good), "ok")
        bad = evaluate(patches, [tinted(p.rgb) for p in patches], tinted((255,) * 3), tinted((0,) * 3),
                       (0.3127, 0.3290))
        self.assertNotEqual(overall_grade(bad), "ok")
        bad.ddc = (87, 79, 100, 94, 89)
        causes = likely_causes(bad, 140.0, (0.3127, 0.3290), (36, 79, 100, 94, 89))
        self.assertEqual(len(causes), 2)                       # DDC and luminance (white is still D65)
        self.assertIn("87", causes[0])
        self.assertIn("36", causes[0])
        self.assertIn("120", causes[1])
        shifted = likely_causes(bad, 120.0, (0.3200, 0.3290), (87, 79, 100, 94, 89))
        self.assertEqual(len(shifted), 1)                       # only the white moved
        self.assertIn("Δu′v′", shifted[0])
        self.assertEqual(len(likely_causes(bad)), 1)            # nothing known: generic hint

    def test_numbers_follow_the_locale_and_report_names_target(self) -> None:
        from PySide6.QtCore import QLocale

        patches = test_patches()
        res = evaluate(patches, [tinted(p.rgb) for p in patches], tinted((255,) * 3), tinted((0,) * 3),
                       (0.3142, 0.3207))
        res.correction, res.white_offset = "/x/KelvinCal_DP-2.ccss", (0.0015, -0.0083)
        try:
            QLocale.setDefault(QLocale(QLocale.Language.German))
            cause = likely_causes(res, 120.0, (0.3200, 0.3290))[0]
            self.assertIn("0,0", cause)
            report = report_html(res)
            self.assertIn("x 0,3142", report)
            self.assertIn("KelvinCal_DP-2.ccss", report)
            self.assertIn("-0,0083", report)
        finally:
            QLocale.setDefault(QLocale.c())

    def test_srgb_white_and_patch_set(self) -> None:
        for got, exp in zip(srgb_to_xyz((255, 255, 255)), SRGB_WHITE_XYZ):
            self.assertAlmostEqual(got, exp, places=3)
        patches = test_patches()
        self.assertGreaterEqual(len(patches), 40)
        self.assertEqual(sum(p.gray for p in patches), 16)  # 10 ramp steps + 6 chart neutrals

    def test_ideal_display_passes(self) -> None:
        patches = test_patches()
        res = evaluate(patches, [ideal(p.rgb) for p in patches], ideal((255, 255, 255)), ideal((0, 0, 0)),
                       (0.3127, 0.3290))
        self.assertLess(res.mean, 0.5)               # only the black level adds a little in the shadows
        self.assertEqual(grade(res.mean, (1.0, 1.5)), "ok")
        self.assertLess(res.gray_chroma_max, 0.3)
        self.assertLess(res.white_duv, 0.001)

    def test_gray_cast_is_detected(self) -> None:
        patches = test_patches()
        res = evaluate(patches, [tinted(p.rgb) for p in patches], tinted((255, 255, 255)), tinted((0, 0, 0)),
                       (0.3127, 0.3290))
        self.assertGreater(res.gray_chroma_max, 2.0)
        self.assertNotEqual(grade(res.gray_chroma_max, (1.0, 2.0)), "ok")

    def test_report_contains_every_patch(self) -> None:
        patches = test_patches()
        res = evaluate(patches, [ideal(p.rgb) for p in patches], ideal((255,) * 3), ideal((0,) * 3),
                       (0.3127, 0.3290), "Test.icc", "Dell (DP-2)")
        text = report_html(res)
        self.assertEqual(text.count("<tr><td>"), len(patches))
        self.assertIn("Test.icc", text)


class _Sensor:
    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        pass

    def measure_rgb(self, rgb):  # noqa: ANN001, ANN201
        x, y, z = ideal(rgb)
        return ColorMeasurement(rgb, x, y, z)


class _Patch:
    def __init__(self) -> None:
        self.shown: list[tuple[int, int, int]] = []
        self.closed = False

    def wait_for_placement(self, prompt, cancel) -> bool:  # noqa: ANN001
        return True

    def show_patch(self, rgb, status, progress=None) -> None:  # noqa: ANN001
        self.shown.append(rgb)

    def close(self) -> None:
        self.closed = True


class ControllerVerificationTest(unittest.TestCase):
    def test_run_verification(self) -> None:
        patch = _Patch()
        ctl = CalibrationController(
            display=DisplayInfo(connector="DP-2", drm_card_connector="c", edid_hash="x", model="Dell"),
            compositor=None,  # type: ignore[arg-type] - verification must not touch the compositor
            patch_display=patch,  # type: ignore[arg-type]
            sensor_factory=lambda _c: _Sensor(),  # type: ignore[arg-type,return-value]
        )
        res = ctl.run_verification(profile_label="new.icc")
        self.assertEqual(len(res.patches), len(test_patches()))
        self.assertEqual(patch.shown[:2], [(255, 255, 255), (0, 0, 0)])
        self.assertTrue(patch.closed)
        self.assertLess(res.mean, 0.5)
        self.assertEqual(res.display_label, "Dell (DP-2)")



class VerificationPageTest(unittest.TestCase):
    def test_page_runs_and_shows_result(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from kelvincal.gui.inspector.verification_page import VerificationPage

        _app = QApplication.instance() or QApplication([])
        labels: list[str] = []

        def starter(label, on_progress, on_done, on_failed):  # noqa: ANN001, ANN202
            labels.append(label)
            patches = test_patches()
            on_progress(1, 2)
            on_done(evaluate(patches, [tinted(p.rgb) for p in patches], tinted((255,) * 3), tinted((0,) * 3),
                             (0.3127, 0.3290), label))
            return lambda: None

        page = VerificationPage(starter, lambda: "new.icc")
        page.start()
        self.assertEqual(labels, ["new.icc"])
        self.assertFalse(page.is_running())
        self.assertEqual(page.table.rowCount(), len(test_patches()))
        self.assertEqual(page.kpi_gray.value.state, "error")        # the green cast is graded
        self.assertFalse(page.cause_banner.isHidden())              # … and named in a banner
        self.assertEqual(page.cause_banner.kind, "error")
        self.assertTrue(page.btn_report.isEnabled())
        self.assertEqual(page.table.item(0, 0).text(), "1")       # ascending by number

        failing = VerificationPage(lambda *a: (a[3]("no screen"), (lambda: None))[1], lambda: "x")
        failing._on_failed = lambda msg: VerificationPage._finish(failing)  # no message box in tests
        failing.start()
        self.assertFalse(failing.is_running())                    # immediate failure must not hang

    def test_without_display_measuring_is_disabled(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from kelvincal.gui.inspector.verification_page import VerificationPage

        _app = QApplication.instance() or QApplication([])
        page = VerificationPage(None, lambda: "")
        self.assertFalse(page.btn_start.isEnabled())


if __name__ == "__main__":
    unittest.main()
