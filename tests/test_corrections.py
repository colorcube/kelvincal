"""Spectral corrections: CGATS header parsing, discovery, technology matching, import."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from kcal_argyll.corrections import find_corrections, import_correction, read_correction, technology_key

CCSS = """CCSS

ORIGINATOR "Test"
DESCRIPTOR "LCD PFS Phosphor WLED Family"
TECHNOLOGY "LCD PFS Phosphor WLED"
DISPLAY_TYPE_REFRESH "NO"

NUMBER_OF_FIELDS 2
BEGIN_DATA_FORMAT
SAMPLE_ID SPEC_380
END_DATA_FORMAT
NUMBER_OF_SETS 1
BEGIN_DATA
1 0.1
END_DATA
"""

CCMX = """CCMX

DESCRIPTOR "i1 DisplayPro & Dell U2723QE"
INSTRUMENT "X-Rite i1 DisplayPro, ColorMunki Display"
DISPLAY "Dell U2723QE"
TECHNOLOGY "LCD White LED IPS"
BEGIN_DATA
"""


class CorrectionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "pfs.ccss").write_text(CCSS)
        (self.dir / "sub").mkdir()
        (self.dir / "sub" / "dell.ccmx").write_text(CCMX)
        (self.dir / "broken.ccss").write_text("CGATS.17\nDESCRIPTOR \"x\"\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_read_header(self) -> None:
        c = read_correction(self.dir / "pfs.ccss")
        self.assertEqual((c.kind, c.description, c.technology_key), ("ccss", "LCD PFS Phosphor WLED Family", "pfs"))
        m = read_correction(self.dir / "sub" / "dell.ccmx")
        self.assertEqual((m.kind, m.display, m.technology_key), ("ccmx", "Dell U2723QE", "wled"))
        with self.assertRaises(ValueError):
            read_correction(self.dir / "broken.ccss")

    def test_find_skips_invalid_and_recurses(self) -> None:
        names = [c.path.name for c in find_corrections([self.dir, self.dir / "missing"])]
        self.assertEqual(sorted(names), ["dell.ccmx", "pfs.ccss"])

    def test_technology_keys(self) -> None:
        self.assertEqual(technology_key("LCD GB-r-LED"), "gbr")
        self.assertEqual(technology_key("OLED"), "oled")
        self.assertEqual(technology_key("Quantum Dot LCD"), "qd")
        self.assertEqual(technology_key("CRT"), "")

    def test_import_copies_and_validates(self) -> None:
        target = self.dir / "argyll"
        installed = import_correction(self.dir / "pfs.ccss", target)
        self.assertEqual(installed.path, target / "pfs.ccss")
        self.assertTrue(installed.path.exists())
        with self.assertRaises(ValueError):
            import_correction(self.dir / "broken.ccss", target)


class CorrectionPickerTest(unittest.TestCase):
    """The chosen correction file is stored per display."""

    def test_picker_per_display(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication

        from kcal_core.models import DisplayInfo
        from kcal_gui.pages.correction import CorrectionPicker, correction_for

        _app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            (data / "ArgyllCMS").mkdir(parents=True)
            (data / "ArgyllCMS" / "pfs.ccss").write_text(CCSS)
            (data / "ArgyllCMS" / "dell.ccmx").write_text(CCMX)
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(Path(tmp) / "cfg"))
            old = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = str(data)
            try:
                a = DisplayInfo(connector="DP-1", drm_card_connector="c", edid_hash="aaa")
                b = DisplayInfo(connector="DP-2", drm_card_connector="c", edid_hash="bbb")
                picker = CorrectionPicker()
                picker.reload()
                picker.set_display(a)
                self.assertIsNone(correction_for(a))
                self.assertEqual(picker.combo_file.count(), 3)   # none + two files
                idx = next(i for i in range(picker.combo_file.count())
                           if str(picker.combo_file.itemData(i)).endswith("pfs.ccss"))
                self.assertIn("PFS", picker.combo_file.itemText(idx))  # technology shown in the list
                picker.combo_file.setCurrentIndex(idx)
                picker._on_file(idx)
                self.assertTrue(correction_for(a).endswith("pfs.ccss"))
                picker.set_display(b)                       # other display: own (empty) choice
                self.assertEqual(picker.current_path(), "")
                self.assertIsNone(correction_for(b))
                picker.set_display(a)
                self.assertTrue(picker.current_path().endswith("pfs.ccss"))
                # own correction: button only with a spectrometer and not during a run; a new file is assigned
                self.assertFalse(picker.btn_measure.isEnabled())
                picker.set_spectrometer("X-Rite i1 Pro")
                self.assertTrue(picker.btn_measure.isEnabled())
                picker.set_busy(True)
                self.assertFalse(picker.btn_measure.isEnabled())
                picker.set_busy(False)
                own = data / "ArgyllCMS" / "KelvinCal_DP-1_own.ccss"
                own.write_text(CCSS)
                changed: list[str] = []
                picker.changed.connect(changed.append)
                picker.assign(str(own))
                self.assertEqual((correction_for(a), picker.current_path(), changed), (str(own), str(own), [str(own)]))
            finally:
                if old is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old


if __name__ == "__main__":
    unittest.main()
