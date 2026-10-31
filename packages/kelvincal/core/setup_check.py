"""Setup check: is everything in place that KelvinCal needs, and if not, how to fix it.

Checks the external tools (ArgyllCMS, ddcutil, kscreen-doctor), access to the displays' I²C buses and to a
connected measuring instrument (USB), the compositor and the desktop integration. Every problem comes with a
command or step that fixes it, phrased for the running distribution where package names differ.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess

from kelvincal.core.i18n import translate
from kelvincal.core.models import DisplayInfo

APP_ID = "de.colorcube.kelvincal"
OK, INFO, WARNING, ERROR = "ok", "info", "warning", "error"

# USB vendors of colorimeters/spectrometers ArgyllCMS drives: X-Rite, GretagMacbeth (i1 Pro), Datacolor
INSTRUMENT_VENDORS = {"0765", "0971", "085c"}

# package names per distribution family: ArgyllCMS is "argyll" on Debian/Ubuntu
_INSTALL = {
    "fedora": ("sudo dnf install", {}),
    "debian": ("sudo apt install", {"argyllcms": "argyll"}),
    "arch": ("sudo pacman -S", {}),
    "suse": ("sudo zypper install", {}),
}

# the project root when KelvinCal runs from a source checkout (bin/install-desktop exists there)
_SOURCE_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Check:
    key: str
    status: str          # OK, INFO, WARNING or ERROR
    title: str
    detail: str = ""
    fix: str = ""        # shell command(s) or a short instruction; "" if nothing to do


def distribution(os_release: Path = Path("/etc/os-release")) -> str:
    """"fedora", "debian", "arch", "suse" or "" (unknown), from ID/ID_LIKE."""
    try:
        text = os_release.read_text(encoding="utf-8")
    except OSError:
        return ""
    ids = " ".join(m.group(1).strip('"') for m in re.finditer(r"^(?:ID|ID_LIKE)=(.*)$", text, re.MULTILINE))
    for family, names in (("fedora", ("fedora", "rhel")), ("debian", ("debian", "ubuntu")),
                          ("arch", ("arch",)), ("suse", ("suse", "opensuse"))):
        if any(n in ids for n in names):
            return family
    return ""


def install_command(*packages: str, distro: str | None = None) -> str:
    family = distribution() if distro is None else distro
    if family not in _INSTALL:
        return translate("SetupCheck", "Install the package(s) {names} with your package manager.").format(
            names=", ".join(packages))
    command, names = _INSTALL[family]
    return f"{command} {' '.join(names.get(p, p) for p in packages)}"


def _version(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = (out.stdout or out.stderr).strip().splitlines()
    return lines[0].strip() if lines else ""


def _from_source(name: str) -> str:
    """`bin/<name>` of a source checkout, "" for an installed KelvinCal."""
    script = _SOURCE_ROOT / "bin" / name
    return str(script) if script.is_file() else ""


# ---------------------------------------------------------------------------------------------- checks

def check_argyll(argyll_version: str, distro: str | None = None) -> Check:
    missing = [t for t in ("spotread", "dispread", "targen", "colprof") if not shutil.which(t)]
    if not argyll_version or missing:
        return Check("argyll", ERROR, translate("SetupCheck", "ArgyllCMS is missing"),
                     translate("SetupCheck", "Needed for every measurement (missing: {tools}).").format(
                         tools=", ".join(missing) or "spotread"),
                     install_command("argyllcms", distro=distro))
    return Check("argyll", OK, translate("SetupCheck", "ArgyllCMS {version}").format(version=argyll_version))


def check_ddcutil(distro: str | None = None) -> Check:
    if not shutil.which("ddcutil"):
        return Check("ddcutil", ERROR, translate("SetupCheck", "ddcutil is missing"),
                     translate("SetupCheck", "Needed to set brightness, contrast and RGB gains of the displays "
                               "(DDC/CI)."), install_command("ddcutil", distro=distro))
    return Check("ddcutil", OK, _version(["ddcutil", "--version"]) or "ddcutil")


def check_i2c(displays: list[DisplayInfo], dev_root: Path = Path("/dev")) -> list[Check]:
    """Access to the I²C bus of each display, and whether it answers DDC/CI."""
    with_bus = [d for d in displays if d.i2c_bus is not None]
    if displays and not with_bus:
        return [Check("i2c", WARNING, translate("SetupCheck", "No I²C bus found for the displays"),
                      translate("SetupCheck", "Without the kernel module i2c-dev KelvinCal cannot reach the "
                                "displays over DDC/CI (laptop panels have no DDC/CI)."),
                      "sudo modprobe i2c-dev\n"
                      "echo i2c-dev | sudo tee /etc/modules-load.d/i2c-dev.conf")]
    checks: list[Check] = []
    denied = [d for d in with_bus if not os.access(dev_root / f"i2c-{d.i2c_bus}", os.R_OK | os.W_OK)]
    if denied:
        node = dev_root / f"i2c-{denied[0].i2c_bus}"
        try:
            import grp

            gid = node.stat().st_gid
            # a group to join (Debian: i2c); if already a member, or the node is root's only: udev rule
            group = grp.getgrgid(gid).gr_name if gid not in os.getgroups() else ""
        except (OSError, KeyError, ImportError):
            group = ""
        fix = (f"sudo usermod -aG {group} $USER" if group and group != "root" else
               "sudo cp /usr/share/ddcutil/data/60-ddcutil-i2c.rules /etc/udev/rules.d/\n"
               "sudo udevadm control --reload && sudo udevadm trigger")
        checks.append(Check(
            "i2c", ERROR, translate("SetupCheck", "No access to the I²C bus of {displays}").format(
                displays=", ".join(d.connector for d in denied)),
            translate("SetupCheck", "KelvinCal needs read/write access to {node} for DDC/CI. Log out and in "
                      "again after the fix.").format(node=node), fix))
    for d in with_bus:
        if d not in denied and d.ddc is None:
            checks.append(Check(
                f"ddc:{d.connector}", WARNING,
                translate("SetupCheck", "{display} does not answer over DDC/CI").format(
                    display=f"{d.connector} ({d.model})" if d.model else d.connector),
                translate("SetupCheck", "Brightness, contrast and RGB gains cannot be set; profiling still "
                          "works."),
                translate("SetupCheck", "Turn on “DDC/CI” in the display's on-screen menu, then press F5.")))
    if with_bus and not checks:
        checks.append(Check("i2c", OK, translate("SetupCheck", "DDC/CI works on {count} display(s)").format(
            count=len(with_bus))))
    return checks


def usb_instruments(usb_root: Path = Path("/sys/bus/usb/devices")) -> list[tuple[str, Path]]:
    """(product name, device node) of connected USB devices from instrument vendors."""
    found = []
    for dev in sorted(usb_root.glob("*")):
        try:
            if (dev / "idVendor").read_text().strip().lower() not in INSTRUMENT_VENDORS:
                continue
            bus, num = int((dev / "busnum").read_text()), int((dev / "devnum").read_text())
            name = (dev / "product").read_text().strip() if (dev / "product").exists() else dev.name
        except (OSError, ValueError):
            continue
        found.append((name, Path(f"/dev/bus/usb/{bus:03d}/{num:03d}")))
    return found


def check_instrument(instruments: list[str], usb: list[tuple[str, Path]], distro: str | None = None) -> Check:
    if instruments:
        return Check("instrument", OK, translate("SetupCheck", "Measuring instrument: {name}").format(
            name=", ".join(instruments)))
    denied = [(name, node) for name, node in usb if not os.access(node, os.R_OK | os.W_OK)]
    if denied:
        return Check(
            "instrument", ERROR, translate("SetupCheck", "No access to {name}").format(name=denied[0][0]),
            translate("SetupCheck", "The instrument is connected, but {node} may only be used by root. A udev "
                      "rule for colour instruments grants access (colord: 69-cd-sensors.rules). Unplug and "
                      "reconnect the instrument afterwards.").format(node=denied[0][1]),
            install_command("colord", distro=distro))
    if usb:
        return Check("instrument", WARNING, translate("SetupCheck", "{name} is not recognised by ArgyllCMS")
                     .format(name=usb[0][0]),
                     translate("SetupCheck", "Reconnect it; if it stays unrecognised, ArgyllCMS may be too old "
                               "for this instrument."))
    return Check("instrument", INFO, translate("SetupCheck", "No measuring instrument connected"),
                 translate("SetupCheck", "Needed for calibrating and verifying; switching presets works "
                           "without one."))


def check_compositor(name: str, distro: str | None = None) -> Check:
    if name != "kwin":
        return Check("compositor", WARNING, translate("SetupCheck", "Not running under KDE Plasma (KWin)"),
                     translate("SetupCheck", "KelvinCal activates ICC profiles through KWin; with {name} profiles "
                               "are only measured and saved.").format(name=name or "?"))
    if not shutil.which("kscreen-doctor"):
        return Check("compositor", ERROR, translate("SetupCheck", "kscreen-doctor is missing"),
                     translate("SetupCheck", "Needed to switch ICC profiles and colour modes in KWin."),
                     install_command("kscreen", distro=distro))
    version = re.search(r"\d+(?:\.\d+)+", _version(["kwin_wayland", "--version"]))
    return Check("compositor", OK, f"KWin {version.group(0)}" if version else "KWin")


def _data_dirs() -> list[Path]:
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return [Path(home)] + [Path(p) for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share")
                           .split(":") if p]


def check_desktop_entry() -> Check:
    if any((d / "applications" / f"{APP_ID}.desktop").is_file() for d in _data_dirs()):
        return Check("desktop", OK, translate("SetupCheck", "Desktop entry installed"))
    script = _from_source("install-desktop")
    return Check("desktop", WARNING, translate("SetupCheck", "Desktop entry is missing"),
                 translate("SetupCheck", "Without it Plasma shows no icon or name for KelvinCal, and notifications "
                           "and the desktop portal do not work."),
                 script or translate("SetupCheck", "Reinstall the KelvinCal package."))


def check_plasmoid() -> Check | None:
    """The preset switcher for the panel (only under Plasma)."""
    if "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        return None
    if any((d / "plasma" / "plasmoids" / f"{APP_ID}.applet").is_dir() for d in _data_dirs()):
        return Check("plasmoid", OK, translate("SetupCheck", "Panel widget installed"))
    script = _from_source("install-plasmoid")
    return Check("plasmoid", INFO, translate("SetupCheck", "Panel widget not installed (optional)"),
                 translate("SetupCheck", "Switches presets from the panel."),
                 script or translate("SetupCheck", "Install the package with the KelvinCal plasmoid."))


def check_interrupted() -> Check | None:
    """A measurement that did not end cleanly left a display in its raw state (see `recovery`)."""
    from kelvincal.core import recovery

    entries = recovery.interrupted()
    if not entries:
        return None
    return Check("recovery", WARNING, translate("SetupCheck", "Interrupted measurement on {displays}").format(
                     displays=", ".join(e.connector for e in entries)),
                 translate("SetupCheck", "The display may still show uncalibrated colours or measurement settings."),
                 "kelvincal-cli recover")


def run_checks(
    displays: list[DisplayInfo] | None = None,
    argyll_version: str | None = None,
    instruments: list[str] | None = None,
    compositor: str | None = None,
) -> list[Check]:
    """All checks; what is not passed in is detected here (the GUI passes what it already knows)."""
    if displays is None:
        from kelvincal.core.discovery import discover_displays

        displays = discover_displays(include_ddc_values=True)
    if argyll_version is None or instruments is None:
        from kelvincal.argyll.instruments import detect_instruments

        status = detect_instruments()
        argyll_version, instruments = status.argyll_version, status.instruments
    if compositor is None:
        from kelvincal.core.compositor import get_compositor_backend

        compositor = get_compositor_backend().name
    distro = distribution()
    checks = [check_argyll(argyll_version, distro), check_ddcutil(distro)]
    if shutil.which("ddcutil"):
        checks += check_i2c(displays)
    checks.append(check_instrument(instruments, usb_instruments(), distro))
    checks += [check_compositor(compositor, distro), check_desktop_entry()]
    checks += [c for c in (check_plasmoid(), check_interrupted()) if c is not None]
    return checks


def has_errors(checks: list[Check]) -> bool:
    return any(c.status == ERROR for c in checks)
