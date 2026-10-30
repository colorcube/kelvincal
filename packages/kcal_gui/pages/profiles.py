"""ICC library page: profiles in the user ICC directory; double-click opens the inspector."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

from PySide6.QtCore import QDateTime, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kcal_argyll.profile_inspector import read_profile_summary
from kcal_core.i18n import translate
from kcal_core.models import DisplayInfo
from kcal_core.paths import user_icc_dir
from kcal_gui.widgets import SecondaryLabel


class ProfilesPage(QWidget):
    inspect_requested = Signal(str)  # ICC path
    open_file_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 16)
        self.dir_label = SecondaryLabel()
        lay.addWidget(self.dir_label)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            translate("ProfilesPage", "Description"),
            translate("ProfilesPage", "In use on"),
            translate("ProfilesPage", "Type"),
            translate("ProfilesPage", "Created"),
            translate("ProfilesPage", "File"),
        ])
        self.tree.setRootIsDecorated(False)
        self.tree.setSortingEnabled(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemDoubleClicked.connect(lambda item, _c: self.inspect_requested.emit(self._path(item)))
        self.tree.currentItemChanged.connect(lambda *_: self._update_buttons())
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.btn_inspect = QPushButton(translate("ProfilesPage", "Open in Inspector"))
        self.btn_inspect.clicked.connect(lambda: self._emit_current())
        btn_other = QPushButton(translate("ProfilesPage", "Open Other File…"))
        btn_other.clicked.connect(self.open_file_requested)
        btn_folder = QPushButton(translate("ProfilesPage", "Show Folder"))
        btn_folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(user_icc_dir())))
        )
        row.addWidget(self.btn_inspect)
        row.addWidget(btn_other)
        row.addStretch(1)
        row.addWidget(btn_folder)
        lay.addLayout(row)
        self._update_buttons()

    def refresh(self, displays: list[DisplayInfo]) -> None:
        directory = user_icc_dir()
        self.dir_label.setText(str(directory))
        in_use: dict[str, list[str]] = {}
        for d in displays:
            if d.icc_profile_path and d.color_profile_source == "ICC":
                in_use.setdefault(str(Path(d.icc_profile_path).resolve()), []).append(d.connector)
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        files = sorted(directory.glob("*.ic[cm]")) if directory.is_dir() else []
        for path in files:
            try:
                s = read_profile_summary(path)
            except (OSError, ValueError):
                continue
            item = QTreeWidgetItem([
                s.description,
                ", ".join(in_use.get(str(path.resolve()), [])),
                s.profile_type,
                "",
                path.name,
            ])
            if s.created is not None:
                # QDateTime as display data: shown in the locale format and sorted chronologically.
                stamp = int(s.created.replace(tzinfo=timezone.utc).timestamp())
                item.setData(3, Qt.ItemDataRole.DisplayRole, QDateTime.fromSecsSinceEpoch(stamp))
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(4, str(path))
            self.tree.addTopLevelItem(item)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        for col in range(1, 5):
            self.tree.resizeColumnToContents(col)
        self._update_buttons()

    @staticmethod
    def _path(item: QTreeWidgetItem) -> str:
        return str(item.data(0, Qt.ItemDataRole.UserRole))

    def _emit_current(self) -> None:
        item = self.tree.currentItem()
        if item is not None:
            self.inspect_requested.emit(self._path(item))

    def _update_buttons(self) -> None:
        self.btn_inspect.setEnabled(self.tree.currentItem() is not None)
