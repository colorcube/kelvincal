"""Widgets of the running-calibration page: phase stepper, contrast search view, patch swatches, DDC bars."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from kelvincal.gui.theme import status_colors
from kelvincal.gui.widgets.basic import SecondaryLabel, mix, mono_font, title_font

STATE_PENDING, STATE_RUNNING, STATE_DONE, STATE_FAILED, STATE_SKIPPED = range(5)


class _StepBar(QWidget):
    """3 px line above a phase: full when done, partial while running, dim when pending."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = STATE_PENDING
        self.fraction: float | None = None
        self.setFixedHeight(3)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        pal = self.palette()
        window, text = pal.color(QPalette.ColorRole.Window), pal.color(QPalette.ColorRole.WindowText)
        p = QPainter(self)
        p.fillRect(self.rect(), mix(window, text, 0.15))
        if self.state == STATE_DONE:
            p.fillRect(self.rect(), mix(window, text, 0.6))
        elif self.state == STATE_FAILED:
            p.fillRect(self.rect(), status_colors(pal).error)
        elif self.state == STATE_RUNNING:
            frac = 1.0 if self.fraction is None else max(0.0, min(1.0, self.fraction))
            color = text if self.fraction is not None else pal.color(QPalette.ColorRole.Highlight)
            p.fillRect(QRectF(0, 0, self.width() * frac, self.height()), color)


