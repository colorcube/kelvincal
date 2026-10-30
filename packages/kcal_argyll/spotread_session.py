"""Persistent PTY session for ArgyllCMS `spotread` enabling low-latency single-patch measurements."""

from __future__ import annotations

from contextlib import AbstractContextManager
import os
import pty
import re
import select
import shutil
import signal
import subprocess
import time
from typing import Callable

from kcal_core.i18n import translate
from kcal_core.models import ColorMeasurement


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
        display_type: str = "l",
        ccss_path: str | None = None,
        non_adaptive: bool = False,
        settle_before_measure_s: float = 0.15,
    ) -> None:
        self.display_type = display_type
        self.ccss_path = ccss_path
        self.non_adaptive = non_adaptive
        self.settle_before_measure_s = settle_before_measure_s
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
        cmd = [spotread_bin, "-e", "-y", self.display_type]
        if self.non_adaptive:
            cmd.extend(["-Y", "A"])
        if self.ccss_path:
            cmd.extend(["-X", self.ccss_path])

        self._proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        self._master_fd = master_fd

        # Wait for the complete prompt "take a reading: " and allow 100 ms for tcsetattr()
        self._read_until(
            pattern=r"take a reading:\s*$",
            timeout_s=timeout_s,
        )
        time.sleep(0.10)

    def _read_until(self, pattern: str, timeout_s: float) -> str:
        assert self._master_fd is not None
        buf = ""
        deadline = time.monotonic() + timeout_s
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)

        while time.monotonic() < deadline:
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
            raise RuntimeError(translate("Errors", "Could not read a measurement from spotread (is the sensor connected?). "
                                         "Output:\n{output}").format(output=out))

        return ColorMeasurement(rgb=rgb, X=xyz[0], Y=xyz[1], Z=xyz[2])

    def close(self) -> None:
        """Cleanly terminates `spotread` by sending 'q' to the PTY."""
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
                self._proc.send_signal(signal.SIGTERM)
            self._proc = None
