"""Widgets of the running-calibration page: phase stepper, contrast search view, patch swatches, DDC bars."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QWidget,
)

from kcal_gui.theme import status_colors
from kcal_gui.widgets.basic import SecondaryLabel, mix, mono_font

STATE_PENDING, STATE_RUNNING, STATE_DONE, STATE_FAILED, STATE_SKIPPED = range(5)


class PhaseStepper(QWidget):
    """Vertical list of phases with state symbol, title, detail text and an optional progress bar."""

    SYMBOLS = {STATE_PENDING: "○", STATE_RUNNING: "●", STATE_DONE: "✓", STATE_FAILED: "✗", STATE_SKIPPED: "–"}

    def __init__(self, phases: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setColumnStretch(2, 1)
        self.rows: dict[str, tuple[QLabel, QLabel, SecondaryLabel, QProgressBar]] = {}
        for row, (key, title) in enumerate(phases):
            sym = QLabel(self.SYMBOLS[STATE_PENDING])
            sym.setFixedWidth(16)
            badge = QLabel(f"<b>{key}</b> {title}")
            detail = SecondaryLabel(mono=True)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setFixedWidth(140)
            bar.setFixedHeight(6)
            bar.hide()
            grid.addWidget(sym, row, 0)
            grid.addWidget(badge, row, 1)
            grid.addWidget(detail, row, 2)
            grid.addWidget(bar, row, 3)
            self.rows[key] = (sym, badge, detail, bar)

    def reset(self) -> None:
        for key in self.rows:
            self.set_state(key, STATE_PENDING, "")
            self.rows[key][3].hide()

    def set_state(self, key: str, state: int, detail: str | None = None) -> None:
        if key not in self.rows:
            return
        sym, _badge, det, _bar = self.rows[key]
        sym.setText(self.SYMBOLS[state])
        sc = status_colors(self.palette())
        color = {STATE_DONE: sc.ok, STATE_FAILED: sc.error, STATE_RUNNING: self.palette().color(
            QPalette.ColorRole.Highlight)}.get(state)
        sym.setStyleSheet(f"color: {color.name()}" if color else "")
        if detail is not None:
            det.setText(detail)

    def set_progress(self, key: str, current: int, total: int) -> None:
        if key not in self.rows:
            return
        bar = self.rows[key][3]
        bar.show()
        bar.setRange(0, max(1, total))
        bar.setValue(current)


@dataclass
class _Step:
    contrast: int
    clipped: bool


class ContrastSearchView(QWidget):
    """Number line of the contrast binary search: tested values (ok / clipped) and the current best."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lo, self.hi = 40, 100
        self.steps: list[_Step] = []
        self.best: int | None = None
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(320, 64)

    def reset(self, lo: int, hi: int) -> None:
        self.lo, self.hi, self.steps, self.best = lo, hi, [], None
        self.update()

    def add_step(self, contrast: int, clipped: bool) -> None:
        self.steps.append(_Step(contrast, clipped))
        if not clipped and (self.best is None or contrast > self.best):
            self.best = contrast
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        pal = self.palette()
        sc = status_colors(pal)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fg = pal.color(QPalette.ColorRole.WindowText)
        dim = mix(pal.color(QPalette.ColorRole.Window), fg, 0.35)
        x0, x1, y = 16.0, self.width() - 16.0, self.height() / 2.0

        def xpos(v: float) -> float:
            return x0 + (v - self.lo) / max(1, self.hi - self.lo) * (x1 - x0)

        p.setPen(QPen(dim, 2))
        p.drawLine(QPointF(x0, y), QPointF(x1, y))
        if self.best is not None:
            p.setPen(QPen(sc.ok, 4))
            p.drawLine(QPointF(x0, y), QPointF(xpos(self.best), y))
        p.setFont(mono_font(-1))
        p.setPen(dim)
        p.drawText(QRectF(x0 - 16, y + 8, 32, 16), Qt.AlignmentFlag.AlignCenter, str(self.lo))
        p.drawText(QRectF(x1 - 16, y + 8, 32, 16), Qt.AlignmentFlag.AlignCenter, str(self.hi))
        for i, st in enumerate(self.steps):
            color = sc.error if st.clipped else sc.ok
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            r = 5.0 if i == len(self.steps) - 1 else 3.5
            p.drawEllipse(QPointF(xpos(st.contrast), y), r, r)
        if self.best is not None:
            p.setPen(fg)
            p.drawText(QRectF(xpos(self.best) - 20, y - 26, 40, 16), Qt.AlignmentFlag.AlignCenter,
                       str(self.best))


class SwatchStrip(QWidget):
    """Row of the most recently measured patch colours (newest left)."""

    def __init__(self, capacity: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capacity = capacity
        self.colors: list[QColor] = []
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.capacity * 30, 28)

    def clear(self) -> None:
        self.colors.clear()
        self.update()

    def push(self, rgb: tuple[int, int, int]) -> None:
        self.colors.insert(0, QColor(*rgb))
        del self.colors[self.capacity:]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.height() - 2, (self.width() - 4 * self.capacity) / self.capacity)
        border = mix(self.palette().color(QPalette.ColorRole.Window),
                     self.palette().color(QPalette.ColorRole.WindowText), 0.25)
        for i, c in enumerate(self.colors):
            p.setPen(QPen(border, 1))
            p.setBrush(c)
            p.setOpacity(1.0 - i * 0.6 / self.capacity)
            p.drawRoundedRect(QRectF(1 + i * (size + 4), 1, size, size), 3, 3)


class DdcBars(QWidget):
    """Read-only bars for the DDC values brightness, contrast and R/G/B gain."""

    ROWS = (("0x10", "brightness"), ("0x12", "contrast"), ("0x16", "red_gain"),
            ("0x18", "green_gain"), ("0x1A", "blue_gain"))

    def __init__(self, labels: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setVerticalSpacing(4)
        self.bars: dict[str, tuple[QProgressBar, QLabel]] = {}
        for row, (vcp, attr) in enumerate(self.ROWS):
            code = SecondaryLabel(vcp, mono=True)
            name = QLabel(labels.get(attr, attr))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            value = QLabel("–")
            value.setFont(mono_font())
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setMinimumWidth(28)
            grid.addWidget(code, row, 0)
            grid.addWidget(name, row, 1)
            grid.addWidget(bar, row, 2)
            grid.addWidget(value, row, 3)
            self.bars[attr] = (bar, value)
        grid.setColumnStretch(2, 1)

    def set_values(self, ddc) -> None:  # noqa: ANN001 - kcal_core.models.DDCState or None
        for attr, (bar, label) in self.bars.items():
            v = getattr(ddc, attr, None) if ddc is not None else None
            bar.setValue(int(v) if v is not None else 0)
            bar.setEnabled(v is not None)
            label.setText(str(v) if v is not None else "–")
