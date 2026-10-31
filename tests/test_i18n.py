"""Consistency checks for the Qt translation files and the translator setup."""

from __future__ import annotations

import os
import string
import unittest
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from kelvincal.core.i18n import translate
from kelvincal.gui.i18n_setup import TRANSLATIONS_DIR, install_translators

TS_FILES = sorted(TRANSLATIONS_DIR.glob("kelvincal_*.ts"))


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


class TestTranslationFiles(unittest.TestCase):
    def test_placeholders_match_source(self) -> None:
        self.assertTrue(TS_FILES)
        for ts in TS_FILES:
            for msg in ET.parse(ts).getroot().iter("message"):
                source = msg.findtext("source") or ""
                tr_el = msg.find("translation")
                forms = [f.text or "" for f in tr_el.iter("numerusform")] or [tr_el.text or ""]
                for form in forms:
                    if not form:
                        continue
                    with self.subTest(ts=ts.name, source=source):
                        self.assertEqual(_fields(source), _fields(form))
                        self.assertEqual("%n" in source, "%n" in form)


class TestTranslatorSetup(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])  # shared with the widget tests

    def test_untranslated_without_translator(self) -> None:
        self.assertEqual(translate("NoSuchContext", "Hello"), "Hello")

    @unittest.skipUnless((TRANSLATIONS_DIR / "kelvincal_de.qm").exists(), "kelvincal_de.qm not built")
    def test_german_translation_loads(self) -> None:
        os.environ["KELVINCAL_LANG"] = "de"
        translators = install_translators(self.app)
        try:
            self.assertEqual(translate("RunningPage", "Cancel"), "Abbrechen")
            text = translate("MainWindow", "Displays detected: {count}").format(count=3)
            self.assertEqual(text, "Erkannte Monitore: 3")
        finally:
            for t in translators:
                self.app.removeTranslator(t)
            del os.environ["KELVINCAL_LANG"]

    @unittest.skipUnless((TRANSLATIONS_DIR / "kelvincal_de.qm").exists(), "kelvincal_de.qm not built")
    def test_qm_rewritten_while_running(self) -> None:
        """bin/update-translations rewrites the .qm in place; a running KelvinCal must not read it again
        (a mapped file crashed the GUI in QTranslator::translate)."""
        import shutil
        import tempfile
        from pathlib import Path
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            qm = Path(tmp) / "kelvincal_de.qm"
            shutil.copy(TRANSLATIONS_DIR / "kelvincal_de.qm", qm)
            os.environ["KELVINCAL_LANG"] = "de"
            with mock.patch("kelvincal.gui.i18n_setup.TRANSLATIONS_DIR", Path(tmp)):
                translators = install_translators(self.app)
            try:
                with open(qm, "r+b") as f:   # in place, like lrelease
                    f.write(b"\0" * qm.stat().st_size)
                self.assertEqual(translate("RunningPage", "Cancel"), "Abbrechen")
            finally:
                for t in translators:
                    self.app.removeTranslator(t)
                del os.environ["KELVINCAL_LANG"]


if __name__ == "__main__":
    unittest.main()
