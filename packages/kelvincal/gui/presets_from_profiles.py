"""Dialog: create or update presets from calibrated profiles (one preset per target)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kelvincal.core.i18n import translate
from kelvincal.core.models import DisplayInfo
from kelvincal.presets.from_profiles import PresetProposal
from kelvincal.gui.widgets import SecondaryLabel, title_font


def _date(iso: str) -> str:
    try:
        return QLocale().toString(datetime.fromisoformat(iso), QLocale.FormatType.ShortFormat)
    except ValueError:
        return iso or "?"


class PresetsFromProfilesDialog(QDialog):
    """Rows: proposed presets (checkable); columns: the displays with the profile that would be used."""

    def __init__(self, proposals: list[PresetProposal], displays: list[DisplayInfo],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.proposals = proposals
        self.setWindowTitle(translate("PresetsFromProfiles", "Presets from Calibrations"))
        lay = QVBoxLayout(self)
        head = QLabel(translate("PresetsFromProfiles", "Create presets from calibrated profiles"))
        head.setFont(title_font(self, 1.1))
        lay.addWidget(head)
        intro = SecondaryLabel(translate(
            "PresetsFromProfiles",
            "One preset per target with the newest profile of every display and the hardware settings it was "
            "measured with. Displays without a profile for a target are not changed by that preset; an existing "
            "preset of the same name keeps its entries for them."))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        columns = [translate("PresetsFromProfiles", "Preset")]
        columns += [f"{d.connector}\n{d.model}" for d in displays]
        columns.append(translate("PresetsFromProfiles", "Action"))
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for prop in proposals:
            row = self.table.rowCount()
            self.table.insertRow(row)
            first = QTableWidgetItem(prop.name)
            first.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            first.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, first)
            for col, d in enumerate(displays, start=1):
                meta = prop.profiles.get(d.connector)
                item = QTableWidgetItem(_date(meta.created) if meta else "–")
                if meta:
                    item.setToolTip(f"{meta.icc_path.name}\nDDC {'/'.join(map(str, meta.ddc))}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
            action = translate("PresetsFromProfiles", "update") if prop.exists \
                else translate("PresetsFromProfiles", "new")
            self.table.setItem(row, len(columns) - 1, QTableWidgetItem(action))
        self.table.itemChanged.connect(self._update)
        lay.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.btn_ok = buttons.addButton(translate("PresetsFromProfiles", "Create / Update"),
                                        QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_ok.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(760, 380)

    def selected(self) -> list[PresetProposal]:
        return [p for row, p in enumerate(self.proposals)
                if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def _update(self, *_args: object) -> None:
        self.btn_ok.setEnabled(bool(self.selected()))
