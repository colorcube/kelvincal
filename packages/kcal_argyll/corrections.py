"""Colorimeter spectral corrections (.ccss) and correction matrices (.ccmx) for ArgyllCMS.

Both are CGATS text files; only the header keywords are read here (DESCRIPTOR, TECHNOLOGY, DISPLAY,
INSTRUMENT, ...). Files are looked up where ArgyllCMS itself looks for installed corrections
(`oeminst` installs into $XDG_DATA_HOME/ArgyllCMS) and are imported into the same directory.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil

from kcal_core.i18n import QT_TRANSLATE_NOOP, translate

SUFFIXES = (".ccss", ".ccmx")

# Panel technologies offered in the GUI: key, label, regular expression on TECHNOLOGY/DESCRIPTOR.
# Order matters: the first matching technology wins (wide-gamut phosphor before plain white LED).
TECHNOLOGIES: tuple[tuple[str, str, str], ...] = (
    ("wled", QT_TRANSLATE_NOOP("Corrections", "Standard white LED (W-LED)"), r"white\s*led|\bwled\b"),
    ("pfs", QT_TRANSLATE_NOOP("Corrections", "Wide-gamut LED / PFS (KSF) phosphor"), r"pfs|ksf|phosphor"),
    ("gbr", QT_TRANSLATE_NOOP("Corrections", "GB-r-LED"), r"gb-?r"),
    ("rgbled", QT_TRANSLATE_NOOP("Corrections", "RGB LED"), r"rgb\s*led"),
    ("qd", QT_TRANSLATE_NOOP("Corrections", "Quantum dot (QD)"), r"quantum|\bqd\b"),
    ("oled", QT_TRANSLATE_NOOP("Corrections", "OLED"), r"oled"),
    ("ccfl", QT_TRANSLATE_NOOP("Corrections", "CCFL"), r"ccfl"),
)
_TECH_ORDER = ("pfs", "gbr", "qd", "oled", "rgbled", "ccfl", "wled")


@dataclass(frozen=True)
class Correction:
    path: Path
    kind: str                # "ccss" or "ccmx"
    description: str         # DESCRIPTOR (or file name)
    technology: str = ""     # TECHNOLOGY keyword
    display: str = ""        # DISPLAY keyword (model the correction was made for)
    instrument: str = ""     # INSTRUMENT keyword (.ccmx only: the colorimeter it belongs to)

    @property
    def technology_key(self) -> str:
        return technology_key(f"{self.technology} {self.description}")

    @property
    def label(self) -> str:
        return f"{self.description} ({self.path.name})" if self.description != self.path.stem else self.path.name


def technology_key(text: str) -> str:
    """Maps a free-text TECHNOLOGY/DESCRIPTOR to one of `TECHNOLOGIES` (or "")."""
    patterns = {key: pattern for key, _label, pattern in TECHNOLOGIES}
    lowered = text.lower()
    return next((key for key in _TECH_ORDER if re.search(patterns[key], lowered)), "")


_KEYWORD = re.compile(r'^([A-Z_][A-Z0-9_]*)\s+"(.*)"\s*$')


def read_correction(path: str | Path) -> Correction:
    """Reads the CGATS header of a .ccss/.ccmx file. Raises ValueError if it is not one."""
    p = Path(path)
    keywords: dict[str, str] = {}
    first = ""
    with open(p, encoding="latin-1", errors="replace") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if i == 0:
                first = line.split()[0].upper() if line else ""
            if line.startswith("BEGIN_DATA"):
                break
            m = _KEYWORD.match(line)
            if m:
                keywords[m.group(1)] = m.group(2).strip()
    kind = first.lower()
    if kind not in ("ccss", "ccmx"):
        raise ValueError(translate("Errors", "{name} is not a .ccss/.ccmx file (starts with '{start}').").format(
            name=p.name, start=first))
    return Correction(
        path=p,
        kind=kind,
        description=keywords.get("DESCRIPTOR") or p.stem,
        technology=keywords.get("TECHNOLOGY", ""),
        display=keywords.get("DISPLAY", ""),
        instrument=keywords.get("INSTRUMENT", ""),
    )


def user_corrections_dir() -> Path:
    """Where ArgyllCMS `oeminst` installs corrections for the user; KelvinCal imports there as well."""
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "ArgyllCMS"


def correction_dirs() -> list[Path]:
    dirs = [user_corrections_dir()]
    for base in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if base:
            dirs.append(Path(base) / "ArgyllCMS")
            dirs.append(Path(base) / "color" / "argyll")
    out: list[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def find_corrections(dirs: list[Path] | None = None) -> list[Correction]:
    """All readable .ccss/.ccmx files (recursively) in the ArgyllCMS directories, sorted by description."""
    found: dict[str, Correction] = {}
    for d in dirs if dirs is not None else correction_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.suffix.lower() in SUFFIXES and f.is_file() and f.name not in found:
                try:
                    found[f.name] = read_correction(f)
                except (OSError, ValueError):
                    continue
    return sorted(found.values(), key=lambda c: c.description.lower())


def import_correction(source: str | Path, target_dir: Path | None = None) -> Correction:
    """Validates `source` and copies it into the user's ArgyllCMS directory; returns the installed copy."""
    corr = read_correction(source)  # raises ValueError for anything else
    target = (target_dir or user_corrections_dir())
    target.mkdir(parents=True, exist_ok=True)
    dest = target / Path(source).name
    if Path(source).resolve() != dest.resolve():
        shutil.copy2(source, dest)
    return read_correction(dest) if dest.exists() else corr
