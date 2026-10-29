"""Unit tests for display discovery, ddcutil parser, KWin output config, and ArgyllCMS parsers."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kcal_argyll.spotread_session import parse_spotread_xyz
from kcal_core.compositor.kwin import KWinBackend
from kcal_core.discovery import parse_ddcutil_detect_output
from kcal_ddc.ddc_client import parse_terse_getvcp


SAMPLE_DDC_DETECT = """
Display 1
   I2C bus:          /dev/i2c-5
   DRM connector:    card1-HDMI-A-2
   drm_connector_id: 476
   Monitor:          LEN:LEN P32u-10:SN-MOCK-001

Display 2
   I2C bus:          /dev/i2c-7
   DRM connector:    card1-DP-1
   drm_connector_id: 452
   Monitor:          LEN:LEN P32u-10:SN-MOCK-002

Display 3
   I2C bus:          /dev/i2c-8
   DRM connector:    card1-DP-2
   drm_connector_id: 462
   Monitor:          LEN:LEN P32p-20:SN-MOCK-003
"""


class TestDiscoveryAndParsers(unittest.TestCase):
    def test_parse_ddcutil_detect_output(self) -> None:
        entries = parse_ddcutil_detect_output(SAMPLE_DDC_DETECT)
        self.assertEqual(len(entries), 3)

        self.assertEqual(entries[0]["display_num"], 1)
        self.assertEqual(entries[0]["i2c_bus"], 5)
        self.assertEqual(entries[0]["connector"], "HDMI-A-2")
        self.assertEqual(entries[0]["model"], "LEN P32u-10")
        self.assertEqual(entries[0]["serial"], "SN-MOCK-001")

        self.assertEqual(entries[2]["display_num"], 3)
        self.assertEqual(entries[2]["i2c_bus"], 8)
        self.assertEqual(entries[2]["connector"], "DP-2")
        self.assertEqual(entries[2]["model"], "LEN P32p-20")
        self.assertEqual(entries[2]["serial"], "SN-MOCK-003")

    def test_parse_terse_getvcp(self) -> None:
        raw = """
VCP 10 C 87 100
VCP 12 C 60 100
VCP 16 C 99 100
VCP 18 C 100 100
VCP 1A C 98 100
"""
        parsed = parse_terse_getvcp(raw)
        self.assertEqual(parsed["10"], (87, 100))
        self.assertEqual(parsed["12"], (60, 100))
        self.assertEqual(parsed["16"], (99, 100))
        self.assertEqual(parsed["18"], (100, 100))
        self.assertEqual(parsed["1A"], (98, 100))

    def test_kwin_backend_reads_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_file = Path(tmp_dir) / "kwinoutputconfig.json"
            sample_data = [
                {
                    "name": "outputs",
                    "data": [
                        {
                            "connectorName": "DP-2",
                            "edidHash": "0123456789abcdef0123456789abcdef",
                            "edidIdentifier": "LEN 25250 0 28 2020 0",
                            "colorProfileSource": "ICC",
                            "iccProfilePath": "/home/user/.local/share/icc/P32p.icc",
                            "brightness": 0.87,
                            "highDynamicRange": False,
                            "wideColorGamut": False,
                            "scale": 1.15,
                            "mode": {"width": 3840, "height": 2160, "refreshRate": 60000},
                        }
                    ],
                }
            ]
            cfg_file.write_text(json.dumps(sample_data), encoding="utf-8")

            backend = KWinBackend(config_path=cfg_file)
            outputs = backend.get_outputs()
            self.assertIn("DP-2", outputs)
            dp2 = outputs["DP-2"]
            self.assertEqual(dp2.edid_hash, "0123456789abcdef0123456789abcdef")
            self.assertEqual(dp2.color_profile_source, "ICC")
            self.assertEqual(dp2.icc_profile_path, "/home/user/.local/share/icc/P32p.icc")
            self.assertEqual(dp2.width, 3840)
            self.assertEqual(dp2.height, 2160)

    def test_argyll_parsers(self) -> None:
        spot_out = """
Place instrument on spot to be measured,
Hit Esc or Q to exit, any other key to take a reading:
 Result is XYZ: 132.842 140.115 152.610, D50 Lab: 100.00 0.12 -0.25
"""
        xyz = parse_spotread_xyz(spot_out)
        self.assertEqual(xyz, (132.842, 140.115, 152.610))


if __name__ == "__main__":
    unittest.main()
