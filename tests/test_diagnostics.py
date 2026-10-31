"""vcgt reader, diagnostics text output and the spot measurement of the current state."""

from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest

from kelvincal.argyll.vcgt import read_vcgt
from kelvincal.gui.diagnostics import format_text


def icc_with_vcgt(curves: list[list[int]]) -> bytes:
    """Minimal ICC container with a 16-bit table vcgt tag."""
    body = b"vcgt" + b"\0" * 4 + struct.pack(">I", 0) + struct.pack(">HHH", 3, len(curves[0]), 2)
    for curve in curves:
        body += b"".join(struct.pack(">H", v) for v in curve)
    offset = 128 + 4 + 12
    header = bytearray(128)
    header[36:40] = b"acsp"
    total = offset + len(body)
    struct.pack_into(">I", header, 0, total)
    tags = struct.pack(">I", 1) + b"vcgt" + struct.pack(">II", offset, len(body))
    return bytes(header) + tags + body


class VcgtTest(unittest.TestCase):
    def test_table_curves(self) -> None:
        n = 256
        identity = [round(65535 * i / (n - 1)) for i in range(n)]
        blue_down = [round(v * 0.9) for v in identity]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.icc"
            path.write_bytes(icc_with_vcgt([identity, identity, blue_down]))
            v = read_vcgt(path)
        self.assertIsNotNone(v)
        self.assertEqual(v.size, 256)
        self.assertAlmostEqual(v.white[2], 0.9, places=3)
        self.assertAlmostEqual(v.max_deviation, 0.1, places=3)
        self.assertFalse(v.is_identity)

    def test_no_vcgt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.icc"
            data = bytearray(icc_with_vcgt([[0, 65535]] * 3))
            data[132:136] = b"xxxx"  # rename the tag
            path.write_bytes(bytes(data))
            self.assertIsNone(read_vcgt(path))


class GpuLutTest(unittest.TestCase):
    def test_lut_summary_and_vcgt_comparison(self) -> None:
        import struct

        from kelvincal.argyll.vcgt import Vcgt
        from kelvincal.gui.diagnostics import compare_lut_vcgt, lut_summary

        n = 4096
        curve = [min(1.0, 0.02 + i / (n - 1)) for i in range(n)]           # lifted black
        data = b"".join(struct.pack("<HHHH", *(round(v * 65535),) * 3, 0) for v in curve)
        summary = lut_summary(data)
        self.assertEqual(summary["entries"], n)
        self.assertAlmostEqual(summary["black_rgb"][0], 0.02, places=3)
        self.assertEqual(summary["white_rgb"], [1.0, 1.0, 1.0])
        self.assertFalse(summary["identity"])
        same = Vcgt(([0.02 + 0.98 * i / 255 for i in range(256)],) * 3)       # nearly the same curve
        identity = Vcgt(([i / 255 for i in range(256)],) * 3)
        self.assertLess(compare_lut_vcgt(summary["curves"], same), 0.02)
        self.assertAlmostEqual(compare_lut_vcgt(summary["curves"], identity), 0.02, places=3)


class FormatTest(unittest.TestCase):
    def test_text_contains_the_essentials(self) -> None:
        report = {
            "created": "2026-10-30T09:00:00",
            "system": {"kernel": "7.2", "kwin": "kwin 6.7.5", "ddcutil": "ddcutil 3.0.2", "argyll": "ArgyllCMS 3.4.1",
                       "instruments": ["i1 DisplayPro"], "drm_info": False},
            "compositor": {"name": "kwin", "error": ""},
            "active_preset": "Büro",
            "gpu": {"available": False, "note": "drm_info not installed"},
            "displays": [{
                "connector": "DP-2", "model": "LEN P32p-20", "serial": "X", "edid_hash": "h", "i2c_bus": 8,
                "mode": "3840x2160@60Hz scale 1.15",
                "kwin": {"color_profile_source": "ICC", "icc_profile_path": "/p/new.icc", "hdr_enabled": False,
                         "wcg_enabled": False, "brightness": 0.25, "sdr_brightness": 200, "allow_ddc_ci": True},
                "ddc": {"brightness": 25, "contrast": 78, "red_gain": 100, "green_gain": 97, "blue_gain": 89},
                "profile": {"path": "/p/new.icc", "exists": True, "white_cct_k": 6504, "white_xy": [0.3127, 0.329],
                            "white_duv_d65": 0.0013, "effective_gamma": 2.2, "vcgt": None,
                            "kelvincal_ddc": [25, 78, 100, 97, 89], "ddc_matches_profile": True},
                "preset_entry": None, "preset_drift": [],
                "measurement": {"white_cdm2": 120.1, "white_cct_k": 6510, "white_xy": [0.3125, 0.3291],
                                "white_duv_d65": 0.0004, "black_cdm2": 0.118, "contrast": 1018},
            }],
        }
        text = format_text(report)
        for needle in ("kwin 6.7.5", "RGB 100/97/89", "vcgt: none", "MATCHES", "6510 K", "KWin controls VCP 0x10"):
            self.assertIn(needle, text)


class SpotCheckTest(unittest.TestCase):
    def test_spot_check_measures_white_and_black(self) -> None:
        from kelvincal.core.models import ColorMeasurement, DisplayInfo
        from kelvincal.gui.controller import CalibrationController

        class Sensor:
            def __enter__(self):  # noqa: ANN204
                return self

            def __exit__(self, *exc) -> None:  # noqa: ANN002
                pass

            def measure_rgb(self, rgb):  # noqa: ANN001, ANN201
                y = 120.0 if rgb[0] else 0.12
                return ColorMeasurement(rgb, 0.9505 * y, y, 1.089 * y)

        class Patch:
            def wait_for_placement(self, prompt, cancel) -> bool:  # noqa: ANN001
                return True

            def show_patch(self, rgb, status, progress=None) -> None:  # noqa: ANN001
                pass

            def close(self) -> None:
                pass

        ctl = CalibrationController(DisplayInfo(connector="DP-2", drm_card_connector="c", edid_hash="h"),
                                    None, Patch(), sensor_factory=lambda _c: Sensor())  # type: ignore[arg-type]
        res = ctl.run_spot_check()
        self.assertEqual(res["white_cdm2"], 120.0)
        self.assertEqual(res["contrast"], 1000)
        self.assertLess(res["white_duv_d65"], 0.001)


if __name__ == "__main__":
    unittest.main()
