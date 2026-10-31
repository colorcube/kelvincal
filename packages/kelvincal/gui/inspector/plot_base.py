"""Shared plot frame for the inspector: palette colours, axes, grid, crosshair and hover readout."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from kelvincal.gui.theme import status_colors
from kelvincal.gui.widgets.basic import mix, mono_font


@dataclass(frozen=True)
class PlotColors:
    background: QColor
    frame: QColor
    grid: QColor
    zero: QColor
    label: QColor
    foreground: QColor
    reference: QColor
    red: QColor
    green: QColor
    blue: QColor
    ok: QColor
    warning: QColor
    error: QColor

    def channel(self, key: str) -> QColor:
        return {"R": self.red, "G": self.green, "B": self.blue}.get(key, self.foreground)


def plot_colors(palette: QPalette) -> PlotColors:
    base = palette.color(QPalette.ColorRole.Base)
    text = palette.color(QPalette.ColorRole.Text)
    sc = status_colors(palette)
    return PlotColors(
        background=base,
        frame=mix(base, text, 0.25),
        grid=mix(base, text, 0.09),
        zero=mix(base, text, 0.3),
        label=palette.color(QPalette.ColorRole.PlaceholderText),
        foreground=text,
        reference=mix(base, text, 0.5),
        red=sc.red,
        green=sc.green,
        blue=sc.blue,
        ok=sc.ok,
        warning=sc.warning,
        error=sc.error,
    )


def with_alpha(color: QColor, alpha: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(alpha)
    return c


class PlotWidget(QWidget):
    """Base class: draws background and frame, tracks the mouse and asks subclasses for a readout text.

    Subclasses implement `paint_plot(painter, rect, colors)` and `readout_at(fx, fy)` where fx/fy are
    fractions (0..1) of the plot area, y pointing up.
    """

    readout_changed = Signal(str)

    MARGIN_LEFT = 52.0
    MARGIN_RIGHT = 16.0
    MARGIN_TOP = 14.0
    MARGIN_BOTTOM = 34.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hover: QPointF | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(480, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ------------------------------------------------------------------ geometry

    def plot_rect(self) -> QRectF:
        return QRectF(
            self.MARGIN_LEFT,
            self.MARGIN_TOP,
            max(10.0, self.width() - self.MARGIN_LEFT - self.MARGIN_RIGHT),
            max(10.0, self.height() - self.MARGIN_TOP - self.MARGIN_BOTTOM),
        )

    @staticmethod
    def map_point(rect: QRectF, fx: float, fy: float) -> QPointF:
        return QPointF(rect.left() + fx * rect.width(), rect.bottom() - fy * rect.height())

    # ------------------------------------------------------------------ mouse

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        rect = self.plot_rect()
        pos = event.position()
        if rect.contains(pos):
            self.hover = QPointF((pos.x() - rect.left()) / rect.width(), (rect.bottom() - pos.y()) / rect.height())
        else:
            self.hover = None
        self._emit_readout()
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: ANN001, N802
        self.hover = None
        self._emit_readout()
        self.update()
        super().leaveEvent(event)

    def _emit_readout(self) -> None:
        self.readout_changed.emit(self.readout_at(self.hover.x(), self.hover.y()) if self.hover else "")

    def refresh(self) -> None:
        """Repaints and re-emits the readout after a data or option change."""
        self._emit_readout()
        self.update()

    # ------------------------------------------------------------------ to implement

    def paint_plot(self, painter: QPainter, rect: QRectF, colors: PlotColors) -> None:
        raise NotImplementedError

    def readout_at(self, fx: float, fy: float) -> str:
        return ""

    def show_crosshair(self) -> bool:
        return True

    # ------------------------------------------------------------------ painting

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        colors = plot_colors(self.palette())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), colors.background)
        p.setFont(mono_font(-1.0))
        rect = self.plot_rect()
        p.save()
        self.paint_plot(p, rect, colors)
        p.restore()
        if self.hover is not None and self.show_crosshair():
            pt = self.map_point(rect, self.hover.x(), self.hover.y())
            p.setPen(QPen(with_alpha(colors.foreground, 0.5), 1))
            p.drawLine(QPointF(pt.x(), rect.top()), QPointF(pt.x(), rect.bottom()))
            p.setPen(QPen(with_alpha(colors.foreground, 0.25), 1))
            p.drawLine(QPointF(rect.left(), pt.y()), QPointF(rect.right(), pt.y()))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(colors.frame, 1))
        p.drawRect(rect)

    # ------------------------------------------------------------------ helpers for subclasses

    def draw_label(self, p: QPainter, colors: PlotColors, x: float, y: float, text: str,
                   align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter, color: QColor | None = None) -> None:
        """Draws `text` anchored at (x, y): AlignRight → right edge at x, AlignLeft → left edge at x."""
        fm = p.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 2, fm.height()
        if align & Qt.AlignmentFlag.AlignRight:
            box = QRectF(x - w, y - h / 2, w, h)
        elif align & Qt.AlignmentFlag.AlignLeft:
            box = QRectF(x, y - h / 2, w, h)
        else:
            box = QRectF(x - w / 2, y - h / 2, w, h)
        p.setPen(color or colors.label)
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    @staticmethod
    def polyline(points: list[QPointF]) -> QPainterPath:
        path = QPainterPath()
        for i, pt in enumerate(points):
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        return path
