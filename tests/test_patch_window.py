"""Offscreen rendering of the patch window states (placement 1e, measurement 1f)."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kelvincal.gui.patch_window import WaylandPatchWindow  # noqa: E402


class PatchWindowRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _render(self, win: WaylandPatchWindow) -> QImage:
        img = QImage(win.width(), win.height(), QImage.Format.Format_RGB32)
        img.fill(0)
        p = QPainter(img)
        if win.show_crosshair:
            win._paint_placement(p)
        else:
            win._paint_measurement(p)
        p.end()
        return img

    def test_placement_and_measurement(self) -> None:
        win = WaylandPatchWindow(connector=QGuiApplication.primaryScreen().name())
        win.resize(800, 450)
        win.show_crosshair = True
        win.status_text = "Place the sensor\nDP-2 · Model"
        win.hints = [("Space", "Start"), ("Esc", "Cancel")]
        img = self._render(win)
        centre = win.patch_rect().center()
        self.assertEqual(img.pixelColor(centre.x() - 30, centre.y() - 30).rgb() & 0xFFFFFF, 0)  # black inside
        win.show_crosshair = False
        win.current_rgb = (64, 128, 32)
        win.status_text = "Phase 2 · Patch 1/2"
        win.progress = 0.5
        img = self._render(win)
        self.assertEqual(img.pixelColor(centre).getRgb()[:3], (64, 128, 32))
        self.assertNotEqual(img.pixelColor(10, 0).rgb() & 0xFFFFFF, 0)    # progress line
        self.assertEqual(img.pixelColor(790, 0).rgb() & 0xFFFFFF, 0)
        win.deleteLater()


if __name__ == "__main__":
    unittest.main()