class PhaseStepper(QWidget):
    """Horizontal phase overview (mockup 1d): progress line, title with state mark, detail text."""

    def __init__(self, phases: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        self.states: dict[str, int] = {}
        self.rows: dict[str, tuple[_StepBar, QLabel, QLabel, SecondaryLabel]] = {}
        for col, (key, title) in enumerate(phases):
            bar = _StepBar()
            head = QHBoxLayout()
            name = QLabel(f"{key} {title}")
            name.setFont(title_font(self, 1.0))
            mark = QLabel()
            mark.setFont(mono_font())
            head.addWidget(name, 1)
            head.addWidget(mark)
            detail = SecondaryLabel(mono=True)
            grid.addWidget(bar, 0, col)
            grid.addLayout(head, 1, col)
            grid.addWidget(detail, 2, col)
            grid.setColumnStretch(col, 1)
            self.rows[key] = (bar, name, mark, detail)
            self.states[key] = STATE_PENDING
        self.reset()

    def reset(self) -> None:
        for key in self.rows:
            self.rows[key][0].fraction = None
            self.set_state(key, STATE_PENDING, "")

    def state(self, key: str) -> int:
        return self.states.get(key, STATE_PENDING)

    def set_state(self, key: str, state: int, detail: str | None = None) -> None:
        if key not in self.rows:
            return
        bar, name, mark, det = self.rows[key]
        self.states[key] = state
        bar.state = state
        bar.update()
        sc = status_colors(self.palette())
        pal = name.palette()
        role = QPalette.ColorRole.WindowText if state in (STATE_RUNNING, STATE_DONE, STATE_FAILED) \
            else QPalette.ColorRole.PlaceholderText
        name.setForegroundRole(role)
        if state == STATE_DONE:
            mark.setText("✓")
            pal.setColor(QPalette.ColorRole.WindowText, sc.ok)
            mark.setPalette(pal)
        elif state == STATE_FAILED:
            mark.setText("✗")
            pal.setColor(QPalette.ColorRole.WindowText, sc.error)
            mark.setPalette(pal)
        elif state == STATE_RUNNING and bar.fraction is not None:
            mark.setText(f"{round(bar.fraction * 100)} %")
            mark.setPalette(self.palette())
        else:
            mark.setText("")
        if detail is not None:
            det.setText(detail)

    def set_progress(self, key: str, current: int, total: int) -> None:
        if key not in self.rows:
            return
        self.rows[key][0].fraction = current / max(1, total)
        self.set_state(key, STATE_RUNNING)


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
    """Most recently measured patch colours over the full width, newest at the right (outlined)."""

    def __init__(self, capacity: int = 10, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capacity = capacity
        self.colors: list[QColor] = []
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.capacity * 30, 26)

    def clear(self) -> None:
        self.colors.clear()
        self.update()

    def push(self, rgb: tuple[int, int, int]) -> None:
        self.colors.append(QColor(*rgb))
        del self.colors[:-self.capacity]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        p = QPainter(self)
        gap = 4.0
        w = (self.width() - 4 - gap * (self.capacity - 1)) / self.capacity
        offset = self.capacity - len(self.colors)  # fill from the right
        fg = self.palette().color(QPalette.ColorRole.WindowText)
        for i, c in enumerate(self.colors):
            rect = QRectF(2 + (offset + i) * (w + gap), 2, w, self.height() - 4)
            p.fillRect(rect, c)
            if i == len(self.colors) - 1:
                p.setPen(QPen(fg, 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect.adjusted(-1.5, -1.5, 1.5, 1.5))


class PatchSwatch(QWidget):
    """The patch currently on screen, as a large square-cornered field."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color: QColor | None = None
        self.setFixedSize(132, 132)

    def set_rgb(self, rgb: tuple[int, int, int] | None) -> None:
        self.color = QColor(*rgb) if rgb else None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        pal = self.palette()
        p = QPainter(self)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(mix(pal.color(QPalette.ColorRole.Window), pal.color(QPalette.ColorRole.WindowText), 0.25), 1))
        p.setBrush(self.color if self.color is not None else Qt.BrushStyle.NoBrush)
        p.drawRect(rect)


class ThinBar(QWidget):
    """Flat 0–100 bar in a given channel colour (thin, like the mockup's DDC meters)."""

    def __init__(self, channel: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.channel = channel  # "red" | "green" | "blue" | "" (neutral)
        self.value: float | None = None
        self.setFixedHeight(8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setValue(self, value: float | None) -> None:  # noqa: N802
        self.value = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Window)
        text = pal.color(QPalette.ColorRole.WindowText)
        track = mix(base, text, 0.12)
        fill = getattr(status_colors(pal), self.channel, None) if self.channel else None
        if fill is None:
            fill = mix(base, text, 0.55)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(0, (self.height() - 4) / 2, self.width(), 4)
        p.setBrush(track)
        p.drawRoundedRect(rect, 2, 2)
        if self.value is not None:
            p.setBrush(fill)
            p.drawRoundedRect(QRectF(rect.left(), rect.top(), rect.width() * max(0.0, min(100.0, self.value)) / 100,
                                     rect.height()), 2, 2)


class DdcBars(QWidget):
    """Read-only bars for the DDC values brightness, contrast and R/G/B gain."""

    ROWS = (("0x10", "brightness", ""), ("0x12", "contrast", ""), ("0x16", "red_gain", "red"),
            ("0x18", "green_gain", "green"), ("0x1A", "blue_gain", "blue"))

    def __init__(self, labels: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setVerticalSpacing(6)
        grid.setHorizontalSpacing(8)
        self.bars: dict[str, tuple[ThinBar, QLabel]] = {}
        for row, (vcp, attr, channel) in enumerate(self.ROWS):
            code = SecondaryLabel(vcp, mono=True)
            name = SecondaryLabel(labels.get(attr, attr))
            bar = ThinBar(channel)
            value = QLabel("–")
            value.setFont(mono_font())
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setMinimumWidth(value.fontMetrics().horizontalAdvance("100") + 2)
            grid.addWidget(code, row, 0)
            grid.addWidget(name, row, 1)
            grid.addWidget(bar, row, 2)
            grid.addWidget(value, row, 3)
            self.bars[attr] = (bar, value)
        grid.setColumnStretch(2, 1)

    def set_values(self, ddc) -> None:  # noqa: ANN001 - kelvincal.core.models.DDCState or None
        for attr, (bar, label) in self.bars.items():
            v = getattr(ddc, attr, None) if ddc is not None else None
            bar.setValue(v)
            label.setText(str(v) if v is not None else "–")
