"""Persistent PTY session for ArgyllCMS `spotread` enabling low-latency single-patch measurements."""

from __future__ import annotations

from contextlib import AbstractContextManager
import os
import pty
import re
import select
import shutil
import subprocess
import time
from typing import Callable

from kcal_argyll import processes
from kcal_argyll.processes import PipelineCancelled
from kcal_core.i18n import translate
from kcal_core.models import ColorMeasurement

# spotread/dispread -y: measurement mode / built-in correction of the instrument. For an i1 DisplayPro
# "e" = "LCD White LED IPS" (X-Rite WLED family). The former "l" selected the *CCFL* correction, which shifts
# WLED displays by ≈ 100 K (measured 30.10.2026, see Dokumente/kelvincal-tests/2026-10-30/korrekturen).
# A .ccss/.ccmx passed with -X replaces the built-in correction. The mode is chosen per display in the GUI
# ("" = no -y, for instruments without display types).
DEFAULT_DISPLAY_TYPE = "e"


XYZ_REGEX = re.compile(
    r"Result is XYZ:\s*([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def parse_spotread_xyz(output_chunk: str) -> tuple[float, float, float] | None:
    """Extracts the most recently measured XYZ tristimulus values from spotread output."""
    matches = list(XYZ_REGEX.finditer(output_chunk))
    if not matches:
        return None
    last = matches[-1]
    return (float(last.group(1)), float(last.group(2)), float(last.group(3)))


class SpotreadSession(AbstractContextManager["SpotreadSession"]):
    """Keeps `spotread -e -y l` open inside a pseudo-terminal (PTY).

    Advantage: The USB colorimeter (e.g. X-Rite i1 DisplayPro / ColorMunki Display) is opened
    only once on startup, reducing each subsequent reading in binary search to ~0.6–1.5 s.
    """

    def __init__(
        self,
        display_type: str = DEFAULT_DISPLAY_TYPE,
        ccss_path: str | None = None,
        non_adaptive: bool = False,
        settle_before_measure_s: float = 0.15,
        observer: str | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.display_type = display_type
        self.ccss_path = ccss_path
        self.observer = observer          # spotread -Q (only with spectral data / a .ccss), e.g. "2015_2"
        self.non_adaptive = non_adaptive
        self.settle_before_measure_s = settle_before_measure_s
        # polled while waiting for spotread: a cancelled run must not sit out a hanging reading
        self.cancel_check = cancel_check
        self._proc: subprocess.Popen[bytes] | None = None
        self._master_fd: int | None = None

    def __enter__(self) -> SpotreadSession:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def start(self, timeout_s: float = 15.0) -> None:
        """Starts `spotread -e` inside a PTY and waits until the reading prompt is ready."""
        spotread_bin = shutil.which("spotread")
        if not spotread_bin:
            raise RuntimeError(translate("Errors", "ArgyllCMS tool '{tool}' was not found in PATH.").format(tool="spotread"))

        master_fd, slave_fd = pty.openpty()
        cmd = [spotread_bin, "-e"]
        if self.display_type:
            cmd.extend(["-y", self.display_type])
        if self.non_adaptive:
            cmd.extend(["-Y", "A"])
        if self.ccss_path:
            cmd.extend(["-X", self.ccss_path])
        if self.observer:
            cmd.extend(["-Q", self.observer])

        self._proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        self._master_fd = master_fd
        processes.register(self._proc)

        # Wait for the complete prompt "take a reading: " and allow 100 ms for tcsetattr()
        try:
            out = self._read_until(pattern=r"take a reading:\s*$", timeout_s=timeout_s)
        except BaseException:
            self.close()
            raise
        # Without the prompt: fail if spotread is gone or silent. Other output (e.g. an instrument that asks
        # for its own calibration first) is left to the first reading, as before.
        if not re.search(r"take a reading:\s*$", out, re.IGNORECASE):
            try:
                self._proc.wait(timeout=0.5)   # the PTY reports EOF slightly before the exit status
            except subprocess.TimeoutExpired:
                pass
            ended = self._proc.poll() is not None
            if ended or not out.strip():
                self.close()
                message = (translate("Errors", "spotread ended before it was ready (is the sensor connected?). "
                                     "Output:\n{output}") if ended else
                           translate("Errors", "spotread did not get ready within {seconds} s (sensor not "
                                     "responding?). Output:\n{output}"))
                raise RuntimeError(message.format(output=out.strip(), seconds=f"{timeout_s:g}"))
        time.sleep(0.10)

    def _read_until(self, pattern: str, timeout_s: float) -> str:
        assert self._master_fd is not None
        buf = ""
        deadline = time.monotonic() + timeout_s
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)

        while time.monotonic() < deadline:
            if self.cancel_check is not None and self.cancel_check():
                raise PipelineCancelled()
            remaining = max(0.05, deadline - time.monotonic())
            rlist, _, _ = select.select([self._master_fd], [], [], min(0.20, remaining))
            if self._master_fd in rlist:
                try:
                    chunk = os.read(self._master_fd, 4096).decode("utf-8", errors="replace")
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                if regex.search(buf):
                    return buf
        return buf

    def measure_rgb(
        self,
        rgb: tuple[int, int, int],
        show_patch_fn: Callable[[tuple[int, int, int]], None] | None = None,
        timeout_s: float = 15.0,
    ) -> ColorMeasurement:
        """Displays `rgb` in the patch window, triggers `spotread` via Space, and returns ColorMeasurement."""
        if self._master_fd is None or self._proc is None:
            raise RuntimeError("SpotreadSession is not started.")

        if show_patch_fn is not None:
            show_patch_fn(rgb)
        if self.settle_before_measure_s > 0:
            time.sleep(self.settle_before_measure_s)

        # Drain any stale bytes in the PTY buffer
        while True:
            rlist, _, _ = select.select([self._master_fd], [], [], 0.0)
            if not rlist:
                break
            try:
                os.read(self._master_fd, 4096)
            except OSError:
                break

        # Send Space key to trigger measurement and wait for XYZ + next prompt
        os.write(self._master_fd, b" ")
        out = self._read_until(
            r"Result is XYZ:.*?take a reading:\s*$",
            timeout_s=timeout_s,
        )
        xyz = parse_spotread_xyz(out)

        if xyz is None:
            if self._proc.poll() is not None:
                raise RuntimeError(translate("Errors", "spotread ended during the measurement (sensor unplugged?). "
                                             "Output:\n{output}").format(output=out.strip()))
            raise RuntimeError(translate("Errors", "Could not read a measurement from spotread (is the sensor connected?). "
                                         "Output:\n{output}").format(output=out))

        return ColorMeasurement(rgb=rgb, X=xyz[0], Y=xyz[1], Z=xyz[2])

    def close(self) -> None:
        """Ends `spotread`: 'q' to the PTY, then SIGTERM/SIGKILL if it does not quit (hanging instrument)."""
        if self._master_fd is not None:
            try:
                os.write(self._master_fd, b"q")
            except OSError:
                pass
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        if self._proc is not None:
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
            processes.terminate(self._proc)
            self._proc = None
