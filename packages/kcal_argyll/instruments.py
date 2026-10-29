"""Detects connected measurement instruments and the ArgyllCMS version without opening the instrument."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import shutil
import subprocess

_PORT_RE = re.compile(r"^\s+\d+\s*=\s*'(?P<port>[^'(]*?)\s*\((?P<name>[^)]*)\)'", re.MULTILINE)
_VERSION_RE = re.compile(r"Version\s+(\d+(?:\.\d+)+)")


@dataclass
class InstrumentStatus:
    argyll_version: str = ""          # "" if ArgyllCMS is not installed
    instruments: list[str] = field(default_factory=list)


def parse_spotread_usage(text: str) -> InstrumentStatus:
    """Parses `spotread -?` output: version line and the `-c listno` port list."""
    version = _VERSION_RE.search(text)
    names = [m.group("name").split(",")[0].strip() for m in _PORT_RE.finditer(text)]
    return InstrumentStatus(argyll_version=version.group(1) if version else "", instruments=names)


def detect_instruments(timeout_s: float = 10.0) -> InstrumentStatus:
    if not shutil.which("spotread"):
        return InstrumentStatus()
    try:
        proc = subprocess.run(["spotread", "-?"], capture_output=True, text=True, timeout=timeout_s)
    except (OSError, subprocess.TimeoutExpired):
        return InstrumentStatus()
    return parse_spotread_usage(proc.stdout + proc.stderr)
