"""Small building blocks styled only through the application palette (no style sheets)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
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
    """Label in the inactive (secondary) text colour, optionally monospaced.

    Not selectable by default: a selectable label swallows mouse presses, so clicks on it would not
    reach a surrounding clickable `Card`.
    """

    def __init__(self, text: str = "", mono: bool = False, parent: QWidget | None = None,
                 selectable: bool = False) -> None:
        super().__init__(text, parent)
        self.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        if mono:
            self.setFont(mono_font())
        if selectable:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)


class SectionHeader(QWidget):
    """Numbered section title like "1  Select display"."""

    def __init__(self, number: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 4)
        lay.setSpacing(12)
        badge = QLabel(number)
        font = mono_font()
        font.setPointSizeF(self.font().pointSizeF() * 2.2)
        font.setWeight(QFont.Weight.Medium)
        badge.setFont(font)
        badge.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        badge.setMinimumWidth(QFontMetrics(font).horizontalAdvance("0") + 4)
        label = QLabel(text)
        label.setFont(title_font(self, 1.15))
        lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(label, 1, Qt.AlignmentFlag.AlignVCenter)


class SegmentedControl(QWidget):
    """Connected row of exclusive segments (e.g. "Simple | Expert", "D65 | D50").

    Painted from the palette in the manner of a button group: one frame, thin separators,
    the current segment filled with the highlight colour.
    """

    currentChanged = Signal(int)  # noqa: N815 - Qt naming

    def __init__(self, labels: list[str], parent: QWidget | None = None, expanding: bool = False) -> None:
        super().__init__(parent)
        self.labels = list(labels)
        self._current = 0 if labels else -1
        self._hover = -1
        self._pressed = -1
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        horizontal = QSizePolicy.Policy.Expanding if expanding else QSizePolicy.Policy.Fixed
        self.setSizePolicy(horizontal, QSizePolicy.Policy.Fixed)

    # -- API compatible with the former QButtonGroup implementation
    def currentIndex(self) -> int:  # noqa: N802
        return self._current

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if 0 <= index < len(self.labels) and index != self._current:
            self._current = index
            self.update()
            self.currentChanged.emit(index)

    def count(self) -> int:
        return len(self.labels)

    # -- geometry
    def _padding(self) -> int:
        return self.fontMetrics().horizontalAdvance("M") + 4

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        widest = max((fm.horizontalAdvance(t) for t in self.labels), default=0)
        height = max(fm.height() + 12, QPushButton().sizeHint().height())
        return QSize((widest + 2 * self._padding()) * max(1, len(self.labels)) + 2, height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def _segment_rects(self) -> list[QRectF]:
        n = max(1, len(self.labels))
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        w = r.width() / n
        return [QRectF(r.left() + i * w, r.top(), w, r.height()) for i in range(len(self.labels))]

    def _index_at(self, pos) -> int:  # noqa: ANN001
        for i, rect in enumerate(self._segment_rects()):
            if rect.contains(pos):
                return i
        return -1

    # -- events
    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        idx = self._index_at(event.position())
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: ANN001, N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = self._index_at(event.position())
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001, N802
        idx = self._index_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and idx == self._pressed and idx >= 0:
            self.setCurrentIndex(idx)
        self._pressed = -1
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.setCurrentIndex(max(0, self._current - 1))
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.setCurrentIndex(min(len(self.labels) - 1, self._current + 1))
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        pal = self.palette()
        enabled = self.isEnabled()
        window = pal.color(QPalette.ColorRole.Window)
        text = pal.color(QPalette.ColorRole.ButtonText)
        button = pal.color(QPalette.ColorRole.Button)
        highlight = pal.color(QPalette.ColorRole.Highlight)
        frame = mix(button, text, 0.25)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 4.0
        p.setPen(QPen(frame, 1))
        p.setBrush(button)
        p.drawRoundedRect(outer, radius, radius)
        rects = self._segment_rects()
        for i, rect in enumerate(rects):
            checked = i == self._current
            if checked or (enabled and i in (self._hover, self._pressed)):
                if checked:
                    fill = highlight if enabled else mix(button, highlight, 0.35)
                else:
                    fill = mix(button, highlight, 0.3 if i == self._pressed else 0.15)
                path = QPainterPath()
                path.addRoundedRect(outer, radius, radius)
                clip = QPainterPath()
                clip.addRect(rect)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(fill)
                p.drawPath(path.intersected(clip))
            if i > 0 and not checked and i - 1 != self._current:
                p.setPen(QPen(frame, 1))
                p.drawLine(rect.topLeft() + QPointF(0, 5), rect.bottomLeft() - QPointF(0, 5))
            if checked and enabled:
                color = pal.color(QPalette.ColorRole.HighlightedText)
            else:
                color = text if enabled else mix(window, text, 0.45)
            p.setPen(color)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.labels[i])
        if self.hasFocus():
            p.setPen(QPen(highlight, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(outer.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


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


class ElidedLabel(QLabel):
    """Single-line label that elides instead of widening its layout (file names, models)."""

    def __init__(self, text: str = "", mono: bool = False, secondary: bool = False,
                 mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.mode = mode
        if mono:
            self.setFont(mono_font())
        if secondary:
            self.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.fontMetrics().horizontalAdvance("…") * 3, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        rect = self.contentsRect()
        p.drawText(rect, int(self.alignment()) | int(Qt.AlignmentFlag.AlignVCenter),
                   self.fontMetrics().elidedText(self.text(), self.mode, rect.width()))


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
