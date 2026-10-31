"""Cancelling and quitting: hanging or vanishing spotread, process bookkeeping, quit signals, forced quit."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from kelvincal.argyll import processes
from kelvincal.argyll.processes import PipelineCancelled
from kelvincal.argyll.spotread_session import SpotreadSession
from kelvincal.core.models import DDCState, DisplayInfo
from kelvincal.gui.app import QUIT_SIGNALS, install_quit_signals
from kelvincal.gui.controller import CancelToken

# Stand-in for spotread; FAKE_SPOTREAD selects the behaviour. Reads keys unbuffered like the real one.
FAKE_SPOTREAD = f"""#!{sys.executable}
import os, signal, sys, time, tty
mode = os.environ.get("FAKE_SPOTREAD", "ok")
if mode == "exit":
    print("Failed to find an instrument", flush=True)
    sys.exit(1)
if mode == "silent":
    time.sleep(60)
if mode == "stubborn":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
tty.setcbreak(0)
prompt = "Place instrument on spot to be measured,\\nand hit [A-Z] to read white and setup FWA compensation (keyed to letter)\\nor hit 'q' to quit, or any other key to take a reading: "
sys.stdout.write(prompt); sys.stdout.flush()
while True:
    key = os.read(0, 1)
    if key in (b"q", b""):
        sys.exit(0)
    if mode == "unplug":
        print("\\nInstrument access failed", flush=True)
        sys.exit(1)
    if mode in ("hang", "stubborn"):
        time.sleep(60)
    sys.stdout.write("\\n Result is XYZ: 95.000000 100.000000 108.000000, D50 Lab: 100 0 0\\n\\n" + prompt)
    sys.stdout.flush()
"""


class TestSpotreadSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        tool = Path(cls.tmp.name) / "spotread"
        tool.write_text(FAKE_SPOTREAD, encoding="utf-8")
        tool.chmod(0o755)
        cls._path = os.environ["PATH"]
        os.environ["PATH"] = f"{cls.tmp.name}{os.pathsep}{cls._path}"

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ["PATH"] = cls._path
        os.environ.pop("FAKE_SPOTREAD", None)
        cls.tmp.cleanup()

    def _session(self, mode: str, **kw) -> SpotreadSession:  # noqa: ANN003
        os.environ["FAKE_SPOTREAD"] = mode
        return SpotreadSession(settle_before_measure_s=0, **kw)

    def tearDown(self) -> None:
        self.assertEqual(processes.running(), [], "no ArgyllCMS process may be left behind")

    def test_reading_and_clean_close(self) -> None:
        with self._session("ok") as sensor:
            self.assertEqual(len(processes.running()), 1)
            m = sensor.measure_rgb((255, 255, 255))
        self.assertAlmostEqual(m.Y, 100.0)

    def test_missing_instrument_fails_at_start(self) -> None:
        sensor = self._session("exit")
        with self.assertRaises(RuntimeError) as ctx:
            sensor.start()
        self.assertIn("Failed to find an instrument", str(ctx.exception))

    def test_silent_spotread_times_out(self) -> None:
        sensor = self._session("silent")
        t0 = time.monotonic()
        with self.assertRaises(RuntimeError):
            sensor.start(timeout_s=1.0)
        self.assertLess(time.monotonic() - t0, 8.0)

    def test_unplugged_sensor_reports_it(self) -> None:
        with self._session("unplug") as sensor:
            with self.assertRaises(RuntimeError) as ctx:
                sensor.measure_rgb((255, 255, 255))
        self.assertIn("Instrument access failed", str(ctx.exception))

    def test_cancel_interrupts_a_hanging_reading(self) -> None:
        cancel = CancelToken()
        with self._session("hang", cancel_check=lambda: cancel.cancelled) as sensor:
            t0 = time.monotonic()
            threading.Timer(0.5, cancel.cancel).start()
            with self.assertRaises(PipelineCancelled):
                sensor.measure_rgb((255, 255, 255))
            self.assertLess(time.monotonic() - t0, 3.0)

    def test_close_kills_a_process_ignoring_sigterm(self) -> None:
        cancel = CancelToken()
        sensor = self._session("stubborn", cancel_check=lambda: cancel.cancelled)
        sensor.start()
        proc = sensor._proc
        assert proc is not None
        cancel.cancel()
        with self.assertRaises(PipelineCancelled):
            sensor.measure_rgb((255, 255, 255))
        sensor.close()
        self.assertIsNotNone(proc.poll())

    def test_terminate_all_ends_registered_processes(self) -> None:
        sensor = self._session("hang")
        sensor.start()
        proc = sensor._proc
        assert proc is not None
        self.assertEqual(processes.terminate_all(timeout_s=1.0), 1)
        self.assertIsNotNone(proc.poll())
        sensor.close()


def _spin(ms: int = 100) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class TestQuit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_signal_requests_a_clean_quit(self) -> None:
        old = {sig: signal.getsignal(sig) for sig in QUIT_SIGNALS}
        calls: list[int] = []
        notifier = install_quit_signals(lambda: calls.append(1))
        try:
            os.kill(os.getpid(), signal.SIGHUP)
            _spin()
            self.assertEqual(calls, [1])
        finally:
            signal.set_wakeup_fd(-1)
            for sig, handler in old.items():
                signal.signal(sig, handler)
            notifier.setEnabled(False)

    def test_quit_now_rejects_dialogs_and_waits_for_measurements(self) -> None:
        import kelvincal.gui.main_window as mw
        from kelvincal.argyll.instruments import InstrumentStatus

        tmp = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tmp.name)
        os.environ["KELVINCAL_PRESETS_PATH"] = os.path.join(tmp.name, "presets.json")
        orig = (mw.discover_displays, mw.detect_instruments)
        mw.discover_displays = lambda **_kw: [DisplayInfo(
            connector="DP-1", drm_card_connector="card1-DP-1", edid_hash="a", model="EIZO",
            i2c_bus=7, ddc=DDCState(38, 72, 100, 96, 91))]
        mw.detect_instruments = lambda: InstrumentStatus("3.4.1", ["X-Rite i1 DisplayPro"])
        try:
            win = mw.KelvinCalMainWindow()
            win.show()
            _spin(300)
            dialog = QDialog(win)
            dialog.show()
            side_job, cancel = object(), CancelToken()
            win._side_jobs[side_job] = cancel
            self.assertTrue(win.is_measuring())

            win.quit_now()
            _spin()
            self.assertFalse(dialog.isVisible())
            self.assertTrue(cancel.cancelled)
            self.assertTrue(win.isVisible(), "the window waits until the measurement has cleaned up")

            win._side_job_finished(side_job)
            _spin()
            self.assertFalse(win.isVisible())
        finally:
            mw.discover_displays, mw.detect_instruments = orig
            del os.environ["KELVINCAL_PRESETS_PATH"]
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
