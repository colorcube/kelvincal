"""Bookkeeping for running ArgyllCMS child processes (spotread, dispread, colprof).

Every long-running ArgyllCMS process is registered while it runs, so KelvinCal can end all of them when it
has to quit (signal, logout) or when a cancelled run does not come to an end on its own (a reading that
hangs): the waiting worker then sees the process die, raises and restores the display as usual.
"""

from __future__ import annotations

import subprocess
import threading


class PipelineCancelled(Exception):
    """Raised when a running ArgyllCMS step was cancelled through `cancel_check`."""


_lock = threading.Lock()
_running: set[subprocess.Popen] = set()


def register(proc: subprocess.Popen) -> None:
    with _lock:
        _running.add(proc)


def unregister(proc: subprocess.Popen) -> None:
    with _lock:
        _running.discard(proc)


def running() -> list[subprocess.Popen]:
    """The registered processes that have not exited yet."""
    with _lock:
        return [p for p in _running if p.poll() is None]


def terminate(proc: subprocess.Popen, timeout_s: float = 3.0) -> None:
    """Terminates an ArgyllCMS child process (SIGTERM, then SIGKILL after `timeout_s`) and reaps it."""
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    finally:
        unregister(proc)


def terminate_all(timeout_s: float = 3.0) -> int:
    """Terminates every registered process; returns how many were still running."""
    procs = running()
    for proc in procs:
        proc.terminate()
    for proc in procs:
        terminate(proc, timeout_s)
    return len(procs)
