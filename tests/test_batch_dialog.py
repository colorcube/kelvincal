"""Batch calibration dialogs: target selection (remembered), time estimate, summary table."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kcal_argyll.profile_pipeline import ProfileConfig  # noqa: E402
from kcal_core.models import ColorMeasurement  # noqa: E402
from kcal_core.targets import TARGETS  # noqa: E402
from kcal_gui.batch_dialog import BatchSetupDialog, BatchSummaryDialog  # noqa: E402
from kcal_gui.controller import BatchItem, BatchItemResult  # noqa: E402
from kcal_gui.pages.running import RunningPage  # noqa: E402
from kcal_gui.widgets.run_views import STATE_PENDING, STATE_SKIPPED  # noqa: E402


class BatchDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.tmp.name)

    def test_selection_estimate_and_memory(self) -> None:
        QSettings().remove("batch")
        dlg = BatchSetupDialog(list(TARGETS), "Dell (DP-2)", preselect="office")
        self.assertEqual([t.key for t in dlg.selected_targets()], ["office"])
        dlg.table.item(5, 0).setCheckState(Qt.CheckState.Checked)        # evening
        self.assertEqual([t.key for t in dlg.selected_targets()], ["office", "evening"])
        minutes = TARGETS[1].estimated_minutes() + TARGETS[5].estimated_minutes() + 2
        self.assertIn(f"{minutes // 60} h {minutes % 60} min", dlg.total.text())
        dlg.check_verify.setChecked(False)
        dlg._accept()
        again = BatchSetupDialog(list(TARGETS), "Dell (DP-2)", preselect="photo")
        self.assertEqual([t.key for t in again.selected_targets()], ["office", "evening"])
        self.assertFalse(again.verify)
        for row in range(again.table.rowCount()):
            again.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertFalse(again.btn_start.isEnabled())

    def test_summary_lists_failures(self) -> None:
        item = BatchItem("office", "Office", 140, None, ProfileConfig(monitor_name="x"))
        ok = BatchItemResult(item, ddc=(30, 70, 100, 97, 90), white=ColorMeasurement((255,) * 3, 95, 100, 109),
                             profile_path=Path("/tmp/KelvinCal_DP-2_office.icc"))
        bad = BatchItemResult(BatchItem("video", "Video", 100, None, ProfileConfig(monitor_name="y")),
                              error="colprof failed")
        dlg = BatchSummaryDialog([ok, bad], "Dell (DP-2)")
        self.assertEqual(dlg.table.rowCount(), 2)
        self.assertEqual(dlg.table.item(0, 2).text(), "30/70/100/97/90")
        self.assertIn("colprof failed", dlg.table.item(1, 1).text())

    def test_running_page_resets_per_target(self) -> None:
        page = RunningPage()
        page.begin("x", "DP-2", ("1a", "1b", "2", "3"), (40, 90))
        page.on_batch_item(1, 2, "Office")
        page.on_phase_finished("1b")
        page.on_batch_item(2, 2, "Evening")
        self.assertIn("2 / 2", page.title.text())
        self.assertEqual(page.stepper.state("1a"), STATE_SKIPPED)
        self.assertEqual(page.stepper.state("1b"), STATE_PENDING)


if __name__ == "__main__":
    unittest.main()
