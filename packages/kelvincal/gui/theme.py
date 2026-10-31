"""Colour scheme support: follow the KDE system theme or apply an installed `.colors` scheme.

KDE colour schemes (`/usr/share/color-schemes/*.colors`, `~/.local/share/color-schemes/*.colors`) are INI
files with one group per colour set (`[Colors:Window]`, `[Colors:View]`, ...) and `r,g,b` values. There are
no Python bindings for KColorSchemeManager, so this module maps the documented colour sets onto QPalette
roles itself. "System" mode applies nothing: under Plasma the platform theme (plasma-integration) provides
style and palette and keeps following the system settings.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
import os
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QActionGroup, QColor, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMenu, QStyleFactory

from kelvincal.core.i18n import translate

SYSTEM_SCHEME = ""  # settings value for "follow the system"
SETTINGS_KEY = "appearance/color_scheme"


def scheme_dirs() -> list[Path]:
    """Directories searched for `.colors` files, user directory first (it overrides system schemes)."""
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    dirs = [data_home / "color-schemes"]
    for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if d:
            dirs.append(Path(d) / "color-schemes")
    return dirs


@dataclass(frozen=True)
class ColorScheme:
    """An installed KDE colour scheme file."""

    name: str  # display name from [General] Name, file stem as fallback
    path: Path

    @property
    def key(self) -> str:
        return self.path.stem


def available_schemes() -> list[ColorScheme]:
    """Lists the installed colour schemes sorted by name (a user file hides a system file of the same stem)."""
    found: dict[str, ColorScheme] = {}
    for directory in scheme_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.colors")):
            if path.stem in found:
                continue
            cfg = _read(path)
            name = cfg.get("General", "Name", fallback="") if cfg else ""
            found[path.stem] = ColorScheme(name=name or path.stem, path=path)
    return sorted(found.values(), key=lambda s: s.name.casefold())


def _read(path: Path) -> configparser.ConfigParser | None:
    cfg = configparser.ConfigParser(interpolation=None, strict=False)
    cfg.optionxform = str  # keys are case-sensitive (BackgroundNormal, ...)
    try:
        cfg.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        return None
    return cfg


def _color(cfg: configparser.ConfigParser, group: str, key: str, fallback: QColor) -> QColor:
    raw = cfg.get(f"Colors:{group}", key, fallback="")
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) >= 3:
        try:
            r, g, b = (int(p) for p in parts[:3])
            a = int(parts[3]) if len(parts) > 3 else 255
            return QColor(r, g, b, a)
        except ValueError:
            pass
    return fallback


def _mix(a: QColor, b: QColor, amount: float) -> QColor:
    """Linear blend from `a` (amount 0) to `b` (amount 1)."""
    t = max(0.0, min(1.0, amount))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        1.0,
    )


def palette_from_scheme(path: Path) -> QPalette:
    """Builds a QPalette from a KDE `.colors` file."""
    cfg = _read(path)
    if cfg is None:
        raise ValueError(f"Cannot read colour scheme {path}")
    base = QApplication.style().standardPalette() if QApplication.instance() else QPalette()

    def c(group: str, key: str, role: QPalette.ColorRole) -> QColor:
        return _color(cfg, group, key, base.color(QPalette.ColorGroup.Active, role))

    R = QPalette.ColorRole
    window_bg = c("Window", "BackgroundNormal", R.Window)
    button_bg = c("Button", "BackgroundNormal", R.Button)
    roles: dict[QPalette.ColorRole, QColor] = {
        R.Window: window_bg,
        R.WindowText: c("Window", "ForegroundNormal", R.WindowText),
        R.Base: c("View", "BackgroundNormal", R.Base),
        R.AlternateBase: c("View", "BackgroundAlternate", R.AlternateBase),
        R.Text: c("View", "ForegroundNormal", R.Text),
        R.PlaceholderText: c("View", "ForegroundInactive", R.PlaceholderText),
        R.Button: button_bg,
        R.ButtonText: c("Button", "ForegroundNormal", R.ButtonText),
        R.Highlight: c("Selection", "BackgroundNormal", R.Highlight),
        R.HighlightedText: c("Selection", "ForegroundNormal", R.HighlightedText),
        R.ToolTipBase: c("Tooltip", "BackgroundNormal", R.ToolTipBase),
        R.ToolTipText: c("Tooltip", "ForegroundNormal", R.ToolTipText),
        R.Link: c("View", "ForegroundLink", R.Link),
        R.LinkVisited: c("View", "ForegroundVisited", R.LinkVisited),
        R.BrightText: c("Window", "ForegroundNegative", R.BrightText),
        R.Accent: c("Selection", "BackgroundNormal", R.Highlight),
        R.Light: button_bg.lighter(150),
        R.Midlight: button_bg.lighter(125),
        R.Mid: button_bg.darker(130),
        R.Dark: button_bg.darker(170),
        R.Shadow: QColor(0, 0, 0),
    }

    # Disabled: fade foregrounds towards their background (KDE "ContrastEffect = fade" approximation).
    fade = cfg.getfloat("ColorEffects:Disabled", "ContrastAmount", fallback=0.65)
    disabled = dict(roles)
    for fg, bg in ((R.WindowText, R.Window), (R.Text, R.Base), (R.ButtonText, R.Button),
                   (R.HighlightedText, R.Highlight), (R.PlaceholderText, R.Base)):
        disabled[fg] = _mix(roles[fg], roles[bg], fade * 0.8)
    disabled[R.Highlight] = _mix(roles[R.Highlight], roles[R.Window], 0.5)

    pal = QPalette()
    for group, values in (
        (QPalette.ColorGroup.Active, roles),
        (QPalette.ColorGroup.Inactive, roles),
        (QPalette.ColorGroup.Disabled, disabled),
    ):
        for role, color in values.items():
            pal.setColor(group, role, color)
    return pal


def is_dark(palette: QPalette | None = None) -> bool:
    """True if the window background of `palette` (default: application palette) is dark."""
    pal = palette or QGuiApplication.palette()
    return pal.color(QPalette.ColorRole.Window).lightnessF() < 0.5


@dataclass(frozen=True)
class StatusColors:
    ok: QColor
    warning: QColor
    error: QColor
    red: QColor
    green: QColor
    blue: QColor


def status_colors(palette: QPalette | None = None) -> StatusColors:
    """Status and measurement-channel colours readable on the current background."""
    if is_dark(palette):
        return StatusColors(QColor(39, 174, 96), QColor(246, 116, 0), QColor(218, 68, 83),
                            QColor(255, 99, 99), QColor(92, 214, 92), QColor(99, 160, 255))
    return StatusColors(QColor(27, 133, 72), QColor(196, 90, 0), QColor(191, 42, 57),
                        QColor(204, 32, 32), QColor(24, 140, 24), QColor(32, 90, 214))


class ThemeManager(QObject):
    """Applies the colour scheme chosen in the settings and provides the "Colour Scheme" menu."""

    scheme_changed = Signal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self.current = SYSTEM_SCHEME
        self._ensure_style()

    def _ensure_style(self) -> None:
        # Outside Plasma (no plasma-integration) prefer Breeze over Qt's default style.
        if self.app.style().name().lower() not in ("breeze", "oxygen") and "Breeze" in QStyleFactory.keys():
            self.app.setStyle("Breeze")

    def restore(self) -> None:
        key = str(QSettings().value(SETTINGS_KEY, SYSTEM_SCHEME))
        self.apply(key, save=False)

    def apply(self, key: str, save: bool = True) -> None:
        scheme = next((s for s in available_schemes() if s.key == key), None)
        palette = None
        if scheme is not None:
            try:
                palette = palette_from_scheme(scheme.path)
            except ValueError:
                palette = None
        if palette is None:
            key = SYSTEM_SCHEME
            # KColorScheme (and thus the Breeze style for menu bar/header areas) reads this property, the
            # same mechanism KColorSchemeManager uses. Empty = system colours from kdeglobals.
            self.app.setProperty("KDE_COLOR_SCHEME_PATH", "")
        else:
            self.app.setProperty("KDE_COLOR_SCHEME_PATH", str(scheme.path))
        if key != self.current or not save:
            # Re-create the style so Breeze re-polishes existing widgets (menu bar text uses header colours).
            self.app.setStyle(QStyleFactory.create(self.app.style().name()))
        # An empty palette means: back to the platform (system) palette.
        self.app.setPalette(palette if palette is not None else QPalette())
        self.current = key
        if save:
            QSettings().setValue(SETTINGS_KEY, key)
        self.scheme_changed.emit(key)

    def build_menu(self, parent: QMenu) -> QMenu:
        """Creates the "Color Scheme" submenu (exclusive choice, current entry checked)."""
        menu = parent.addMenu(QIcon.fromTheme("preferences-desktop-color"), translate("Theme", "Color Scheme"))
        group = QActionGroup(menu)
        group.setExclusive(True)

        def add(label: str, key: str) -> None:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setData(key)
            act.setChecked(key == self.current)
            act.triggered.connect(lambda _=False, k=key: self.apply(k))
            group.addAction(act)

        add(translate("Theme", "Default (System)"), SYSTEM_SCHEME)
        menu.addSeparator()
        for scheme in available_schemes():
            add(scheme.name, scheme.key)

        def sync(key: str) -> None:
            for act in group.actions():
                act.setChecked(act.data() == key)

        self.scheme_changed.connect(sync)
        return menu
