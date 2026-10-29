"""Wayland-native fullscreen patch window targeted at a specific monitor (QScreen)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QPainter,
    QPen,
    QRasterWindow,
    QScreen,
)

from kcal_core.i18n import tr


def find_qscreen_for_connector(connector: str) -> QScreen | None:
    """Finds the matching QScreen instance by DRM connector name (e.g. 'DP-1', 'HDMI-A-2')."""
    for scr in QGuiApplication.screens():
        if scr.name() == connector:
            return scr
    return None


class WaylandPatchWindow(QRasterWindow):
    """Frameless fullscreen window for rendering calibration color patches on a target Wayland monitor.

    Must live in the GUI thread. Worker threads reach it through `kcal_gui.workers.QtPatchDisplay`.
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
                tr(
                    f"No screen found for connector {connector} (available: {available}).",
                    f"Kein Bildschirm für Anschluss {connector} gefunden (verfügbar: {available}).",
                )
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

    def set_patch_rgb(self, rgb: tuple[int, int, int], status_text: str | None = None) -> None:
        """Updates the displayed patch colour. The caller is responsible for the settle delay."""
        self.current_rgb = (
            max(0, min(255, int(rgb[0]))),
            max(0, min(255, int(rgb[1]))),
            max(0, min(255, int(rgb[2]))),
        )
        if status_text is not None:
            self.status_text = status_text
        self.show_crosshair = False
        if not self.isVisible():
            self.show_on_target_screen()
        self.update()

    def show_placement(self, prompt_text: str) -> None:
        """Shows the alignment crosshair; emits `confirmed` (Space/Enter) or `aborted` (Esc/close)."""
        self.show_crosshair = True
        self.status_text = prompt_text
        self.show_on_target_screen()
        self.update()

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
        w = self.width()
        h = self.height()

        # Solid black surround prevents stray light contamination
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0))

        box_size = int(min(w, h) * self.patch_scale)
        box_x = (w - box_size) // 2
        box_y = (h - box_size) // 2
        patch_rect = QRect(box_x, box_y, box_size, box_size)

        r, g, b = self.current_rgb
        painter.fillRect(patch_rect, QColor(r, g, b))

        if self.show_crosshair:
            pen = QPen(QColor(255, 180, 0), 3)
            painter.setPen(pen)
            painter.drawRect(patch_rect)
            cx = w // 2
            cy = h // 2
            painter.drawLine(cx - 60, cy, cx + 60, cy)
            painter.drawLine(cx, cy - 60, cx, cy + 60)

        if self.status_text:
            painter.setPen(QColor(190, 190, 190))
            font = QFont("Sans Serif", 12)
            painter.setFont(font)
            text_rect = QRect(40, h - 70, w - 80, 50)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignCenter,
                f"{self.status_text}   |   RGB({r}, {g}, {b})",
            )
        painter.end()
