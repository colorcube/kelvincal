"""Small building blocks styled only through the application palette (no style sheets)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kcal_gui.theme import status_colors


def mono_font(point_delta: float = 0.0) -> QFont:
    """System fixed-width font for measured values."""
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if point_delta:
        font.setPointSizeF(font.pointSizeF() + point_delta)
    return font


def title_font(widget: QWidget, scale: float = 1.5, bold: bool = True) -> QFont:
    font = QFont(widget.font())
    font.setPointSizeF(font.pointSizeF() * scale)
    font.setBold(bold)
    return font


def mix(a: QColor, b: QColor, amount: float) -> QColor:
    t = max(0.0, min(1.0, amount))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
    )


class SecondaryLabel(QLabel):
    """Label in the inactive (secondary) text colour, optionally monospaced."""

    def __init__(self, text: str = "", mono: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        if mono:
            self.setFont(mono_font())
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)


class SectionHeader(QWidget):
    """Numbered section title like "1  Select display"."""

    def __init__(self, number: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 4)
        badge = QLabel(number)
        badge.setFont(title_font(self, 1.0))
        badge.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        label = QLabel(text)
        label.setFont(title_font(self, 1.1))
        lay.addWidget(badge)
        lay.addWidget(label, 1)


class SegmentedControl(QWidget):
    """Exclusive row of checkable tool buttons (e.g. "Simple | Expert", "D65 | D50")."""

    currentChanged = Signal(int)  # noqa: N815 - Qt naming

    def __init__(self, labels: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QToolButton] = []
        for i, text in enumerate(labels):
            btn = QToolButton()
            btn.setText(text.replace("&", "&&"))
            btn.setCheckable(True)
            btn.setAutoRaise(False)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.group.addButton(btn, i)
            self.buttons.append(btn)
            lay.addWidget(btn)
        lay.addStretch(1)
        if self.buttons:
            self.buttons[0].setChecked(True)
        self.group.idToggled.connect(lambda i, on: on and self.currentChanged.emit(i))

    def currentIndex(self) -> int:  # noqa: N802
        return self.group.checkedId()

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)


class Card(QFrame):
    """Rounded panel in the view background; optionally selectable (highlight frame when checked)."""

    clicked = Signal()

    def __init__(self, selectable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.selectable = selectable
        self._checked = False
        self._hover = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, selectable)
        self.setBackgroundRole(QPalette.ColorRole.Base)
        if selectable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(4)

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        if checked != self._checked:
            self._checked = checked
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if self.selectable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802
        if self.selectable and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: ANN001, N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001, N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        pal = self.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        border = mix(pal.color(QPalette.ColorRole.Window), pal.color(QPalette.ColorRole.WindowText), 0.2)
        width = 1.0
        if self._checked:
            border, width = pal.color(QPalette.ColorRole.Highlight), 2.0
        elif self._hover or (self.selectable and self.hasFocus()):
            border = mix(pal.color(QPalette.ColorRole.Highlight), border, 0.4)
        p.setPen(QPen(border, width))
        p.setBrush(pal.color(QPalette.ColorRole.Base))
        p.drawRoundedRect(rect.adjusted(width / 2, width / 2, -width / 2, -width / 2), 6, 6)


class StatusDot(QWidget):
    """Small coloured dot (ok / warning / error / inactive)."""

    def __init__(self, state: str = "inactive", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setFixedSize(10, 10)

    def setState(self, state: str) -> None:  # noqa: N802
        self.state = state
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        sc = status_colors(self.palette())
        color = {"ok": sc.ok, "warning": sc.warning, "error": sc.error}.get(
            self.state, self.palette().color(QPalette.ColorRole.PlaceholderText)
        )
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(1, 1, 8, 8)


class MessageBanner(QFrame):
    """Inline message in the style of KMessageWidget (information / positive / warning / error)."""

    ICONS = {
        "information": "dialog-information",
        "positive": "dialog-positive",
        "warning": "dialog-warning",
        "error": "dialog-error",
    }

    def __init__(self, text: str = "", kind: str = "information", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        self.icon = QLabel()
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.label, 1)
        self.actions_layout = QHBoxLayout()
        lay.addLayout(self.actions_layout)
        self.setKind(kind)

    def setKind(self, kind: str) -> None:  # noqa: N802
        self.kind = kind
        self.icon.setPixmap(QIcon.fromTheme(self.ICONS.get(kind, "dialog-information")).pixmap(QSize(22, 22)))
        self.update()

    def setText(self, text: str) -> None:  # noqa: N802
        self.label.setText(text)

    def addAction(self, text: str, slot) -> QPushButton:  # noqa: ANN001, N802
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        self.actions_layout.addWidget(btn)
        return btn

    def _color(self) -> QColor:
        sc = status_colors(self.palette())
        return {
            "positive": sc.ok,
            "warning": sc.warning,
            "error": sc.error,
        }.get(self.kind, self.palette().color(QPalette.ColorRole.Highlight))

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        color = self._color()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(color, 1))
        p.setBrush(mix(self.palette().color(QPalette.ColorRole.Window), color, 0.15))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)


class ClickableLabel(QAbstractButton):
    """Flat link-like button (e.g. "profile.icc ↗")."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + 4, fm.height() + 2)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        p = QPainter(self)
        color = self.palette().color(QPalette.ColorRole.Link)
        if not self.isEnabled():
            color = self.palette().color(QPalette.ColorRole.PlaceholderText)
        p.setPen(color)
        font = QFont(self.font())
        font.setUnderline(self.underMouse())
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideMiddle, self.width()))
