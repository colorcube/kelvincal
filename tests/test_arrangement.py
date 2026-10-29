"""Monitor arrangement view: real positions when known, card-only fallback otherwise."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kcal_core.models import DDCState, DisplayInfo  # noqa: E402
import kcal_gui.pages.monitors_simple as ms  # noqa: E402


def _display(connector: str, bus: int | None = 7) -> DisplayInfo:
    return DisplayInfo(connector=connector, drm_card_connector=f"card1-{connector}", edid_hash=connector,
                       model=f"Model {connector}", i2c_bus=bus, ddc=DDCState(40, 70, 100, 100, 100))


class ArrangementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls._orig = ms.screen_geometries

    @classmethod
    def tearDownClass(cls) -> None:
        ms.screen_geometries = cls._orig

    def test_positions_order_and_click(self) -> None:
        # DP-2 is physically left of DP-1
        ms.screen_geometries = lambda: {"DP-1": QRect(2560, 0, 2560, 1440), "DP-2": QRect(0, 0, 2560, 1440)}
        page = ms.MonitorsSimplePage()
        page.resize(1000, 800)
        page.show()
        page.set_displays([_display("DP-1"), _display("DP-2")], "DP-1")
        self.assertTrue(page.arrangement.isVisible())
        self.assertEqual(page.monitor_cards, [])           # one detail card instead of a card per display
        self.assertTrue(page.detail.isVisible())
        self.assertEqual(page.detail.connector, "DP-1")
        picked: list[str] = []
        page.display_selected.connect(picked.append)
        rect = page.arrangement._rects()["DP-2"]
        QTest.mouseClick(page.arrangement, Qt.MouseButton.LeftButton, pos=QPoint(int(rect.center().x()),
                                                                                  int(rect.center().y())))
        self.assertEqual(picked, ["DP-2"])
        page.set_selected("DP-2")
        self.assertEqual(page.detail.connector, "DP-2")
        self.assertFalse(page.arrangement.grab().isNull())
        page.close()

    def test_fallback_without_positions(self) -> None:
        ms.screen_geometries = lambda: {}
        page = ms.MonitorsSimplePage()
        page.show()
        page.set_displays([_display("DP-1"), _display("HDMI-A-1", None)], "DP-1")
        self.assertFalse(page.arrangement.isVisible())
        self.assertFalse(page.detail.isVisible())
        self.assertEqual(len(page.monitor_cards), 2)
        page.close()

    def test_expert_page_uses_arrangement(self) -> None:
        from kcal_gui.pages.monitors_expert import MonitorsExpertPage

        ms.screen_geometries = lambda: {"DP-1": QRect(0, 0, 2560, 1440)}
        page = MonitorsExpertPage()
        page.show()
        page.set_displays([_display("DP-1")], "DP-1")
        self.assertTrue(page.arrangement.isVisible())
        self.assertFalse(page.output_list.isVisible())
        self.assertTrue(page.phase_buttons[1].isEnabled())
        ms.screen_geometries = lambda: {}
        page.set_displays([_display("DP-1")], "DP-1")
        self.assertFalse(page.arrangement.isVisible())
        self.assertTrue(page.output_list.isVisible())
        page.close()


if __name__ == "__main__":
    unittest.main()
