"""Detects connected measurement instruments and the ArgyllCMS version without opening the instrument."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import shutil
import subprocess

_PORT_RE = re.compile(r"^\s+(?P<index>\d+)\s*=\s*'(?P<port>[^'(]*?)\s*\((?P<name>[^)]*)\)'", re.MULTILINE)
_VERSION_RE = re.compile(r"Version\s+(\d+(?:\.\d+)+)")
# Spectrometers ArgyllCMS can use for emissive measurements (colorimeters: i1 Display, Spyder, DTP94, ...)
_SPECTRO_RE = re.compile(r"i1 ?pro|i1 ?studio|colormunki(?! display)|spectro|jeti|specbos|ex1", re.IGNORECASE)


@dataclass
class InstrumentStatus:
    argyll_version: str = ""          # "" if ArgyllCMS is not installed
    instruments: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)      # spotread/dispread -c number of each instrument

    def spectrometers(self) -> list[tuple[int, str]]:
        """(port number, name) of the connected spectrometers."""
        return [(port, name) for port, name in zip(self.ports, self.instruments) if is_spectrometer(name)]


def is_spectrometer(name: str) -> bool:
    return bool(_SPECTRO_RE.search(name))


def parse_spotread_usage(text: str) -> InstrumentStatus:
    """Parses `spotread -?` output: version line and the `-c listno` port list."""
    version = _VERSION_RE.search(text)
    matches = list(_PORT_RE.finditer(text))
    names = [m.group("name").split(",")[0].strip() for m in matches]
    return InstrumentStatus(argyll_version=version.group(1) if version else "", instruments=names,
                            ports=[int(m.group("index")) for m in matches])


def detect_instruments(timeout_s: float = 10.0) -> InstrumentStatus:
    if not shutil.which("spotread"):
        return InstrumentStatus()
    try:
        proc = subprocess.run(["spotread", "-?"], capture_output=True, text=True, timeout=timeout_s)
    except (OSError, subprocess.TimeoutExpired):
        return InstrumentStatus()
    return parse_spotread_usage(proc.stdout + proc.stderr)
