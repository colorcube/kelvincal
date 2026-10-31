"""Presets from calibrated profiles: sidecar listing, grouping per target, newest profile wins, merging."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kelvincal.core.models import DisplayInfo, DisplayPresetEntry, Preset
from kelvincal.core.profile_meta import list_profile_meta, meta_path, write_profile_meta
from kelvincal.presets.from_profiles import build_preset, propose_presets


def _display(connector: str, edid: str) -> DisplayInfo:
    return DisplayInfo(connector=connector, drm_card_connector=f"card1-{connector}", edid_hash=edid, model="LEN")


class PresetsFromProfilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.displays = [_display("DP-1", "a"), _display("DP-2", "b"), _display("HDMI-A-2", "c")]

    def profile(self, name: str, edid: str, target: str, lum: float, created: str,
                ddc=(30, 70, 100, 97, 90), connector: str = "DP-1") -> Path:  # noqa: ANN001
        icc = self.dir / f"{name}.icc"
        icc.write_bytes(b"icc")
        write_profile_meta(icc, ddc, connector, edid, target, lum, "D65")
        data = json.loads(meta_path(icc).read_text())
        data["created"] = created
        meta_path(icc).write_text(json.dumps(data))
        return icc

    def test_proposals_group_by_target_and_take_newest(self) -> None:
        self.profile("old", "a", "office", 140, "2026-10-29T10:00:00", ddc=(1, 1, 1, 1, 1))
        new = self.profile("new", "a", "office", 140, "2026-10-30T10:00:00")
        self.profile("b_office", "b", "office", 140, "2026-10-30T11:00:00", connector="DP-2")
        self.profile("b_evening", "b", "evening", 90, "2026-10-30T12:00:00", connector="DP-2")
        self.profile("foreign", "zzz", "office", 140, "2026-10-30T12:00:00")      # not connected
        self.profile("expert", "a", "", 140, "2026-10-30T12:00:00")               # no target
        (self.dir / "orphan.kelvincal.json").write_text("{}")                      # sidecar without .icc

        metas = list_profile_meta(self.dir)
        self.assertEqual(len(metas), 6)
        props = propose_presets(metas, self.displays, [Preset("Office, Web & Everyday · 140 cd/m² · D65")])
        self.assertEqual([p.name for p in props], ["Office, Web & Everyday · 140 cd/m² · D65",
                                                   "Evening / Dark Room · 90 cd/m² · D65"])
        office = props[0]
        self.assertTrue(office.exists)
        self.assertEqual(set(office.profiles), {"DP-1", "DP-2"})
        self.assertEqual(office.profiles["DP-1"].icc_path, new)
        self.assertFalse(props[1].exists)

    def test_build_keeps_entries_of_displays_without_profile(self) -> None:
        icc = self.profile("p", "a", "office", 140, "2026-10-30T10:00:00")
        prop = propose_presets(list_profile_meta(self.dir), self.displays, [])[0]
        old = Preset(prop.name, displays=[
            DisplayPresetEntry(edid_hash="a", connector="DP-1", ddc_brightness=99, icc_profile="/x.icc"),
            DisplayPresetEntry(edid_hash="c", connector="HDMI-A-2", ddc_brightness=50, icc_profile="/c.icc"),
        ])
        preset = build_preset(prop, self.displays, old)
        by_edid = {e.edid_hash: e for e in preset.displays}
        self.assertEqual(len(preset.displays), 2)
        self.assertEqual((by_edid["a"].ddc_brightness, by_edid["a"].ddc_blue_gain), (30, 90))
        self.assertEqual(by_edid["a"].icc_profile, str(icc))
        self.assertEqual(by_edid["c"].icc_profile, "/c.icc")        # untouched
        self.assertEqual(old.displays[0].ddc_brightness, 99)          # the old preset object is not modified
        fresh = build_preset(prop, self.displays)
        self.assertEqual([e.connector for e in fresh.displays], ["DP-1"])


if __name__ == "__main__":
    unittest.main()
