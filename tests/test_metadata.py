"""Release metadata: one version number in the package, the AppStream file and the changelog."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

from kelvincal import __version__

ROOT = Path(__file__).resolve().parents[1]
METAINFO = ROOT / "share" / "metainfo" / "de.colorcube.kelvincal.metainfo.xml"


class MetadataTest(unittest.TestCase):
    def test_version_everywhere(self) -> None:
        releases = ET.parse(METAINFO).getroot().find("releases")
        self.assertEqual(releases[0].get("version"), __version__)       # newest release first
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual(re.search(r"^## (\S+)", changelog, re.MULTILINE).group(1), __version__)
        self.assertIn('attr = "kelvincal.__version__"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        spec = (ROOT / "packaging" / "rpm" / "kelvincal.spec").read_text(encoding="utf-8")
        self.assertEqual(re.search(r"^Version:\s*(\S+)", spec, re.MULTILINE).group(1), __version__)
        deb = (ROOT / "packaging" / "debian" / "changelog").read_text(encoding="utf-8")
        self.assertEqual(re.match(r"kelvincal \(([^-)]+)-", deb).group(1), __version__)

    @unittest.skipUnless(shutil.which("appstreamcli"), "appstreamcli not installed")
    def test_metainfo_valid(self) -> None:
        out = subprocess.run(["appstreamcli", "validate", "--no-net", str(METAINFO)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    @unittest.skipUnless(shutil.which("desktop-file-validate"), "desktop-file-validate not installed")
    def test_desktop_entry_valid(self) -> None:
        entry = ROOT / "share" / "applications" / "de.colorcube.kelvincal.desktop"
        out = subprocess.run(["desktop-file-validate", str(entry)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
