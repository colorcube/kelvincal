"""Instrument measurement mode (-y): parsing, per-display choice, filtering by instrument, sidecar and report."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from kcal_argyll.instruments import (
    InstrumentStatus,
    correction_kinds,
    display_type_text,
    parse_display_types,
    parse_spotread_usage,
)
from kcal_core.models import DisplayInfo
from kcal_core.profile_meta import read_profile_meta, write_profile_meta

USAGE = """Measure spot values, Version 3.4.1
 -c listno            Set instrument port from the following list (default 1)
    1 = '/dev/bus/usb/003/112 (X-Rite i1 DisplayPro, ColorMunki Display)'
 -e                   Use emissive measurement mode (absolute results)
 -y n                  i1D3: Non-Refresh display [Default,CB1]
    r|c                i1D3: Refresh display [CB2]
    h                  i1D3: LCD RG Phosphor (Addition of Dell Ultrasharp U2413 to the RG-Phosphor Family EDR (created originall
    e                  i1D3: LCD White LED IPS (WLED AC LG Samsung)
    1                  i1D3: Unknown (LEN P32p-20)
 -I illum             Set simulated instrument illumination using FWA (def -i illum):
"""


class ParsingTest(unittest.TestCase):
    def test_display_types(self) -> None:
        types = parse_display_types(USAGE)
        self.assertEqual([t.key for t in types], ["n", "r", "h", "e", "1"])
        self.assertEqual([t.label for t in types],
                         ["Non-Refresh display", "Refresh display", "LCD RG Phosphor", "LCD White LED IPS",
                          "LEN P32p-20"])
        self.assertEqual([t.installed for t in types], [False, False, False, False, True])
        self.assertEqual(types[0].family, "i1D3")
        status = parse_spotread_usage(USAGE)
        self.assertEqual(status.primary, "X-Rite i1 DisplayPro")
        self.assertEqual(status.display_type("e").label, "LCD White LED IPS")

    def test_without_modes(self) -> None:
        self.assertEqual(parse_display_types(" -c listno   port\n -e  emissive\n"), [])

    def test_correction_kinds(self) -> None:
        self.assertEqual(correction_kinds("X-Rite i1 DisplayPro"), ("ccss", "ccmx"))
        self.assertEqual(correction_kinds("Datacolor Spyder5"), ("ccss", "ccmx"))
        self.assertEqual(correction_kinds("Datacolor Spyder3"), ("ccmx",))
        self.assertEqual(correction_kinds("X-Rite DTP94"), ("ccmx",))
        self.assertEqual(correction_kinds("X-Rite i1 Pro 2"), ())
        self.assertEqual(correction_kinds(""), ("ccss", "ccmx"))

    def test_text(self) -> None:
        self.assertEqual(display_type_text("e", "LCD White LED IPS"), "LCD White LED IPS (-y e)")
        self.assertEqual(display_type_text("e"), "-y e")
        self.assertEqual(display_type_text(""), "")


class SidecarAndReportTest(unittest.TestCase):
    def test_sidecar_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            icc = Path(tmp) / "p.icc"
            icc.write_bytes(b"")
            write_profile_meta(icc, (1, 2, 3, 4, 5), display_type="1", display_type_label="LEN P32p-20")
            meta = read_profile_meta(icc)
            self.assertEqual((meta.display_type, meta.display_type_label), ("1", "LEN P32p-20"))
            # older sidecars: not recorded
            write_profile_meta(icc, (1, 2, 3, 4, 5))
            path = icc.with_name("p.kelvincal.json")
            text = path.read_text().replace('"display_type": "",\n', "")
            path.write_text(text)
            self.assertIsNone(read_profile_meta(icc).display_type)

    def test_report_names_the_mode(self) -> None:
        from kcal_core.verification import VerificationResult, report_html

        result = VerificationResult(patches=[], white_xyz=(95, 100, 108), black_xyz=(0.1, 0.1, 0.1),
                                    target_xy=(0.3127, 0.329), display_type="LCD White LED IPS (-y e)")
        self.assertIn("LCD White LED IPS (-y e)", report_html(result))


class PickerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from kcal_gui.pages import correction

        self.correction = correction
        correction.set_instrument(InstrumentStatus())   # module state set by other tests
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name) / "data" / "ArgyllCMS"
        data.mkdir(parents=True)
        (data / "pfs.ccss").write_text('CCSS\n\nDESCRIPTOR "PFS Phosphor"\nTECHNOLOGY "LCD PFS Phosphor WLED"\n')
        (data / "pair.ccmx").write_text('CCMX\n\nDESCRIPTOR "i1 & Dell"\nINSTRUMENT "X"\n')
        self._xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = str(data.parent)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(Path(self.tmp.name) / "cfg"))
        self.display = DisplayInfo(connector="DP-1", drm_card_connector="c", edid_hash="mode-test")
        self.ccss = str(data / "pfs.ccss")

    def tearDown(self) -> None:
        self.correction.set_instrument(InstrumentStatus())
        if self._xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self._xdg
        self.tmp.cleanup()

    def _picker(self, status: InstrumentStatus):  # noqa: ANN202
        picker = self.correction.CorrectionPicker()
        picker.set_display(self.display)
        picker.set_instrument(status)
        return picker

    def test_modes_offered_and_saved_per_display(self) -> None:
        c = self.correction
        self.assertEqual(c.display_type_for(self.display), "e")   # no instrument known yet: default
        picker = self._picker(parse_spotread_usage(USAGE))
        modes = [picker.combo_mode.itemData(i) for i in range(picker.combo_mode.count())]
        self.assertEqual([m for m in modes if m], ["n", "r", "h", "e", "1"])   # separator before installed
        self.assertEqual(picker.current_mode(), "e")
        idx = picker.combo_mode.findData("1")
        self.assertIn("LEN P32p-20", picker.combo_mode.itemText(idx))
        picker.combo_mode.setCurrentIndex(idx)
        picker._on_mode(idx)
        self.assertEqual(c.measurement_mode(self.display), ("1", "LEN P32p-20"))
        # another instrument without that mode: falls back to the default
        c.set_instrument(InstrumentStatus("3.4.1", ["Datacolor Spyder5"], [1], parse_display_types(
            " -y l   Spyder: LCD\n    e   Spyder: White LED\n -I x\n")))
        self.assertEqual(c.display_type_for(self.display), "e")

    def test_old_colorimeter_lists_only_ccmx(self) -> None:
        QSettings().setValue(f"corrections/{self.display.edid_hash}/path", self.ccss)
        picker = self._picker(InstrumentStatus("3.4.1", ["Datacolor Spyder3"], [1]))
        files = [str(picker.combo_file.itemData(i)) for i in range(picker.combo_file.count())]
        self.assertTrue(all(not f.endswith(".ccss") for f in files))
        self.assertIsNone(self.correction.correction_for(self.display))   # stored .ccss is not used
        self.assertIn(".ccmx", picker.hint.text())

    def test_spectrometer_needs_no_correction_and_no_mode(self) -> None:
        QSettings().setValue(f"corrections/{self.display.edid_hash}/path", self.ccss)
        picker = self._picker(InstrumentStatus("3.4.1", ["X-Rite i1 Pro 2"], [1]))
        self.assertFalse(picker.combo_file.isEnabled())
        self.assertTrue(picker.combo_mode.isHidden())
        self.assertIsNone(self.correction.correction_for(self.display))
        self.assertEqual(self.correction.display_type_for(self.display), "")


if __name__ == "__main__":
    unittest.main()
