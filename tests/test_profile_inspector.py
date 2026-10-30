"""Unit tests for ICC profile and .ti3 measurement inspection and kink detection."""

from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest

from kcal_argyll.profile_inspector import (
    _analyze_gray_ramp,
    _detect_trc_kinks,
    inspect_profile,
    parse_ti3_text,
)


def _build_synthetic_ti3(with_kink: bool = False) -> str:
    lines = [
        "CTI3",
        "BEGIN_DATA_FORMAT",
        "SAMPLE_ID RGB_R RGB_G RGB_B XYZ_X XYZ_Y XYZ_Z",
        "END_DATA_FORMAT",
        "BEGIN_DATA",
    ]
    y_min = 0.14
    y_max = 140.0
    for i in range(11):
        pct = i * 10.0
        norm = (pct / 100.0) ** 2.2
        if with_kink and i == 5:
            # Inject a reversal/kink at 50% gray (drops below 40% gray)
            norm = (0.35) ** 2.2
        y = y_min + norm * (y_max - y_min)
        # D65-like XYZ proportions
        x = y * (0.3127 / 0.3290)
        z = y * (0.3583 / 0.3290)
        lines.append(f"{i + 1} {pct:.2f} {pct:.2f} {pct:.2f} {x:.4f} {y:.4f} {z:.4f}")
    lines.append("END_DATA")
    return "\n".join(lines)


def _build_minimal_icc_bytes(ti3_text: str) -> bytes:
    """Constructs a minimal valid ICC binary containing desc, lumi, rTRC, gTRC, bTRC, and targ tags."""
    desc_str = b"KelvinCal Test Profile\x00"
    desc_tag = b"desc\x00\x00\x00\x00" + struct.pack(">I", len(desc_str)) + desc_str + b"\x00" * 16

    def _curv_tag(gamma: float) -> bytes:
        vals = [int(round(((i / 63.0) ** gamma) * 65535)) for i in range(64)]
        return b"curv\x00\x00\x00\x00" + struct.pack(">I", 64) + struct.pack(">64H", *vals)

    r_tag = _curv_tag(2.2)
    g_tag = _curv_tag(2.2)
    b_tag = _curv_tag(2.2)
    targ_bytes = ti3_text.encode("latin-1") + b"\x00"
    targ_tag = b"text\x00\x00\x00\x00" + targ_bytes

    tag_list = [
        (b"desc", desc_tag),
        (b"rTRC", r_tag),
        (b"gTRC", g_tag),
        (b"bTRC", b_tag),
        (b"targ", targ_tag),
    ]
    tag_count = len(tag_list)
    offset = 132 + tag_count * 12
    directory = bytearray()
    payloads = bytearray()
    for sig, payload in tag_list:
        directory.extend(struct.pack(">4sII", sig, offset, len(payload)))
        payloads.extend(payload)
        offset += len(payload)

    total_size = offset
    header = bytearray(128)
    struct.pack_into(">I", header, 0, total_size)
    header[36:40] = b"acsp"
    return bytes(header) + struct.pack(">I", tag_count) + bytes(directory) + bytes(payloads)


