"""Colour pad for the visual whitepoint matching: where the white has been moved, in steps from the start.

Horizontal: warmer (left, orange) ↔ cooler (right, blue); vertical: greener (top) ↔ magenta (bottom). The
tints only show the direction – they are not colour-accurate. A click moves one step towards the click.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen, QPixmap, \
    QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from kcal_ddc.visual_match import COOLER, GREENER, MAGENTA, WARMER

# Direction tints (pastel, readable with dark text in light and dark themes)
TINTS = {
    WARMER: QColor(255, 176, 96),
    COOLER: QColor(120, 170, 255),
    GREENER: QColor(120, 220, 120),
    MAGENTA: QColor(235, 120, 225),
}
_NEUTRAL = QColor(238, 238, 238)
# Position change per direction: (horizontal, vertical), vertical positive = greener (up)
MOVES = {WARMER: (-1, 0), COOLER: (1, 0), GREENER: (0, 1), MAGENTA: (0, -1)}


def _blend(a: QColor, b: QColor, t: float) -> tuple[float, float, float]:
    return (a.redF() + (b.redF() - a.redF()) * t, a.greenF() + (b.greenF() - a.greenF()) * t,
            a.blueF() + (b.blueF() - a.blueF()) * t)


def _pad_image(size: int = 64) -> QImage:
    """Neutral centre, direction tints towards the edges (horizontal and vertical tints added)."""
    img = QImage(size, size, QImage.Format.Format_RGB32)
    for py in range(size):
        v = 1.0 - 2.0 * py / (size - 1)           # +1 top (greener) … −1 bottom (magenta)
        for px in range(size):
            h = 2.0 * px / (size - 1) - 1.0       # −1 left (warmer) … +1 right (cooler)
            ch = _blend(_NEUTRAL, TINTS[COOLER] if h > 0 else TINTS[WARMER], abs(h))
            cv = _blend(_NEUTRAL, TINTS[GREENER] if v > 0 else TINTS[MAGENTA], abs(v))
            n = (_NEUTRAL.redF(), _NEUTRAL.greenF(), _NEUTRAL.blueF())
            rgb = [max(0.0, min(1.0, ch[i] + cv[i] - n[i])) for i in range(3)]
            img.setPixelColor(px, py, QColor.fromRgbF(*rgb))
    return img


def direction_icon(direction: str, size: int = 32) -> QIcon:
    """Coloured circle with an arrow pointing in `direction`."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(TINTS[direction].darker(140), 1.5))
    p.setBrush(TINTS[direction])
    p.drawEllipse(QRectF(1.5, 1.5, size - 3, size - 3))
    c, r = size / 2, size * 0.24
    dx, dy = MOVES[direction]
    dy = -dy                                       # screen y grows downwards
    tip = QPointF(c + dx * r, c + dy * r)
    base = QPointF(c - dx * r * 0.7, c - dy * r * 0.7)
    side = QPointF(-dy * r * 0.8, dx * r * 0.8)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(40, 40, 40))
    p.drawPolygon(QPolygonF([tip, base + side, base - side]))
    p.end()
    return QIcon(pm)


class WhitePad(QWidget):
    """Shows the path of the white in steps from the start; `stepRequested(direction)` on click."""

    stepRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.trail: list[tuple[int, int]] = [(0, 0)]
        self._image = _pad_image()
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(320, 320)

    def set_position(self, pos: tuple[int, int]) -> None:
        """Current position in steps (h: + cooler, v: + greener); appended to the trail."""
        if pos == (0, 0):
            self.trail = [(0, 0)]
        elif pos != self.trail[-1]:
            self.trail.append(pos)
        self.update()

    @property
    def position(self) -> tuple[int, int]:
        return self.trail[-1]

    def _square(self) -> QRectF:
        side = min(self.width(), self.height()) - 2
        return QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)

    def _range(self) -> int:
        return max(6, *(max(abs(h), abs(v)) + 1 for h, v in self.trail))

    def _to_point(self, pos: tuple[int, int], rect: QRectF) -> QPointF:
        n = self._range()
        return QPointF(rect.center().x() + pos[0] / n * rect.width() / 2,
                       rect.center().y() - pos[1] / n * rect.height() / 2)

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self._square()
        clip = QPainterPath()
        clip.addRoundedRect(rect, 10, 10)
        p.setClipPath(clip)
        p.drawImage(rect, self._image)
        # step grid
        n = self._range()
        grid = QPen(QColor(0, 0, 0, 28), 1)
        p.setPen(grid)
        for i in range(-n + 1, n):
            x = rect.center().x() + i / n * rect.width() / 2
            y = rect.center().y() + i / n * rect.height() / 2
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        p.setPen(QPen(QColor(0, 0, 0, 90), 1.2))
        p.drawLine(QPointF(rect.center().x(), rect.top()), QPointF(rect.center().x(), rect.bottom()))
        p.drawLine(QPointF(rect.left(), rect.center().y()), QPointF(rect.right(), rect.center().y()))
        # trail and current position
        pts = [self._to_point(t, rect) for t in self.trail]
        p.setPen(QPen(QColor(40, 40, 40, 150), 2, Qt.PenStyle.DashLine))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
        p.setPen(QPen(QColor(40, 40, 40), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(pts[0], 5, 5)                                  # start
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QPen(QColor(20, 20, 20), 2.5))
        p.drawEllipse(pts[-1], 8, 8)                                 # now
        p.setClipping(False)
        p.setPen(QPen(self.palette().mid().color(), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 10, 10)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.isEnabled():
            return
        rect = self._square()
        cur = self._to_point(self.position, rect)
        dx, dy = event.position().x() - cur.x(), event.position().y() - cur.y()
        if max(abs(dx), abs(dy)) < 6:
            return
        if abs(dx) >= abs(dy):
            self.stepRequested.emit(COOLER if dx > 0 else WARMER)
        else:
            self.stepRequested.emit(MAGENTA if dy > 0 else GREENER)
