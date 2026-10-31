"""Sleep/screen-lock inhibition: never fails, even without the D-Bus services; release is idempotent."""

from __future__ import annotations

import unittest
from unittest import mock

from PySide6.QtCore import QCoreApplication

from kelvincal.gui import inhibit


class SleepInhibitorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QCoreApplication.instance() or QCoreApplication([])

    def test_missing_services_are_ignored(self) -> None:
        with mock.patch.object(inhibit, "SERVICES", (("org.kelvincal.DoesNotExist", "/x", "org.kelvincal.X"),)):
            inh = inhibit.SleepInhibitor("test")
            self.assertFalse(inh.acquire())
            self.assertFalse(inh.acquire())      # second call does not open another connection
            inh.release()
            inh.release()
            self.assertEqual(inh.active, [])

    def test_context_manager_releases(self) -> None:
        with mock.patch.object(inhibit, "SERVICES", ()):
            with inhibit.SleepInhibitor("test") as inh:
                self.assertTrue(inh._name)
            self.assertEqual(inh._name, "")


if __name__ == "__main__":
    unittest.main()
