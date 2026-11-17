"""Per-display switch for DDC/CI hardware control, stored in QSettings (kelvincal.conf).

When the switch is off, KelvinCal must not write any VCP code for that display: the user set
brightness, contrast and the RGB gains by hand (in the monitor's OSD or with the Manual
Adjustment dialog) and calibration/profiling only measures and profiles that state.

The key follows the other per-display settings (`corrections/<id>`, `whiteoffset/<id>`):
`ddc/<edid hash or connector>/enabled`, default on (the historical behaviour).
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import QCheckBox, QWidget

from kelvincal.core.i18n import translate
from kelvincal.core.models import DisplayInfo


def _key(display: DisplayInfo) -> str:
    return f"ddc/{display.edid_hash or display.connector}"


def ddc_control_enabled(display: DisplayInfo | None) -> bool:
    """True unless the user turned DDC/CI control off for `display` (default: on)."""
    if display is None:
        return True
    value = QSettings().value(f"{_key(display)}/enabled", "true")
    return str(value).lower() not in ("false", "0", "no")


def set_ddc_control_enabled(display: DisplayInfo, enabled: bool) -> None:
    QSettings().setValue(f"{_key(display)}/enabled", "true" if enabled else "false")


class DdcControlCheck(QCheckBox):
    """Per-display switch "Adjust monitor settings via DDC/CI", bound to the selected display.

    Emits `changed(connector, enabled)` after storing the value, so the page can re-evaluate its
    buttons. Hidden for displays without an I²C bus (the switch would have no effect).
    """

    changed = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(translate("MonitorsPage", "Adjust monitor settings via DDC/CI"), parent)
        self.setToolTip(translate(
            "MonitorsPage",
            "Off: KelvinCal never writes brightness, contrast or RGB gains for this display. Set them by "
            "hand in the monitor's menu (or with Manual Adjustment); calibration then only measures and "
            "profiles the display as it is."))
        self._display: DisplayInfo | None = None
        self.toggled.connect(self._on_toggled)

    def set_display(self, display: DisplayInfo | None) -> None:
        self._display = display
        self.setVisible(display is not None and display.i2c_bus is not None)
        self.blockSignals(True)
        self.setChecked(ddc_control_enabled(display))
        self.blockSignals(False)

    def _on_toggled(self, enabled: bool) -> None:
        if self._display is None:
            return
        set_ddc_control_enabled(self._display, enabled)
        self.changed.emit(self._display.connector, enabled)
