"""Monitor arrangement view in the manner of the KDE display settings: outputs at their real positions."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from kcal_gui.theme import status_colors
from kcal_gui.widgets.basic import mix, mono_font


@dataclass
class ArrangedDisplay:
    connector: str
    title: str          # e.g. model name
    detail: str         # e.g. "2560 × 1440"
    geometry: QRect     # logical desktop geometry
    warning: bool = False  # e.g. drift against the active preset
    enabled: bool = True   # False: shown dimmed (e.g. no DDC/CI)


class DisplayArrangement(QWidget):
    """Scaled outlines of all outputs at their desktop positions; click selects (signal `selected`)."""

    selected = Signal(str)

    PADDING = 6.0
    GAP = 4.0  # visual gap between adjacent outputs

    def __init__(self, parent: QWidget | None = None, hint: QSize | None = None) -> None:
        super().__init__(parent)
        self._hint = hint or QSize(600, 120)
        self.items: list[ArrangedDisplay] = []
        self.current = ""
        self._hover = ""
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self._hint

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(120, self.minimumHeight())

    def set_items(self, items: list[ArrangedDisplay], current: str) -> None:
        self.items = items
        self.current = current
        self.update()

    def set_current(self, connector: str) -> None:
        self.current = connector
        self.update()

    # ------------------------------------------------------------------ geometry

    def _rects(self) -> dict[str, QRectF]:
        if not self.items:
            return {}
        bounds = QRect(self.items[0].geometry)
        for it in self.items[1:]:
            bounds = bounds.united(it.geometry)
        avail = QRectF(self.rect()).adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING)
        if bounds.width() <= 0 or bounds.height() <= 0:
            return {}
        s = min(avail.width() / bounds.width(), avail.height() / bounds.height())
        ox = avail.left() + (avail.width() - bounds.width() * s) / 2
        oy = avail.top() + (avail.height() - bounds.height() * s) / 2
        out = {}
        for it in self.items:
            g = it.geometry
            r = QRectF(ox + (g.x() - bounds.x()) * s, oy + (g.y() - bounds.y()) * s, g.width() * s, g.height() * s)
            out[it.connector] = r.adjusted(self.GAP / 2, self.GAP / 2, -self.GAP / 2, -self.GAP / 2)
        return out

    def _at(self, pos: QPointF) -> str:
        return next((c for c, r in self._rects().items() if r.contains(pos)), "")

    # ------------------------------------------------------------------ events

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        hover = self._at(event.position())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover else Qt.CursorShape.ArrowCursor)
            item = next((it for it in self.items if it.connector == hover), None)
            self.setToolTip(f"{item.connector} · {item.title} · {item.detail}" if item else "")
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: ANN001, N802
        self._hover = ""
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        hit = self._at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and hit:
            self.selected.emit(hit)

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802
        order = [it.connector for it in sorted(self.items, key=lambda i: (i.geometry.x(), i.geometry.y()))]
        if order and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            idx = order.index(self.current) if self.current in order else 0
            idx = max(0, min(len(order) - 1, idx + (1 if event.key() == Qt.Key.Key_Right else -1)))
            self.selected.emit(order[idx])
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ painting

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        pal = self.palette()
        window = pal.color(QPalette.ColorRole.Window)
        text = pal.color(QPalette.ColorRole.WindowText)
        base = pal.color(QPalette.ColorRole.Base)
        highlight = pal.color(QPalette.ColorRole.Highlight)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rects = self._rects()
        bold = QFont(self.font())
        bold.setBold(True)
        small = mono_font(-1)
        for it in self.items:
            r = rects.get(it.connector)
            if r is None:
                continue
            selected = it.connector == self.current
            hover = it.connector == self._hover
            fill = mix(base, highlight, 0.18) if selected else base
            border = highlight if selected else mix(highlight, mix(window, text, 0.3), 0.5 if hover else 1.0)
            p.setPen(QPen(border, 2.0 if selected else 1.0))
            p.setBrush(fill)
            p.drawRoundedRect(r, 4, 4)
            p.setOpacity(1.0 if it.enabled else 0.55)
            inner = r.adjusted(8, 6, -8, -6)
            lines = [(it.connector, bold, text), (it.title, self.font(), text),
                     (it.detail, small, pal.color(QPalette.ColorRole.PlaceholderText))]
            heights = [_line_height(p, f) for _t, f, _c in lines]
            while len(lines) > 1 and sum(heights) > inner.height():  # small outline: drop detail lines
                lines.pop()
                heights.pop()
            y = max(inner.top(), inner.center().y() - sum(heights) / 2)
            for (txt, font, color), h in zip(lines, heights):
                p.setFont(font)
                p.setPen(color)
                width = max(4, int(r.width() - 6))
                p.drawText(QRectF(r.left() + 3, y, r.width() - 6, h), Qt.AlignmentFlag.AlignCenter,
                           p.fontMetrics().elidedText(txt, Qt.TextElideMode.ElideRight, width))
                y += h
            p.setOpacity(1.0)
            if it.warning:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(status_colors(pal).warning)
                p.drawEllipse(QPointF(r.right() - 9, r.top() + 9), 4, 4)
        if self.hasFocus() and self.current in rects:
            p.setPen(QPen(highlight, 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rects[self.current].adjusted(-3, -3, 3, 3), 6, 6)


def _line_height(p: QPainter, font: QFont) -> float:
    p.setFont(font)
    return float(p.fontMetrics().height())
