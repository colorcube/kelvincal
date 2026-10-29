"""Collapsible measurement & diagnostic log with copy/export."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

QWIDGETSIZE_MAX = (1 << 24) - 1

from kcal_core.i18n import translate
from kcal_gui.widgets.basic import mono_font


class LogPanel(QWidget):
    """Timestamped, read-only log. The header is a disclosure button (like KCollapsibleGroupBox).

    Collapsed, the panel shrinks to its header; inside a QSplitter the freed space goes to the
    other widgets and the previous splitter sizes come back on expanding.
    """

    expandedChanged = Signal(bool)  # noqa: N815

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.setSpacing(2)
        self.toggle = QToolButton()
        self.toggle.setText(translate("LogPanel", "Measurement & Diagnostic Log").replace("&", "&&"))
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setAutoRaise(True)
        self.toggle.clicked.connect(lambda: self.setExpanded(not self._expanded))
        self.btn_copy = self._tool_button("edit-copy", translate("LogPanel", "Copy"), self.copy_all)
        self.btn_export = self._tool_button("document-export", translate("LogPanel", "Export…"), self.export)
        head.addWidget(self.toggle)
        head.addStretch(1)
        head.addWidget(self.btn_copy)
        head.addWidget(self.btn_export)
        lay.addLayout(head)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(mono_font())
        self.view.setMaximumBlockCount(5000)
        self.view.setPlaceholderText(translate("LogPanel", "Measurement and diagnostic log..."))
        lay.addWidget(self.view)
        self._expanded = True
        self._splitter_sizes: list[int] | None = None
        self._update_header()

    @staticmethod
    def _tool_button(icon: str, text: str, slot) -> QToolButton:  # noqa: ANN001
        btn = QToolButton()
        btn.setIcon(QIcon.fromTheme(icon))
        btn.setText(text)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setAutoRaise(True)
        btn.clicked.connect(slot)
        return btn

    def append(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.view.appendPlainText(f"{stamp}  {message}")

    def text(self) -> str:
        return self.view.toPlainText()

    def isExpanded(self) -> bool:  # noqa: N802
        return self._expanded

    def setExpanded(self, expanded: bool) -> None:  # noqa: N802
        if expanded == self._expanded:
            return
        splitter = self.parentWidget() if isinstance(self.parentWidget(), QSplitter) else None
        if not expanded and splitter is not None:
            self._splitter_sizes = splitter.sizes()
        self._expanded = expanded
        self.view.setVisible(expanded)
        self._update_header()
        if expanded:
            self.setMaximumHeight(QWIDGETSIZE_MAX)
            if splitter is not None:
                sizes = self._splitter_sizes or splitter.sizes()
                idx = splitter.indexOf(self)
                minimum = 6 * self.fontMetrics().lineSpacing()
                if sizes[idx] < minimum:  # e.g. state saved while collapsed
                    other = max(range(len(sizes)), key=lambda i: -1 if i == idx else sizes[i])
                    sizes[other] = max(0, sizes[other] - (minimum * 2 - sizes[idx]))
                    sizes[idx] = minimum * 2
                splitter.setSizes(sizes)
        else:
            self.setMaximumHeight(self.toggle.sizeHint().height() + 2)
        self.expandedChanged.emit(expanded)

    def _update_header(self) -> None:
        self.toggle.setIcon(QIcon.fromTheme("arrow-down" if self._expanded else "arrow-right"))
        self.btn_copy.setVisible(self._expanded)
        self.btn_export.setVisible(self._expanded)

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
