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

    def test_profile_review_dialog_offscreen_render(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication
        from kcal_gui.profile_review_dialog import ProfileReviewDialog

        app = QApplication.instance() or QApplication([])
        _ = app
        ti3_text = _build_synthetic_ti3(with_kink=True)
        icc_bytes = _build_minimal_icc_bytes(ti3_text)
        with tempfile.TemporaryDirectory() as tmp:
            icc_path = Path(tmp) / "test_kink.icc"
            icc_path.write_bytes(icc_bytes)
            insp = inspect_profile(icc_path)
            dlg = ProfileReviewDialog(inspection=insp)
            img = QImage(860, 660, QImage.Format.Format_ARGB32)
            dlg.render(img)
            dlg.curve_widget.set_view_mode(dlg.curve_widget.MODE_DEVIATION)
            dlg.render(img)
            dlg.close()


if __name__ == "__main__":
    unittest.main()