class TestProfileInspector(unittest.TestCase):
    def test_smooth_ti3_gray_ramp_is_clean(self) -> None:
        rows = parse_ti3_text(_build_synthetic_ti3(with_kink=False))
        self.assertEqual(len(rows), 11)
        ramp, kinks, eff_gamma = _analyze_gray_ramp(rows, target_gamma=2.2)
        self.assertEqual(len(ramp), 11)
        self.assertEqual(len(kinks), 0)
        self.assertIsNotNone(eff_gamma)
        self.assertAlmostEqual(eff_gamma or 0.0, 2.2, places=2)

    def test_kinked_ti3_gray_ramp_is_detected(self) -> None:
        rows = parse_ti3_text(_build_synthetic_ti3(with_kink=True))
        ramp, kinks, _ = _analyze_gray_ramp(rows, target_gamma=2.2)
        self.assertEqual(len(ramp), 11)
        self.assertGreaterEqual(len(kinks), 1)
        self.assertTrue(any(k.severity == "error" and k.input_pct == 50.0 for k in kinks))

    def test_trc_reversal_detection(self) -> None:
        clean_curve = [(i / 63.0) ** 2.2 for i in range(64)]
        self.assertEqual(len(_detect_trc_kinks("R", clean_curve)), 0)

        kinked_curve = list(clean_curve)
        kinked_curve[32] = kinked_curve[30] - 0.01
        warnings = _detect_trc_kinks("R", kinked_curve)
        self.assertGreaterEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "error")

    def test_inspect_profile_from_icc_with_embedded_targ(self) -> None:
        ti3_text = _build_synthetic_ti3(with_kink=False)
        icc_bytes = _build_minimal_icc_bytes(ti3_text)
        with tempfile.TemporaryDirectory() as tmp:
            icc_path = Path(tmp) / "test.icc"
            icc_path.write_bytes(icc_bytes)
            insp = inspect_profile(icc_path)
            self.assertEqual(insp.description, "KelvinCal Test Profile")
            self.assertTrue(insp.is_clean)
            self.assertAlmostEqual(insp.luminance_cdm2 or 0.0, 140.0, places=1)
            self.assertAlmostEqual(insp.black_luminance_cdm2 or 0.0, 0.14, places=2)
            self.assertAlmostEqual(insp.contrast_ratio or 0.0, 1000.0, delta=5.0)
            self.assertEqual(len(insp.r_trc), 64)

    def test_reference_gamut_coverage(self) -> None:
        from kcal_argyll.profile_inspector import REFERENCE_GAMUTS, gamut_coverage_pct

        srgb = REFERENCE_GAMUTS["sRGB"]
        self.assertAlmostEqual(gamut_coverage_pct(srgb, srgb) or 0.0, 100.0, places=3)
        self.assertAlmostEqual(gamut_coverage_pct(REFERENCE_GAMUTS["Rec.2020"], srgb) or 0.0, 100.0, places=3)
        p3_in_srgb = gamut_coverage_pct(srgb, REFERENCE_GAMUTS["DCI-P3"]) or 0.0
        self.assertTrue(60.0 < p3_in_srgb < 90.0, p3_in_srgb)
        self.assertIsNone(gamut_coverage_pct({"R": (0.6, 0.3)}, srgb))

    def test_inspector_dialog_offscreen_render(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication
        from kcal_gui.inspector import InspectorDialog
        from kcal_gui.inspector.dialog import TAB_GAMUT, TAB_GAMMA, TAB_KNICK, TAB_TRC

        app = QApplication.instance() or QApplication([])
        _ = app
        ti3_text = _build_synthetic_ti3(with_kink=True)
        icc_bytes = _build_minimal_icc_bytes(ti3_text)
        with tempfile.TemporaryDirectory() as tmp:
            icc_path = Path(tmp) / "test_kink.icc"
            icc_path.write_bytes(icc_bytes)
            insp = inspect_profile(icc_path)
            dlg = InspectorDialog(inspection=insp)
            dlg.resize(1240, 820)
            dlg.show()
            for tab in (TAB_TRC, TAB_GAMMA, TAB_KNICK, TAB_GAMUT):
                dlg.tabs.setCurrentIndex(tab)
                w = dlg.plots.currentWidget()
                w.resize(700, 400)
                img = QImage(700, 400, QImage.Format.Format_ARGB32)
                w.render(img)
                rect = w.plot_rect()
                bg_rgb = img.pixelColor(int(rect.left()) + 3, int(rect.top()) + 3).rgb()
                interior_colors = {
                    img.pixelColor(x, y).rgb()
                    for x in range(int(rect.left()) + 10, int(rect.right()) - 10, 6)
                    for y in range(int(rect.top()) + 10, int(rect.bottom()) - 10, 6)
                }
                self.assertGreater(len(interior_colors - {bg_rgb}), 3, f"Tab {tab} rendered no curves")
                self.assertTrue(w.readout_at(0.5, 0.5))
            # switching views must not resize the dialog (it used to grow after the gamut view)
            dlg.tabs.setCurrentIndex(TAB_TRC)
            dlg.resize(dlg.minimumSizeHint())
            QApplication.processEvents()
            size_before = dlg.size()
            dlg.tabs.setCurrentIndex(TAB_GAMUT)
            QApplication.processEvents()
            dlg.tabs.setCurrentIndex(TAB_TRC)
            QApplication.processEvents()
            self.assertEqual(dlg.size(), size_before)
            dlg.seg_lstar.setCurrentIndex(1)
            dlg.seg_cie.setCurrentIndex(1)
            self.assertFalse(dlg.curve_plot.lstar is False)
            self.assertFalse(dlg.gamut_plot.uv)
            dlg.reject()



class InspectorDdcPreviewTest(unittest.TestCase):
    """A/B preview switches the display hardware (DDC) together with the profile."""

    def test_preview_and_discard_switch_ddc(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from kcal_gui.inspector import InspectorDialog
        from kcal_gui.inspector.dialog import PREVIEW_NEW, PREVIEW_PREVIOUS, PREVIEW_UNCALIBRATED

        app = QApplication.instance() or QApplication([])

        class Comp:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def apply_output_profile(self, connector, icc_profile_path="", color_profile_source="ICC",  # noqa: ANN001
                                     brightness=None) -> None:  # noqa: ANN001
                self.calls.append(Path(icc_profile_path).name)

            def reset_for_calibration(self, connector) -> None:  # noqa: ANN001
                self.calls.append("sRGB")

        class Staged:
            suggested_output_path = Path("/tmp/x.icc")

            def cleanup(self) -> None:
                pass

        applied: list[tuple] = []
        before, after = (87, 60, 99, 100, 99), (25, 78, 100, 97, 89)
        with tempfile.TemporaryDirectory() as tmp:
            icc_path = Path(tmp) / "new.icc"
            icc_path.write_bytes(_build_minimal_icc_bytes(_build_synthetic_ti3()))
            comp = Comp()
            dlg = InspectorDialog(inspect_profile(icc_path), connector="DP-2", compositor=comp,
                                  staged_profile=Staged(), previous_icc_path="/x/old.icc", previous_source="ICC",
                                  ddc_previous=before, ddc_new=after, ddc_apply=applied.append)

            def switch(mode: int) -> None:
                dlg.set_preview(mode)
                if dlg._ddc_task is not None:
                    dlg._ddc_task.wait()
                for _ in range(5):
                    app.processEvents()

            switch(PREVIEW_PREVIOUS)
            self.assertEqual((comp.calls[-1], applied[-1]), ("old.icc", before))
            switch(PREVIEW_UNCALIBRATED)
            self.assertEqual((comp.calls[-1], applied[-1]), ("sRGB", after))
            switch(PREVIEW_NEW)
            self.assertEqual(comp.calls[-1], "new.icc")
            self.assertEqual(len(applied), 2)               # hardware already at "after": no extra write
            dlg.reject()                                    # discard → previous profile and hardware
            self.assertEqual((comp.calls[-1], applied[-1]), ("old.icc", before))



class ProfileMetaTest(unittest.TestCase):
    def test_sidecar_roundtrip(self) -> None:
        from kcal_core.profile_meta import connector_of, meta_path, read_profile_ddc, write_profile_meta

        with tempfile.TemporaryDirectory() as tmp:
            icc = Path(tmp) / "KC_DP2.icc"
            self.assertIsNone(read_profile_ddc(icc))
            write_profile_meta(icc, (25, 78, 100, 97, 89), "DP-2", "abc", "photo")
            self.assertEqual(meta_path(icc).name, "KC_DP2.kelvincal.json")
            self.assertEqual(read_profile_ddc(icc), (25, 78, 100, 97, 89))
            self.assertEqual(connector_of(icc), "DP-2")

    def test_sidecar_records_target_offset_and_correction(self) -> None:
        import json

        from kcal_core.profile_meta import meta_path, read_profile_meta, write_profile_meta

        with tempfile.TemporaryDirectory() as tmp:
            icc = Path(tmp) / "KC_DP2.icc"
            icc.write_bytes(b"")
            write_profile_meta(icc, (36, 79, 100, 94, 89), "DP-2", "abc", "office", 140.0, "D65",
                               (0.31421, 0.32072), (0.0015, -0.0083), "/x/KelvinCal_DP-2.ccss")
            meta = read_profile_meta(icc)
            self.assertEqual(meta.whitepoint_xy, (0.31421, 0.32072))
            self.assertEqual(meta.white_offset, (0.0015, -0.0083))
            self.assertEqual(meta.correction, "/x/KelvinCal_DP-2.ccss")
            # sidecars written before these fields existed still load
            data = json.loads(meta_path(icc).read_text())
            for key in ("whitepoint_xy", "white_offset", "correction"):
                del data[key]
            meta_path(icc).write_text(json.dumps(data))
            meta = read_profile_meta(icc)
            self.assertEqual((meta.whitepoint_xy, meta.white_offset, meta.correction), (None, (0.0, 0.0), None))


class LibraryInspectorDdcTest(unittest.TestCase):
    def test_library_profile_switches_to_its_hardware_and_back(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from kcal_gui.inspector import InspectorDialog
        from kcal_gui.inspector.dialog import PREVIEW_NEW

        app = QApplication.instance() or QApplication([])

        class Comp:
            def apply_output_profile(self, **kw) -> None:  # noqa: ANN003
                pass

            def reset_for_calibration(self, connector) -> None:  # noqa: ANN001
                pass

        applied: list[tuple] = []
        current, profile_hw = (87, 60, 99, 100, 99), (25, 78, 100, 97, 89)
        with tempfile.TemporaryDirectory() as tmp:
            icc_path = Path(tmp) / "lib.icc"
            icc_path.write_bytes(_build_minimal_icc_bytes(_build_synthetic_ti3()))
            dlg = InspectorDialog(inspect_profile(icc_path), connector="DP-2", compositor=Comp(),
                                  previous_icc_path="/x/old.icc", previous_source="ICC",
                                  ddc_previous=current, ddc_new=profile_hw, ddc_apply=applied.append)
            self.assertEqual(dlg._ddc_current, current)    # library: hardware untouched at first
            dlg.set_preview(PREVIEW_NEW)
            if dlg._ddc_task is not None:
                dlg._ddc_task.wait()
            for _ in range(5):
                app.processEvents()
            self.assertEqual(applied, [profile_hw])
            self.assertIn("DDC 25/78/100/97/89", dlg.active_state_label())
            dlg.reject()                                    # closing restores the current state
            self.assertEqual(applied[-1], current)


class VerificationClearTest(unittest.TestCase):
    def test_start_clears_previous_result(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from kcal_core.verification import evaluate, srgb_to_xyz, test_patches
        from kcal_gui.inspector.verification_page import VerificationPage

        _app = QApplication.instance() or QApplication([])
        patches = test_patches()
        xyz = [tuple(v * 100 for v in srgb_to_xyz(p.rgb)) for p in patches]
        result = evaluate(patches, xyz, (95.0, 100.0, 108.9), (0.1, 0.1, 0.1), (0.3127, 0.329), "old.icc")
        page = VerificationPage(lambda *a: (lambda: None), lambda: "new.icc")  # never finishes
        page.set_result(result)
        self.assertEqual(page.table.rowCount(), len(patches))
        page.start()
        self.assertEqual(page.table.rowCount(), 0)
        self.assertFalse(page.btn_report.isEnabled())
        self.assertEqual(page.kpi_mean.value.text(), "–")


if __name__ == "__main__":
    unittest.main()
