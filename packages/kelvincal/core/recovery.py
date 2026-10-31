"""Recovery after a crash during a measurement.

While a measurement runs, the display is switched to uncalibrated sRGB (`CalibrationColorGuard`) and its
DDC/CI values are changed. Normally both are restored afterwards; if KelvinCal is killed or crashes, the
display stays like that. So the guard writes the state from before the measurement to a small file in
$XDG_STATE_HOME/kelvincal/recovery/ and removes it once the display is back (or the new profile has been
saved or discarded). A file whose process is gone means the measurement was interrupted: the next start
offers to restore that state.

Only enabled by the programs (`enable()` in the GUI and CLI), not when the modules are used elsewhere
(tests, scripts).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kelvincal.core.compositor.base import CompositorBackend, CompositorOutputState

_enabled = False


def enable(on: bool = True) -> None:
    global _enabled
    _enabled = on


def recovery_dir() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "kelvincal" / "recovery"


@dataclass
class Interrupted:
    """The state of one display from before an interrupted measurement."""

    connector: str
    icc_profile_path: str = ""
    color_profile_source: str = "sRGB"
    hdr_enabled: bool = False
    i2c_bus: int | None = None
    ddc: list[int] | None = None        # brightness, contrast, red, green, blue gain
    pid: int = 0
    started: str = ""                   # ISO time
    path: Path | None = field(default=None, compare=False)

    @property
    def started_at(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.started)
        except ValueError:
            return None


def _file(connector: str) -> Path:
    return recovery_dir() / f"{connector}.json"


def _write(entry: Interrupted) -> None:
    path = _file(entry.connector)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(entry)
    data.pop("path")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read(path: Path) -> Interrupted | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = Interrupted.__dataclass_fields__
        entry = Interrupted(**{k: v for k, v in data.items() if k in fields and k != "path"})
    except (OSError, ValueError, TypeError):
        return None
    entry.path = path
    return entry


def record(connector: str, state: CompositorOutputState | None) -> None:
    """Called when a measurement switches `connector` to its raw state; `state` is what it showed before.

    An existing file of an interrupted earlier run is kept: it holds the state from before *that* run,
    while the display now still shows its leftovers.
    """
    if not _enabled or state is None:
        return
    old = _read(_file(connector))
    if old is not None and not _alive(old.pid):
        return
    _write(Interrupted(connector, state.icc_profile_path, state.color_profile_source, state.hdr_enabled,
                       pid=os.getpid(), started=datetime.now().isoformat(timespec="seconds")))


def note_ddc(connector: str, i2c_bus: int, values: tuple[int, int, int, int, int]) -> None:
    """Adds the DDC/CI values from before the measurement to the running record of `connector`."""
    if not _enabled:
        return
    entry = _read(_file(connector))
    if entry is not None and entry.pid == os.getpid() and entry.ddc is None:
        entry.i2c_bus, entry.ddc = i2c_bus, list(values)
        _write(entry)


def clear(connector: str) -> None:
    """The display is back in a known state: forget the record of this process."""
    if not _enabled:
        return
    entry = _read(_file(connector))
    if entry is not None and entry.pid == os.getpid():
        entry.path.unlink(missing_ok=True)


def _alive(pid: int) -> bool:
    """True if `pid` is a running KelvinCal process (not a recycled pid of something else)."""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False
    return b"kelvincal" in cmdline


def interrupted() -> list[Interrupted]:
    """Records left behind by measurements whose process no longer runs."""
    folder = recovery_dir()
    if not _enabled or not folder.is_dir():
        return []
    found = [_read(p) for p in sorted(folder.glob("*.json"))]
    return [e for e in found if e is not None and not _alive(e.pid)]


def restore(entry: Interrupted, compositor: CompositorBackend, ddc_client=None) -> None:  # noqa: ANN001
    """Brings the display back to the recorded state and removes the record. HDR is not switched back on
    (the compositor backends can only turn it off); the caller says so if `entry.hdr_enabled`."""
    compositor.apply_output_profile(connector=entry.connector, icc_profile_path=entry.icc_profile_path,
                                    color_profile_source=entry.color_profile_source or "sRGB", brightness=None)
    if entry.ddc and entry.i2c_bus is not None and ddc_client is not None:
        b, c, r, g, bl = entry.ddc
        ddc_client.set_vcp_values(entry.i2c_bus, {"10": b, "12": c, "16": r, "18": g, "1A": bl})
    discard(entry)


def discard(entry: Interrupted) -> None:
    if entry.path is not None:
        entry.path.unlink(missing_ok=True)
