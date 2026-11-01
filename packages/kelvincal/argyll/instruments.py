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
# Colorimeters that can be calibrated with spectral samples (.ccss); older ones (DTP94, Spyder 2/3,
# i1 Display 1/2, HCFR, ...) only take a correction matrix (.ccmx) made for the pair display/instrument.
_CCSS_RE = re.compile(r"i1 ?display ?pro|colormunki display|i1 ?d3|spyder ?(4|5|x)|\bk-?10", re.IGNORECASE)
# -y list of `spotread -?`: "    e                  i1D3: LCD White LED IPS (WLED AC LG Samsung)"
_DISPLAY_TYPE_RE = re.compile(r"^\s*(?:-y\s+)?(?P<keys>[A-Za-z0-9](?:\|[A-Za-z0-9])*)\s+"
                              r"(?P<family>[^:\s][^:]*):\s*(?P<label>.+?)\s*$")


@dataclass(frozen=True)
class DisplayType:
    """One `-y` entry of the connected colorimeter: a built-in mode, or a correction file installed into
    ArgyllCMS (`oeminst`, `ccxxmake -a`), which spotread offers as a mode as well."""

    key: str          # the -y letter/number
    family: str       # instrument family as spotread names it, e.g. "i1D3"
    description: str  # full spotread text, e.g. "LCD White LED IPS (WLED AC LG Samsung)"

    @property
    def is_default(self) -> bool:
        """The instrument's own default (spotread marks it "[Default,CB1]")."""
        return "[default" in self.description.lower()

    @property
    def label(self) -> str:
        """Short name without the bracketed tags: "Non-Refresh display", "LCD White LED IPS"."""
        text = re.sub(r"\s*\[[^]]*\]", "", self.description)
        return text.split(" (", 1)[0].strip() or text


@dataclass
class InstrumentStatus:
    argyll_version: str = ""          # "" if ArgyllCMS is not installed
    instruments: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)      # spotread/dispread -c number of each instrument
    display_types: list[DisplayType] = field(default_factory=list)  # -y modes (empty: none / no colorimeter)

    def spectrometers(self) -> list[tuple[int, str]]:
        """(port number, name) of the connected spectrometers."""
        return [(port, name) for port, name in zip(self.ports, self.instruments) if is_spectrometer(name)]

    @property
    def primary(self) -> str:
        """The instrument KelvinCal measures with (spotread/dispread default port 1), "" if none."""
        return self.instruments[0] if self.instruments else ""

    def display_type(self, key: str) -> DisplayType | None:
        return next((t for t in self.display_types if t.key == key), None)


def is_spectrometer(name: str) -> bool:
    return bool(_SPECTRO_RE.search(name))


def display_type_text(key: str, label: str = "") -> str:
    """"LCD White LED IPS (-y e)" for reports and notes; "" if no mode was passed."""
    if not key:
        return ""
    return f"{label} (-y {key})" if label else f"-y {key}"


def correction_kinds(name: str) -> tuple[str, ...]:
    """Correction file types instrument `name` can use: spectrometers measure spectra themselves (none),
    newer colorimeters take .ccss and .ccmx, older ones only .ccmx. Unknown instrument ("") → both."""
    if not name:
        return ("ccss", "ccmx")
    if is_spectrometer(name):
        return ()
    return ("ccss", "ccmx") if _CCSS_RE.search(name) else ("ccmx",)


def parse_display_types(text: str) -> list[DisplayType]:
    """The `-y` block of `spotread -?` (only connected instruments are listed there)."""
    result: list[DisplayType] = []
    in_block = False
    for line in text.splitlines():
        if re.match(r"^\s*-y\s", line):
            in_block = True
        elif in_block and re.match(r"^\s*-[A-Za-z]", line):
            break
        if not in_block:
            continue
        m = _DISPLAY_TYPE_RE.match(line)
        if m:
            key = m.group("keys").split("|")[0]
            result.append(DisplayType(key, m.group("family").strip(), m.group("label")))
    return result


def parse_spotread_usage(text: str) -> InstrumentStatus:
    """Parses `spotread -?` output: version line and the `-c listno` port list."""
    version = _VERSION_RE.search(text)
    matches = list(_PORT_RE.finditer(text))
    names = [m.group("name").split(",")[0].strip() for m in matches]
    return InstrumentStatus(argyll_version=version.group(1) if version else "", instruments=names,
                            ports=[int(m.group("index")) for m in matches],
                            display_types=parse_display_types(text))


def detect_instruments(timeout_s: float = 10.0) -> InstrumentStatus:
    if not shutil.which("spotread"):
        return InstrumentStatus()
    try:
        proc = subprocess.run(["spotread", "-?"], capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        # spotread hangs while enumerating USB (instrument stuck, no /dev/bus/usb): ArgyllCMS is installed
        # all the same, its version line came first
        partial = b"".join(o if isinstance(o, bytes) else (o or "").encode() for o in (exc.stdout, exc.stderr))
        return parse_spotread_usage(partial.decode(errors="replace"))
    except OSError:
        return InstrumentStatus()
    return parse_spotread_usage(proc.stdout + proc.stderr)
