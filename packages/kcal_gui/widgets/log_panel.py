"""Collapsible measurement & diagnostic log with copy/export."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kcal_core.i18n import translate
from kcal_gui.widgets.basic import mono_font


class LogPanel(QWidget):
    """Timestamped, read-only log. The header toggles the text area."""

    expandedChanged = Signal(bool)  # noqa: N815

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self.toggle = QToolButton()
        self.toggle.setText(translate("LogPanel", "Measurement & Diagnostic Log").replace("&", "&&"))
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setAutoRaise(True)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.toggled.connect(self.setExpanded)
        btn_copy = QPushButton(translate("LogPanel", "Copy"))
        btn_copy.setFlat(True)
        btn_copy.clicked.connect(self.copy_all)
        btn_export = QPushButton(translate("LogPanel", "Export…"))
        btn_export.setFlat(True)
        btn_export.clicked.connect(self.export)
        head.addWidget(self.toggle)
        head.addStretch(1)
        head.addWidget(btn_copy)
        head.addWidget(btn_export)
        lay.addLayout(head)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(mono_font())
        self.view.setMaximumBlockCount(5000)
        self.view.setPlaceholderText(translate("LogPanel", "Measurement and diagnostic log..."))
        lay.addWidget(self.view)
        self._update_arrow()

    def append(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.view.appendPlainText(f"{stamp}  {message}")

    def text(self) -> str:
        return self.view.toPlainText()

    def isExpanded(self) -> bool:  # noqa: N802
        return self.toggle.isChecked()

    def setExpanded(self, expanded: bool) -> None:  # noqa: N802
        self.toggle.setChecked(expanded)
        self.view.setVisible(expanded)
        self._update_arrow()
        self.expandedChanged.emit(expanded)

    def _update_arrow(self) -> None:
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if self.toggle.isChecked() else Qt.ArrowType.RightArrow
        )

    def copy_all(self) -> None:
        QGuiApplication.clipboard().setText(self.text())

    def export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate("LogPanel", "Export Log"),
            f"kelvincal-{datetime.now():%Y-%m-%d_%H-%M}.log",
            translate("LogPanel", "Log files (*.log *.txt)"),
        )
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.text() + "\n")
