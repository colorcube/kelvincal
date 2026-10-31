"""Own .ccss: dispread prompts are answered through the pseudo-terminal, patches reach the patch window."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

from kelvincal.argyll.ccss_maker import make_ccss
from kelvincal.argyll.dispread_runner import PROMPT_CALIBRATE, PROMPT_PLACE, PipelineCancelled, prompt_kind
from kelvincal.argyll.instruments import parse_spotread_usage

# Behaves like dispread with a spectrometer: calibration prompt, placement prompt (keys read in cbreak mode
# like ArgyllCMS), then the -C hook for every patch of the .ti1 and a .ti3 with the result.
FAKE_DISPREAD = f"""#!{sys.executable}
import subprocess, sys, termios, tty
args = sys.argv[1:]
hook = args[args.index("-C") + 1]
base = args[-1]
tty.setcbreak(0)
def ask(text):
    sys.stdout.write(text); sys.stdout.flush()
    key = sys.stdin.read(1)
    sys.stdout.write("\\n")
    if key in "qQ\\x1b":
        sys.exit(1)
ask("Place cap on the instrument, or place on a dark surface,\\nor place on the calibration reference,\\n"
    " and then hit any key to continue,\\n or hit Esc or Q to abort: ")
print("Calibration complete")
ask("Place instrument on test window.\\n Hit Esc or Q to give up, any other key to continue: ")
rows = open(base + ".ti1").read().split("BEGIN_DATA\\n")[1].split("END_DATA")[0].split("\\n")
for row in filter(None, rows):
    r, g, b = (round(float(v) * 2.55) for v in row.split()[1:4])
    subprocess.run(hook.split() + [str(r), str(g), str(b)], check=True)
open(base + ".ti3", "w").write("CTI3\\nSPECTRAL_BANDS 36\\n" + " ".join(args))
"""

FAKE_CCXXMAKE = f"""#!{sys.executable}
import sys
open(sys.argv[-1], "w").write("CCSS\\nDESCRIPTOR " + repr(" ".join(sys.argv[1:])) + "\\n")
"""


class PromptAndInstrumentTest(unittest.TestCase):
    def test_prompt_kind(self) -> None:
        self.assertEqual(prompt_kind("Place cap on the instrument, or place on a dark surface ... any key"),
                         PROMPT_CALIBRATE)
        self.assertEqual(prompt_kind("Place instrument on test window.\n Hit Esc or Q to give up, any other key"),
                         PROMPT_PLACE)
        self.assertEqual(prompt_kind("\nCalibration complete\nPlace instrument on test window.\n any other key"),
                         PROMPT_PLACE)

    def test_spectrometer_ports(self) -> None:
        status = parse_spotread_usage(
            " -c listno            Set instrument port from the following list (default 1)\n"
            "    1 = '/dev/bus/usb/003/097 (X-Rite i1 DisplayPro, ColorMunki Display)'\n"
            "    2 = '/dev/bus/usb/001/008 (GretagMacbeth i1 Pro)'\n")
        self.assertEqual(status.ports, [1, 2])
        self.assertEqual(status.spectrometers(), [(2, "GretagMacbeth i1 Pro")])


class MakeCcssTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        bindir = self.dir / "bin"
        bindir.mkdir()
        for name, text in (("dispread", FAKE_DISPREAD), ("ccxxmake", FAKE_CCXXMAKE)):
            f = bindir / name
            f.write_text(text)
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        self.old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{bindir}{os.pathsep}{self.old_path}"

    def tearDown(self) -> None:
        os.environ["PATH"] = self.old_path
        self.tmp.cleanup()

    def test_prompts_patches_and_output(self) -> None:
        prompts: list[str] = []
        patches: list[tuple[int, int, int]] = []
        out = self.dir / "corr" / "DP-2.ccss"
        result = make_ccss(2, out, "LEN P32p-20", lambda rgb, i, n: patches.append(rgb),
                           lambda kind, text: prompts.append(kind) or True)
        self.assertEqual(prompts, [PROMPT_CALIBRATE, PROMPT_PLACE])
        self.assertEqual(patches, [(255, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255)])
        self.assertEqual(result, out)
        args = out.read_text().split("DESCRIPTOR ", 1)[1]
        self.assertIn("-S -f ", args)
        self.assertIn("-I LEN P32p-20 -E KelvinCal LEN P32p-20", args)
        dispread_args = out.with_suffix(".ti3").read_text()
        self.assertIn("-c 2 -H -s", dispread_args)

    def test_declined_prompt_cancels(self) -> None:
        with self.assertRaises(PipelineCancelled):
            make_ccss(2, self.dir / "x.ccss", "X", lambda *a: None, lambda kind, text: False)
        self.assertFalse((self.dir / "x.ccss").exists())


if __name__ == "__main__":
    unittest.main()
