"""Instrument measurement mode (-y) and correction choice: parsing, installed files among the modes, per-display
choice, filtering by instrument, migration, sidecar and report."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from kelvincal.argyll.corrections import correction_for_display_type, read_correction
from kelvincal.argyll.instruments import (
    InstrumentStatus,
    correction_kinds,
    display_type_text,
    parse_display_types,
    parse_spotread_usage,
)
from kelvincal.core.models import DisplayInfo
from kelvincal.core.profile_meta import read_profile_meta, write_profile_meta

USAGE = """Measure spot values, Version 3.4.1
 -c listno            Set instrument port from the following list (default 1)
    1 = '/dev/bus/usb/003/112 (X-Rite i1 DisplayPro, ColorMunki Display)'
 -e                   Use emissive measurement mode (absolute results)
 -y n                  i1D3: Non-Refresh display [Default,CB1]
    r|c                i1D3: Refresh display [CB2]
    h                  i1D3: LCD RG Phosphor (Addition of Dell Ultrasharp U2413 to the RG-Phosphor Family EDR (created originall
    e                  i1D3: LCD White LED IPS (WLED AC LG Samsung)
    1                  i1D3: Unknown (LEN P32p-20)
    2                  i1D3: Unknown (LEN P32u-10)
 -I illum             Set simulated instrument illumination using FWA (def -i illum):
"""


def ccss(technology: str, display: str, descriptor: str = "Not specified") -> str:
    oem = 'ORIGINATOR "X-Rite"\nOEM "YES"\n' if descriptor == "Not specified" else ""
    return f'CCSS\n\n{oem}DESCRIPTOR "{descriptor}"\nTECHNOLOGY "{technology}"\nDISPLAY "{display}"\n'


RG = "Addition of Dell Ultrasharp U2413 to the RG-Phosphor Family EDR (created originally on 12 Aug 2011)"


def install_files(data: Path) -> dict[str, Path]:
    """Correction files as `oeminst` and KelvinCal leave them in ~/.local/share/ArgyllCMS."""
    files = {
        "e": ("WLEDFamily_07Feb11.ccss", ccss("LCD White LED IPS", "WLED AC LG Samsung")),
        "h": ("RG_Phosphor_Family_25Jul12.ccss", ccss("LCD RG Phosphor", RG)),
        "1": ("KelvinCal_DP-2_LEN_P32p-20.ccss", ccss("Unknown", "LEN P32p-20", "KelvinCal LEN P32p-20")),
        "ccmx": ("pair.ccmx", 'CCMX\n\nDESCRIPTOR "i1 & Dell"\nINSTRUMENT "X"\n'),
    }
    for name, text in files.values():
        (data / name).write_text(text)
    return {key: data / name for key, (name, _text) in files.items()}


class ParsingTest(unittest.TestCase):
    def test_display_types(self) -> None:
        types = parse_display_types(USAGE)
        self.assertEqual([t.key for t in types], ["n", "r", "h", "e", "1", "2"])
        self.assertEqual([t.label for t in types][:4],
                         ["Non-Refresh display", "Refresh display", "LCD RG Phosphor", "LCD White LED IPS"])
        self.assertEqual([t.is_default for t in types][:2], [True, False])
        self.assertEqual(types[0].family, "i1D3")
        status = parse_spotread_usage(USAGE)
        self.assertEqual(status.primary, "X-Rite i1 DisplayPro")
        self.assertEqual(status.display_type("e").label, "LCD White LED IPS")

    def test_installed_files_among_the_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = install_files(Path(tmp))
            corrections = [read_correction(f) for f in files.values()]
            by_key = {t.key: correction_for_display_type(t.description, corrections)
                      for t in parse_display_types(USAGE)}
        self.assertEqual({k: c.path.name if c else None for k, c in by_key.items()},
                         {"n": None, "r": None, "h": files["h"].name,   # cut-off name still matches
                          "e": files["e"].name, "1": files["1"].name, "2": None})

    def test_hanging_spotread_still_reports_argyll(self) -> None:
        from unittest import mock
        import subprocess

        from kelvincal.argyll import instruments

        hang = subprocess.TimeoutExpired(["spotread", "-?"], 10, output=b"Measure spot values, Version 3.3.0\n")
        with mock.patch.object(instruments.shutil, "which", return_value="/usr/bin/spotread"), \
                mock.patch.object(instruments.subprocess, "run", side_effect=hang):
            status = instruments.detect_instruments()
        self.assertEqual((status.argyll_version, status.instruments), ("3.3.0", []))

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
        from kelvincal.core.verification import VerificationResult, report_html

        result = VerificationResult(patches=[], white_xyz=(95, 100, 108), black_xyz=(0.1, 0.1, 0.1),
                                    target_xy=(0.3127, 0.329), display_type="LCD White LED IPS (-y e)")
        self.assertIn("LCD White LED IPS (-y e)", report_html(result))


class PickerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from kelvincal.gui.pages import correction

        self.correction = correction
        correction.set_instrument(InstrumentStatus())   # module state set by other tests
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name) / "data" / "ArgyllCMS"
        data.mkdir(parents=True)
        self.files = install_files(data)
        self._xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = str(data.parent)
        correction.reload_corrections()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(Path(self.tmp.name) / "cfg"))
        self.display = DisplayInfo(connector="DP-1", drm_card_connector="c", edid_hash="mode-test")
        self.key = f"corrections/{self.display.edid_hash}"

    def tearDown(self) -> None:
        self.correction.set_instrument(InstrumentStatus())
        if self._xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self._xdg
        self.correction.reload_corrections()
        self.tmp.cleanup()

    def _picker(self, status: InstrumentStatus):  # noqa: ANN202
        picker = self.correction.CorrectionPicker()
        picker.set_display(self.display)
        picker.set_instrument(status)
        return picker

    def test_each_file_once_and_only_built_in_modes(self) -> None:
        c = self.correction
        picker = self._picker(parse_spotread_usage(USAGE))
        modes = [picker.combo_mode.itemData(i) for i in range(picker.combo_mode.count())]
        self.assertEqual(modes, ["n", "r", "2"])   # "2": its file is not installed here
        files = [picker.combo_file.itemText(i) for i in range(1, picker.combo_file.count())]
        self.assertEqual(files[:2], ["LCD RG Phosphor · general (X-Rite)", "LCD White LED IPS · general (X-Rite)"])
        self.assertEqual(files[2:], ["i1 & Dell", "KelvinCal LEN P32p-20"])   # made for one display: after them
        # no choice yet: the white-LED family, as -y e before; the file decides, so no mode is passed
        self.assertEqual(c.correction_for(self.display), str(self.files["e"]))
        self.assertEqual(picker.current_path(), str(self.files["e"]))
        self.assertEqual(c.measurement_mode(self.display), ("", ""))
        self.assertTrue(picker.combo_mode.isHidden())
        # "None": built-in calibration, mode chosen per display
        picker.combo_file.setCurrentIndex(0)
        picker._on_file(0)
        self.assertIsNone(c.correction_for(self.display))
        self.assertFalse(picker.combo_mode.isHidden())
        self.assertEqual(picker.current_mode(), "n")   # the instrument's default
        idx = picker.combo_mode.findData("r")
        picker.combo_mode.setCurrentIndex(idx)
        picker._on_mode(idx)
        self.assertEqual(c.measurement_mode(self.display), ("r", "Refresh display"))

    def test_mode_chosen_before_becomes_the_file(self) -> None:
        QSettings().setValue(f"{self.key}/display_type", "1")   # KelvinCal 65be99a: own .ccss chosen as -y 1
        self.correction.set_instrument(parse_spotread_usage(USAGE))
        self.assertEqual(self.correction.correction_for(self.display), str(self.files["1"]))
        self.assertEqual(QSettings().value(f"{self.key}/path"), str(self.files["1"]))
        self.assertIsNone(QSettings().value(f"{self.key}/display_type"))

    def test_without_white_led_family_the_built_in_default(self) -> None:
        self.files["e"].unlink()
        self.correction.reload_corrections()
        self.correction.set_instrument(parse_spotread_usage(USAGE))
        self.assertIsNone(self.correction.correction_for(self.display))
        self.assertEqual(self.correction.display_type_for(self.display), "n")

    def test_old_colorimeter_lists_only_ccmx_and_keeps_its_mode(self) -> None:
        QSettings().setValue(f"{self.key}/path", str(self.files["1"]))
        QSettings().setValue(f"{self.key}/display_type", "c")
        status = parse_spotread_usage(USAGE.replace("X-Rite i1 DisplayPro, ColorMunki Display", "Datacolor Spyder3"))
        status.display_types = parse_display_types(" -y l   Spyder3: LCD\n    c   Spyder3: CRT\n -I x\n")
        picker = self._picker(status)
        files = [str(picker.combo_file.itemData(i)) for i in range(picker.combo_file.count())]
        self.assertTrue(all(not f.endswith(".ccss") for f in files))
        self.assertIsNone(self.correction.correction_for(self.display))   # stored .ccss is not used
        self.assertIn(".ccmx", picker.hint.text())
        QSettings().setValue(f"{self.key}/path", str(self.files["ccmx"]))
        picker.reload()
        self.assertFalse(picker.combo_mode.isHidden())   # a .ccmx only corrects the mode
        self.assertEqual(self.correction.display_type_for(self.display), "c")

    def test_spectrometer_needs_no_correction_and_no_mode(self) -> None:
        QSettings().setValue(f"{self.key}/path", str(self.files["1"]))
        picker = self._picker(InstrumentStatus("3.4.1", ["X-Rite i1 Pro 2"], [1]))
        self.assertFalse(picker.combo_file.isEnabled())
        self.assertTrue(picker.combo_mode.isHidden())
        self.assertIsNone(self.correction.correction_for(self.display))
        self.assertEqual(self.correction.display_type_for(self.display), "")


if __name__ == "__main__":
    unittest.main()
