"""Wayland-native fullscreen patch window targeted at a specific monitor (QScreen)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QKeyEvent,
    QPainter,
    QPen,
    QRasterWindow,
    QScreen,
)

from kelvincal.core.i18n import translate

# Everything except the patch stays dark and at the edges so that stray light does not reach the sensor.
DIM_TEXT = QColor(106, 106, 106)
GUIDE = QColor(90, 90, 90)
PROGRESS = QColor(58, 58, 58)


def find_qscreen_for_connector(connector: str) -> QScreen | None:
    """Finds the matching QScreen instance by DRM connector name (e.g. 'DP-1', 'HDMI-A-2')."""
    for scr in QGuiApplication.screens():
        if scr.name() == connector:
            return scr
    return None


class WaylandPatchWindow(QRasterWindow):
    """Frameless fullscreen window for rendering calibration color patches on a target Wayland monitor.

    Must live in the GUI thread. Worker threads reach it through `kelvincal.gui.workers.QtPatchDisplay`.
    """

    confirmed = Signal()
    aborted = Signal()

    def __init__(
        self,
        connector: str,
        patch_scale: float = 0.28,
        show_crosshair: bool = False,
    ) -> None:
        super().__init__()
        self.connector = connector
        self.patch_scale = max(0.10, min(1.0, patch_scale))
        self.show_crosshair = show_crosshair
        self.current_rgb: tuple[int, int, int] = (128, 128, 128)
        self.status_text: str = ""
        self.progress: float | None = None
        self.hints: list[tuple[str, str]] = []

        self.setFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.CustomizeWindowHint
        )

        target_screen = find_qscreen_for_connector(connector)
        if target_screen is None:
            # Never fall back to another screen: measuring the wrong monitor would silently corrupt the profile.
            available = ", ".join(s.name() for s in QGuiApplication.screens()) or "-"
            raise RuntimeError(
                translate(
                    "PatchWindow",
                    "No screen found for connector {connector} (available: {available}).",
                ).format(connector=connector, available=available)
            )
        self.setScreen(target_screen)
        self.setGeometry(target_screen.geometry())

    def show_on_target_screen(self) -> None:
        """Opens the window in fullscreen mode on the bound Wayland QScreen."""
        target_screen = find_qscreen_for_connector(self.connector)
        if target_screen is not None:
            self.setScreen(target_screen)
            self.setGeometry(target_screen.geometry())
        self.showFullScreen()

    def set_patch_rgb(self, rgb: tuple[int, int, int], status_text: str | None = None,
                      progress: float | None = None) -> None:
        """Updates the displayed patch colour. The caller is responsible for the settle delay."""
        self.current_rgb = (
            max(0, min(255, int(rgb[0]))),
            max(0, min(255, int(rgb[1]))),
            max(0, min(255, int(rgb[2]))),
        )
        if status_text is not None:
            self.status_text = status_text
        self.progress = progress
        self.show_crosshair = False
        if not self.isVisible():
            self.show_on_target_screen()
        self.update()

    def show_placement(self, prompt_text: str, hints: list[tuple[str, str]] | None = None) -> None:
        """Shows the alignment crosshair; emits `confirmed` (Space/Enter) or `aborted` (Esc/close).

        The first line of `prompt_text` is the instruction, further lines are details. `hints` are
        (key, action) pairs; by default Space starts and Esc cancels.
        """
        self.show_crosshair = True
        self.status_text = prompt_text
        self.progress = None
        self.hints = hints if hints is not None else [
            (translate("PatchWindow", "Space"), translate("PatchWindow", "Start measurement")),
            (translate("PatchWindow", "Esc"), translate("PatchWindow", "Cancel")),
        ]
        self.show_on_target_screen()
        self.update()

    def patch_rect(self) -> QRect:
        w, h = self.width(), self.height()
        size = int(min(w, h) * self.patch_scale)
        return QRect((w - size) // 2, (h - size) // 2, size, size)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.show_crosshair:
                self.show_crosshair = False
                self.update()
            self.confirmed.emit()
        elif key == Qt.Key.Key_Escape:
            self.aborted.emit()
        super().keyPressEvent(event)

    def event(self, ev: QEvent) -> bool:
        if ev.type() == QEvent.Type.Close:
            self.aborted.emit()
        return super().event(ev)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Solid black surround prevents stray light contamination
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0))
        if self.show_crosshair:
            self._paint_placement(painter)
        else:
            self._paint_measurement(painter)
        painter.end()

    def _paint_placement(self, p: QPainter) -> None:
        """Before measuring (mockup 1e): outline of the patch area with crosshair, prompt, key hints."""
        rect = self.patch_rect()
        p.setPen(QPen(GUIDE, 1))
        p.drawRect(rect)
        inset = max(14, rect.width() // 9)
        cx, cy = rect.center().x(), rect.center().y()
        p.drawLine(cx, rect.top() + inset, cx, rect.bottom() - inset)
        p.drawLine(rect.left() + inset, cy, rect.right() - inset, cy)

        lines = self.status_text.split("\n")
        base = QFont(QGuiApplication.font())
        y = rect.bottom() + 28
        title = QFont(base)
        title.setPointSizeF(base.pointSizeF() * 1.4)
        p.setFont(title)
        p.setPen(QColor(200, 200, 200))
        line_h = p.fontMetrics().height()
        p.drawText(QRect(0, y, self.width(), line_h), Qt.AlignmentFlag.AlignCenter, lines[0])
        y += line_h + 6
        p.setFont(base)
        p.setPen(QColor(138, 138, 138))
        for detail in lines[1:]:
            p.drawText(QRect(0, y, self.width(), p.fontMetrics().height()), Qt.AlignmentFlag.AlignCenter, detail)
            y += p.fontMetrics().height() + 2
        self._paint_hints(p, y + 18)

    def _paint_hints(self, p: QPainter, y: int) -> None:
        """Key caps like "[Space] Start measurement   [Esc] Cancel", centred."""
        if not self.hints:
            return
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        text_font = QFont(QGuiApplication.font())
        p.setFont(mono)
        mono_fm = p.fontMetrics()
        p.setFont(text_font)
        text_fm = p.fontMetrics()
        pad, gap, group_gap = 6, 8, 28
        widths = [mono_fm.horizontalAdvance(k) + 2 * pad + gap + text_fm.horizontalAdvance(t) for k, t in self.hints]
        total = sum(widths) + group_gap * (len(widths) - 1)
        x = (self.width() - total) / 2
        cap_h = mono_fm.height() + 4
        for (key, text), width in zip(self.hints, widths):
            cap = QRectF(x, y, mono_fm.horizontalAdvance(key) + 2 * pad, cap_h)
            p.setPen(QPen(QColor(74, 74, 74), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(cap, 3, 3)
            p.setFont(mono)
            p.setPen(QColor(232, 232, 232))
            p.drawText(cap, Qt.AlignmentFlag.AlignCenter, key)
            p.setFont(text_font)
            p.setPen(QColor(166, 166, 166))
            p.drawText(QRectF(cap.right() + gap, y, text_fm.horizontalAdvance(text) + 2, cap_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            x += width + group_gap

    def _paint_measurement(self, p: QPainter) -> None:
        """While measuring (mockup 1f): the patch, a thin progress line on top, dim status in the corners."""
        r, g, b = self.current_rgb
        p.fillRect(self.patch_rect(), QColor(r, g, b))
        if self.progress is not None:
            p.fillRect(QRectF(0, 0, self.width() * max(0.0, min(1.0, self.progress)), 2), PROGRESS)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        p.setFont(font)
        p.setPen(DIM_TEXT)
        line_h = p.fontMetrics().height()
        bottom = QRect(20, self.height() - 16 - line_h, self.width() - 40, line_h)
        if self.status_text:
            p.drawText(bottom, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.status_text)
        p.drawText(bottom, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   translate("PatchWindow", "Esc Cancel"))
