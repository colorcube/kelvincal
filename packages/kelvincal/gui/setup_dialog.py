"""Dialog "Check Setup": the results of `kelvincal.core.setup_check` with the command that fixes each problem.

Shown from the Help menu, and at start when something essential is missing (can be turned off).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kelvincal.core.i18n import translate
from kelvincal.core.setup_check import ERROR, INFO, OK, WARNING, Check
from kelvincal.gui.widgets import SecondaryLabel

CHECK_ON_START_KEY = "setup/check_on_start"

_ICONS = {OK: "dialog-ok-apply", INFO: "dialog-information", WARNING: "dialog-warning", ERROR: "dialog-error"}


def check_on_start() -> bool:
    return QSettings().value(CHECK_ON_START_KEY, True, type=bool)


def _is_command(line: str) -> bool:
    """Commands are shown copyable; instructions ("Turn on … in the menu.") as text."""
    return not line.rstrip().endswith(".")


class SetupCheckDialog(QDialog):
    """`rerun(on_done)` runs the checks again (in the background) and calls `on_done(checks)`."""

    def __init__(self, checks: list[Check], rerun: Callable[[Callable[[list[Check]], None]], None] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(translate("SetupCheck", "Check Setup"))
        self.resize(640, 520)
        self._rerun = rerun
        lay = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.Shape.NoFrame)
        lay.addWidget(self.area, 1)
        self.on_start = QCheckBox(translate("SetupCheck", "Check at start and show problems"))
        self.on_start.setChecked(check_on_start())
        self.on_start.toggled.connect(lambda on: QSettings().setValue(CHECK_ON_START_KEY, on))
        lay.addWidget(self.on_start)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self.btn_again = QPushButton(QIcon.fromTheme("view-refresh"), translate("SetupCheck", "Check Again"))
        self.btn_again.setEnabled(rerun is not None)
        self.btn_again.clicked.connect(self._again)
        buttons.addButton(self.btn_again, QDialogButtonBox.ButtonRole.ActionRole)
        lay.addWidget(buttons)
        self.set_checks(checks)

    def set_checks(self, checks: list[Check]) -> None:
        self.checks = checks
        errors = sum(c.status == ERROR for c in checks)
        warnings = sum(c.status == WARNING for c in checks)
        if errors:
            text = translate("SetupCheck", "Some things KelvinCal needs are missing or not accessible. The "
                             "commands below fix them; run them in a terminal.")
        elif warnings:
            text = translate("SetupCheck", "KelvinCal works, but not every feature is available.")
        else:
            text = translate("SetupCheck", "Everything KelvinCal needs is in place.")
        self.summary.setText(text)

        body = QWidget()
        blocks = QVBoxLayout(body)
        blocks.setSpacing(12)
        size = self.style().pixelMetric(self.style().PixelMetric.PM_SmallIconSize)
        # problems first, in the order error, warning, info; then what is fine (compact)
        order = {ERROR: 0, WARNING: 1, INFO: 2, OK: 3}
        ok_list: QVBoxLayout | None = None
        for c in sorted(checks, key=lambda c: order[c.status]):
            block = QGridLayout()
            block.setColumnStretch(1, 1)
            block.setVerticalSpacing(4)
            icon = QLabel()
            icon.setPixmap(QIcon.fromTheme(_ICONS[c.status]).pixmap(size, size))
            icon.setAlignment(Qt.AlignmentFlag.AlignTop)
            block.addWidget(icon, 0, 0)
            title = QLabel(c.title)
            title.setWordWrap(True)
            block.addWidget(title, 0, 1)
            if c.status == OK:
                if ok_list is None:
                    ok_list = QVBoxLayout()
                    ok_list.setSpacing(2)
                    blocks.addLayout(ok_list)
                ok_list.addLayout(block)
                continue
            font = title.font()
            font.setBold(True)
            title.setFont(font)
            row = 1
            if c.detail:
                detail = SecondaryLabel(c.detail)
                detail.setWordWrap(True)
                block.addWidget(detail, row, 1)
                row += 1
            if c.fix:
                block.addWidget(self._fix_widget(c.fix), row, 1)
            blocks.addLayout(block)
        blocks.addStretch(1)
        self.area.setWidget(body)

    def _fix_widget(self, fix: str) -> QWidget:
        if not all(_is_command(line) for line in fix.splitlines()):
            label = QLabel(fix)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return label
        box = QWidget()
        lay = QGridLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        # a label grows with the (wrapped) command, unlike a fixed-height text field; copy takes the original
        edit = QLabel(fix)
        edit.setTextFormat(Qt.TextFormat.PlainText)
        edit.setWordWrap(True)
        edit.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        edit.setFrameShape(QFrame.Shape.StyledPanel)
        edit.setBackgroundRole(QPalette.ColorRole.Base)
        edit.setAutoFillBackground(True)
        edit.setMargin(6)
        edit.setObjectName("command")
        lay.addWidget(edit, 0, 0)
        copy = QToolButton()
        copy.setIcon(QIcon.fromTheme("edit-copy"))
        copy.setText(translate("SetupCheck", "Copy command"))
        copy.setToolTip(copy.text())
        if not copy.icon().isNull():
            copy.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(fix))
        lay.addWidget(copy, 0, 1, Qt.AlignmentFlag.AlignTop)
        return box

    def _again(self) -> None:
        if self._rerun is None:
            return
        self.btn_again.setEnabled(False)

        def done(checks: list[Check]) -> None:
            self.btn_again.setEnabled(True)
            self.set_checks(checks)

        self._rerun(done)
