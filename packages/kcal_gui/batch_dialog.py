"""Batch calibration: choosing the targets before the run and the summary afterwards."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QBrush, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kcal_core.i18n import translate
from kcal_core.targets import CalibrationTarget, batch_targets
from kcal_core.verification import TOL_MAX, TOL_MEAN, grade
from kcal_gui.controller import BatchItemResult
from kcal_gui.fmt import cdm2, num
from kcal_gui.theme import status_colors
from kcal_gui.widgets import SecondaryLabel, title_font

VERIFY_MINUTES = 1        # 42 spot measurements
SETTINGS_TARGETS = "batch/targets"
SETTINGS_VERIFY = "batch/verify"


def _table(columns: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    return table


def _cell(text: str, align_right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class BatchSetupDialog(QDialog):
    """Lists the targets (with the settings of the target cards) to pick for a batch run."""

    def __init__(self, targets: list[CalibrationTarget], display_label: str,
                 preselect: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.targets = targets
        self.setWindowTitle(translate("BatchDialog", "Batch Calibration"))
        lay = QVBoxLayout(self)
        head = QLabel(translate("BatchDialog", "Calibrate several targets on {display}").format(display=display_label))
        head.setFont(title_font(self, 1.1))
        lay.addWidget(head)
        intro = SecondaryLabel(translate(
            "BatchDialog",
            "The sensor is placed once; the targets then run one after another without any questions "
            "(contrast search once, then whitepoint, patches, profile and verification per target). "
            "Every profile is saved with its hardware settings. Afterwards the display returns to its "
            "previous state, ready to combine the profiles into presets."))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        settings = QSettings()
        saved = settings.value(SETTINGS_TARGETS, "", type=str)
        checked = set(saved.split(",")) if saved else {preselect}
        self.targets = targets = batch_targets(targets)
        self.table = _table([translate("BatchDialog", "Target"), translate("BatchDialog", "Luminance"),
                             translate("BatchDialog", "Whitepoint"), translate("BatchDialog", "Tone curve"),
                             translate("BatchDialog", "Patches"), translate("BatchDialog", "Duration")])
        for t in targets:
            row = self.table.rowCount()
            self.table.insertRow(row)
            first = _cell(t.variant_title)
            first.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            first.setCheckState(Qt.CheckState.Checked if t.variant_key in checked else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, first)
            self.table.setItem(row, 1, _cell(cdm2(t.luminance, 0), True))
            self.table.setItem(row, 2, _cell(t.whitepoint_label))
            self.table.setItem(row, 3, _cell(t.tone_label))
            self.table.setItem(row, 4, _cell(num(t.patch_count), True))
            self.table.setItem(row, 5, _cell(translate("BatchDialog", "{minutes} min").format(
                minutes=t.estimated_minutes()), True))
        self.table.itemChanged.connect(self._update)
        lay.addWidget(self.table, 1)

        self.check_verify = QCheckBox(translate("BatchDialog", "Verify every profile (ΔE00, approx. 1 min each)"))
        self.check_verify.setChecked(settings.value(SETTINGS_VERIFY, True, type=bool))
        self.check_verify.toggled.connect(self._update)
        lay.addWidget(self.check_verify)
        self.total = QLabel()
        lay.addWidget(self.total)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.btn_start = buttons.addButton(translate("BatchDialog", "Start Batch"),
                                           QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_start.setDefault(True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(720, 460)
        self._update()

    def selected_targets(self) -> list[CalibrationTarget]:
        return [t for row, t in enumerate(self.targets)
                if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]

    @property
    def verify(self) -> bool:
        return self.check_verify.isChecked()

    def _update(self, *_args: object) -> None:
        chosen = self.selected_targets()
        minutes = sum(t.estimated_minutes() + (VERIFY_MINUTES if self.verify else 0) for t in chosen)
        self.total.setText(translate("BatchDialog", "{count} targets · approx. {hours} h {minutes} min in total")
                           .format(count=len(chosen), hours=minutes // 60, minutes=minutes % 60))
        self.btn_start.setEnabled(bool(chosen))

    def _accept(self) -> None:
        settings = QSettings()
        settings.setValue(SETTINGS_TARGETS, ",".join(t.variant_key for t in self.selected_targets()))
        settings.setValue(SETTINGS_VERIFY, self.verify)
        self.accept()


class BatchSummaryDialog(QDialog):
    """Result per target: saved profile, hardware state, white and verification."""

    def __init__(self, results: list[BatchItemResult], display_label: str, parent: QWidget | None = None,
                 create_presets: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(translate("BatchDialog", "Batch Calibration"))
        lay = QVBoxLayout(self)
        ok = sum(r.ok for r in results)
        head = QLabel(translate("BatchDialog", "{ok} of {total} targets calibrated · {display}").format(
            ok=ok, total=len(results), display=display_label))
        head.setFont(title_font(self, 1.1))
        lay.addWidget(head)

        colors = status_colors(self.palette())
        brush = {"ok": QBrush(colors.ok), "warning": QBrush(colors.warning), "error": QBrush(colors.error)}
        self.table = _table([translate("BatchDialog", "Target"), translate("BatchDialog", "White"),
                             translate("BatchDialog", "DDC B/C/R/G/B"), "Ø ΔE00", "max ΔE00",
                             translate("BatchDialog", "Profile")])
        for r in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, _cell(r.item.label))
            if not r.ok:
                err = _cell("⚠ " + r.error)
                err.setForeground(brush["error"])
                self.table.setItem(row, 1, err)
                self.table.setSpan(row, 1, 1, 5)
                continue
            w = r.white
            self.table.setItem(row, 1, _cell(f"{w.cct_kelvin:.0f} K · {cdm2(w.Y)}" if w else "–", True))
            self.table.setItem(row, 2, _cell("/".join(map(str, r.ddc)) if r.ddc else "–", True))
            v = r.verification
            for col, value, tol in ((3, v.mean if v else None, TOL_MEAN),
                                    (4, v.maximum.delta_e if v and v.maximum else None, TOL_MAX)):
                item = _cell(num(value, 2) if value is not None else "–", True)
                if value is not None:
                    item.setForeground(brush[grade(value, tol)])
                self.table.setItem(row, col, item)
            self.table.setItem(row, 5, _cell(r.profile_path.name if r.profile_path else "–"))
        lay.addWidget(self.table, 1)
        hint = SecondaryLabel(translate(
            "BatchDialog", "The profiles are in the profile library; their hardware settings are stored next to "
            "them, so the inspector can switch the display to them."))
        hint.setWordWrap(True)
        lay.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        folder = next((r.profile_path.parent for r in results if r.profile_path), None)
        if folder is not None:
            btn = QPushButton(translate("BatchDialog", "Open Profile Folder"))
            btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))))
            buttons.addButton(btn, QDialogButtonBox.ButtonRole.ActionRole)
        if create_presets is not None and any(r.ok for r in results):
            btn = QPushButton(translate("BatchDialog", "Create Presets…"))
            btn.clicked.connect(create_presets)
            buttons.addButton(btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)
        self.resize(820, 360)
