"""Preset manager page (mockup 1h): preset list | details with per-monitor comparison and drift banner."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kcal_core.i18n import translate
from kcal_core.models import DisplayInfo, Preset
from kcal_gui.fmt import num, pct
from kcal_gui.screens import screen_geometries
from kcal_gui.widgets import MessageBanner, SecondaryLabel, Separator, title_font
from kcal_presets.manager import match_display, preset_drift

ROWS = (
    ("ddc_brightness", "brightness", "0x10"),
    ("ddc_contrast", "contrast", "0x12"),
    ("ddc_red_gain", "red_gain", "0x16"),
    ("ddc_green_gain", "green_gain", "0x18"),
    ("ddc_blue_gain", "blue_gain", "0x1A"),
)


class PresetsPage(QWidget):
    capture_requested = Signal()
    from_profiles_requested = Signal()
    activate_requested = Signal(str)
    duplicate_requested = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    recalibrate_requested = Signal(str)   # connector
    inspect_requested = Signal(str)       # ICC path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.presets: list[Preset] = []
        self.active = ""
        self.displays: list[DisplayInfo] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 16)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        lay.addWidget(split)
        self.splitter = split

        # No boxes around the two halves: list and details sit on the window background, a line separates them.
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 12, 0)
        left_lay.setSpacing(6)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.currentItemChanged.connect(lambda *_: self._show_selected())
        self.list.itemDoubleClicked.connect(lambda item: self.activate_requested.emit(self._name(item)))
        left_lay.addWidget(self.list, 1)
        left_lay.addWidget(SecondaryLabel(translate("PresetsPage", "Ctrl+1–9 activates the first nine presets.")))
        self.btn_capture = QPushButton(translate("PresetsPage", "Save Current State as Preset…"))
        self.btn_capture.clicked.connect(self.capture_requested)
        left_lay.addWidget(self.btn_capture)
        self.btn_from_profiles = QPushButton(translate("PresetsPage", "Create from Calibrations…"))
        self.btn_from_profiles.setToolTip(translate(
            "PresetsPage", "One preset per target from the newest calibrated profile of every display"))
        self.btn_from_profiles.clicked.connect(self.from_profiles_requested)
        left_lay.addWidget(self.btn_from_profiles)
        split.addWidget(left)

        right = QWidget()
        right_row = QHBoxLayout(right)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(12)
        right_row.addWidget(Separator(vertical=True))
        right_body = QVBoxLayout()
        right_body.setSpacing(8)
        right_row.addLayout(right_body, 1)
        top = QHBoxLayout()
        col = QVBoxLayout()
        self.name_label = QLabel()
        self.name_label.setFont(title_font(self, 1.3))
        self.meta_label = SecondaryLabel()
        self.meta_label.setWordWrap(True)
        col.addWidget(self.name_label)
        col.addWidget(self.meta_label)
        top.addLayout(col, 1)
        self.btn_duplicate = QPushButton(translate("PresetsPage", "Duplicate"))
        self.btn_rename = QPushButton(translate("PresetsPage", "Rename…"))
        self.btn_delete = QPushButton(translate("PresetsPage", "Delete"))
        self.btn_activate = QPushButton(translate("PresetsPage", "Activate"))
        self.btn_activate.setDefault(True)
        for btn, sig in ((self.btn_duplicate, self.duplicate_requested), (self.btn_rename, self.rename_requested),
                         (self.btn_delete, self.delete_requested), (self.btn_activate, self.activate_requested)):
            btn.clicked.connect(lambda _=False, s=sig: self._emit_selected(s))
            top.addWidget(btn)
        right_body.addLayout(top)

        self.drift = MessageBanner(kind="warning")
        self.btn_drift = self.drift.addAction(translate("PresetsPage", "Recalibrate this display…"),
                                              self._recalibrate_drift)
        self.drift.hide()
        right_body.addWidget(self.drift)

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Read-only comparison: no selection, headers are labels only (actions sit in the last row per display).
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for header in (self.table.horizontalHeader(), self.table.verticalHeader()):
            header.setHighlightSections(False)
            header.setSectionsClickable(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setWordWrap(False)       # one line per row: long ICC names are elided, heights stay fixed
        right_body.addWidget(self.table)

        note = SecondaryLabel(translate(
            "PresetsPage",
            "Displays are matched by EDID hash (connector as fallback). Values in brackets are the live "
            "values if they differ from the preset. “Recalibrate…” opens the calibration of that display; at the "
            "end “Also update in preset” is preselected.",
        ))
        note.setWordWrap(True)
        right_body.addWidget(note)
        right_body.addStretch(1)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        self._columns: list[tuple[str, str]] = []  # (connector, icc path) per table column
        self.column_buttons: list[tuple[QPushButton, QPushButton]] = []  # (recalibrate, show profile) per column
        self._busy = False
        self._show_selected()

    # ------------------------------------------------------------------ public API

    def set_data(self, active: str, presets: list[Preset], displays: list[DisplayInfo]) -> None:
        current = self.selected_name() or active
        self.active, self.presets, self.displays = active, presets, displays
        self.list.blockSignals(True)
        self.list.clear()
        for i, p in enumerate(presets):
            badge = translate("PresetsPage", "active") if p.name == active else ""
            sub = translate("PresetsPage", "{count} displays").format(count=len(p.displays))
            item = QListWidgetItem(f"{p.name}{'  · ' + badge if badge else ''}\n{sub}")
            item.setData(Qt.ItemDataRole.UserRole, p.name)
            if i < 9:
                item.setToolTip(f"Ctrl+{i + 1}")
            if p.name == active:
                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
            self.list.addItem(item)
            if p.name == current:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._show_selected()

    def selected_name(self) -> str:
        item = self.list.currentItem()
        return self._name(item) if item else ""

    def set_busy(self, busy: bool) -> None:
        for w in (self.btn_capture, self.btn_from_profiles, self.btn_activate, self.btn_duplicate, self.btn_rename, self.btn_delete,
                  self.btn_drift, *(recal for recal, _show in self.column_buttons)):
            w.setEnabled(not busy)
        self._busy = busy
        if not busy:
            self._show_selected()

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _name(item: QListWidgetItem) -> str:
        return str(item.data(Qt.ItemDataRole.UserRole))

    def _emit_selected(self, signal) -> None:  # noqa: ANN001
        name = self.selected_name()
        if name:
            signal.emit(name)

    def _show_selected(self) -> None:
        preset = next((p for p in self.presets if p.name == self.selected_name()), None)
        has = preset is not None
        for btn in (self.btn_activate, self.btn_duplicate, self.btn_rename, self.btn_delete):
            btn.setEnabled(has)
        if preset is None:
            self.name_label.setText(translate("PresetsPage", "No preset"))
            self.meta_label.setText(translate(
                "PresetsPage", "Save the current display state to switch back to it later with one click."
            ))
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.table.hide()
            self.drift.hide()
            self._columns = []
            self.column_buttons = []
            return
        is_active = preset.name == self.active
        self.name_label.setText(preset.name)
        self.meta_label.setText(
            (translate("PresetsPage", "Active · ") if is_active else "")
            + (preset.description or translate("PresetsPage", "{count} displays").format(count=len(preset.displays)))
        )
        self.btn_activate.setText(translate("PresetsPage", "Active") if is_active else translate("PresetsPage", "Activate"))
        self.btn_activate.setEnabled(not is_active)

        drift = preset_drift(preset, self.displays) if is_active else {}
        self._fill_table(preset, drift)
        if drift:
            connector = next(iter(drift))
            fields = ", ".join(self._field_label(f) for f in drift[connector])
            self.drift.setText(translate(
                "PresetsPage", "<b>{connector} differs from the preset:</b> {fields}."
            ).format(connector=connector, fields=fields))
            self._drift_connector = connector
            self.drift.show()
        else:
            self.drift.hide()

    def _field_label(self, field: str) -> str:
        labels = {
            "ddc_brightness": translate("PresetsPage", "Brightness"),
            "ddc_contrast": translate("PresetsPage", "Contrast"),
            "ddc_red_gain": translate("PresetsPage", "Gain red"),
            "ddc_green_gain": translate("PresetsPage", "Gain green"),
            "ddc_blue_gain": translate("PresetsPage", "Gain blue"),
            "icc_profile": translate("PresetsPage", "ICC profile"),
        }
        return labels.get(field, field)

    def _ordered_entries(self, preset: Preset) -> list:
        """Preset entries in desktop order (left to right, then top to bottom); unplaced displays last."""
        geometries = screen_geometries()

        def key(item: tuple[int, object]) -> tuple:
            index, entry = item
            live = match_display(entry, self.displays)
            g = geometries.get(live.connector if live else entry.connector)
            return (0, g.x(), g.y(), index) if g is not None and not g.isEmpty() else (1, 0, 0, index)

        return [entry for _i, entry in sorted(enumerate(preset.displays), key=key)]

    def _fill_table(self, preset: Preset, drift: dict[str, list[str]]) -> None:
        self.table.clear()
        self.table.show()
        self.table.setColumnCount(len(preset.displays))
        self.table.setRowCount(len(ROWS) + 2)
        self.table.setVerticalHeaderLabels(
            [f"{self._field_label(attr)} · {vcp}" for attr, _d, vcp in ROWS] + ["ICC", ""]
        )
        self._columns = []
        self.column_buttons = []
        headers = []
        for col, entry in enumerate(self._ordered_entries(preset)):
            live = match_display(entry, self.displays)
            connector = live.connector if live else entry.connector
            headers.append(f"{connector}\n{entry.model}")
            self._columns.append((connector, entry.icc_profile))
            differing = drift.get(connector, [])
            for row, (attr, ddc_attr, _vcp) in enumerate(ROWS):
                stored = getattr(entry, attr)
                text = num(stored)
                if attr in differing and live is not None:
                    text += "  " + translate("PresetsPage", "(live {value})").format(
                        value=num(getattr(live.ddc, ddc_attr)))
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if attr in differing:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, col, item)
            icc = Path(entry.icc_profile).name if entry.icc_profile else entry.color_profile_source
            if entry.compositor_brightness != 1.0:
                icc += f" · {pct(entry.compositor_brightness * 100)}"
            item = QTableWidgetItem(icc)
            item.setToolTip(entry.icc_profile)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(len(ROWS), col, item)
            self.table.setCellWidget(len(ROWS) + 1, col, self._column_actions(connector, entry.icc_profile))
        self.table.setHorizontalHeaderLabels(headers)
        if self.column_buttons:
            self.table.setRowHeight(len(ROWS) + 1,
                                    max(w.sizeHint().height() for w in self._action_cells()))
        self._fit_table_height()

    def _action_cells(self) -> list[QWidget]:
        return [self.table.cellWidget(len(ROWS) + 1, c) for c in range(self.table.columnCount())]

    def _column_actions(self, connector: str, icc: str) -> QWidget:
        """"Recalibrate…" and "Show Profile" for one display column (mockup 1h)."""
        cell = QWidget()
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        recal = QPushButton(translate("PresetsPage", "Recalibrate…"))
        recal.setEnabled(not self._busy and any(d.connector == connector for d in self.displays))
        recal.clicked.connect(lambda: self.recalibrate_requested.emit(connector))
        show = QPushButton(translate("PresetsPage", "Show Profile"))
        show.setFlat(True)
        show.setEnabled(bool(icc) and Path(icc).exists())
        show.clicked.connect(lambda: self.inspect_requested.emit(icc))
        lay.addWidget(recal)
        lay.addWidget(show)
        self.column_buttons.append((recal, show))
        return cell

    def _fit_table_height(self) -> None:
        """Table only as high as its rows, so no empty grid area is left below them."""
        t = self.table
        height = t.horizontalHeader().sizeHint().height() + 2 * t.frameWidth()
        height += sum(t.rowHeight(r) for r in range(t.rowCount()))
        if t.horizontalScrollBar().isVisible():
            height += t.horizontalScrollBar().height()
        t.setFixedHeight(height)

    def _recalibrate_drift(self) -> None:
        connector = getattr(self, "_drift_connector", "")
        if connector:
            self.recalibrate_requested.emit(connector)
