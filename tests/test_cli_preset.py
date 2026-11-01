"""kelvincal-cli apply-preset with a running GUI: returns only when the GUI has applied the preset."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from kelvincal.gui import cli


def _statuses(*states: dict):  # noqa: ANN202
    """Fake D-Bus: ApplyPreset is accepted, then Status returns `states` one after another."""
    replies = iter(states)

    def call(method: str, *_args: str) -> tuple[bool, str]:
        if method == "ApplyPreset":
            return True, ""
        return True, json.dumps(next(replies))

    return call


class ApplyPresetViaGuiTest(unittest.TestCase):
    def _run(self, *states: dict) -> int:
        args = cli.build_parser().parse_args(["apply-preset", "Office"])
        with mock.patch.object(cli, "_running_gui", _statuses(*states)), mock.patch.object(cli.time, "sleep"):
            return cli.cmd_apply_preset(args)

    def test_waits_until_applied(self) -> None:
        busy = {"active_preset": "Photo", "busy": False, "applying": "Office", "preset_error": ""}
        done = {"active_preset": "Office", "busy": False, "applying": "", "preset_error": ""}
        with mock.patch("builtins.print") as out:
            self.assertEqual(self._run(busy, busy, done), 0)
        self.assertIn("applied by the running KelvinCal", out.call_args.args[0])

    def test_reports_failure(self) -> None:
        failed = {"active_preset": "Photo", "busy": False, "applying": "", "preset_error": "DP-1: DDC write failed"}
        with mock.patch("builtins.print") as out:
            self.assertEqual(self._run(failed), 1)
        self.assertIn("DDC write failed", out.call_args.args[0])

    def test_older_gui_without_status_fields(self) -> None:
        with mock.patch("builtins.print"):
            self.assertEqual(self._run({"active_preset": "Office", "busy": False}), 0)


if __name__ == "__main__":
    unittest.main()
