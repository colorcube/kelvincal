"""Per-display spectral correction (.ccss/.ccmx) and instrument measurement mode (-y), stored in QSettings.

What can be chosen depends on the connected instrument (`set_instrument`): which correction files it accepts
(spectrometers none, older colorimeters only .ccmx) and its built-in -y modes. spotread also lists installed
correction files as -y modes; those are offered as files only, so each file appears once.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QComboBox, QFileDialog, QGridLayout, QMessageBox, QToolButton, QVBoxLayout, QWidget

from kcal_argyll.corrections import (
    TECHNOLOGIES,
    Correction,
    correction_for_display_type,
    find_corrections,
    import_correction,
)
from kcal_argyll.instruments import DisplayType, InstrumentStatus, correction_kinds, is_spectrometer
from kcal_core.i18n import translate
from kcal_core.models import DisplayInfo
from kcal_gui.widgets import SecondaryLabel


def _key(display: DisplayInfo) -> str:
    return f"corrections/{display.edid_hash or display.connector}"


# Instrument KelvinCal measures with; empty until detected (then nothing is filtered).
_instrument = InstrumentStatus()
_corrections: list[Correction] | None = None   # installed files, read on first use


def set_instrument(status: InstrumentStatus) -> None:
    global _instrument
    _instrument = status


def reload_corrections() -> list[Correction]:
    global _corrections
    _corrections = find_corrections()
    return _corrections


def _installed() -> list[Correction]:
    return _corrections if _corrections is not None else reload_corrections()


def _correction_kinds() -> tuple[str, ...] | None:
    """Correction file types the instrument accepts; None if no instrument is known."""
    return correction_kinds(_instrument.primary) if _instrument.instruments else None


def _usable(path: str) -> bool:
    kinds = _correction_kinds()
    return bool(path) and (kinds is None or Path(path).suffix.lower().lstrip(".") in kinds) and Path(path).is_file()


def builtin_modes() -> list[DisplayType]:
    """The instrument's own -y modes, without the installed correction files spotread lists among them."""
    return [t for t in _instrument.display_types if correction_for_display_type(t.description, _installed()) is None]


def default_correction() -> str:
    """For a display without a choice: the manufacturer's white-LED family if installed (what -y e meant before)."""
    return next((str(c.path) for c in _installed()
                 if c.kind == "ccss" and c.technology_key == "wled" and _usable(str(c.path))), "")


def correction_for(display: DisplayInfo | None) -> str | None:
    """The correction file used for `display`, if it still exists and the instrument can use it.

    Without a choice: the file an older KelvinCal selected as -y mode (taken over once), else
    `default_correction()`. "None" is stored as an empty path.
    """
    if display is None:
        return None
    settings = QSettings()
    stored = settings.value(f"{_key(display)}/path")
    if stored is None:
        mode = _instrument.display_type(str(settings.value(f"{_key(display)}/display_type", "") or ""))
        file = correction_for_display_type(mode.description, _installed()) if mode else None
        if file is not None:
            settings.setValue(f"{_key(display)}/path", str(file.path))
            settings.remove(f"{_key(display)}/display_type")
            stored = str(file.path)
        else:
            return default_correction() or None
    path = str(stored or "")
    return path if _usable(path) else None


def mode_needed(display: DisplayInfo | None) -> bool:
    """False if the correction file decides: newer colorimeters take calibration and refresh mode from it
    (older ones keep their -y mode, a .ccmx only corrects it); spectrometers have no modes."""
    if _instrument.instruments and is_spectrometer(_instrument.primary):
        return False
    return not (correction_for(display) and "ccss" in (_correction_kinds() or ("ccss",)))


def display_type_for(display: DisplayInfo | None) -> str:
    """-y mode for `display`: "" if the correction file decides or the instrument is unknown; else the
    chosen built-in mode, or the instrument's default."""
    if not mode_needed(display):
        return ""
    modes = builtin_modes()
    stored = str(QSettings().value(f"{_key(display)}/display_type", "") or "") if display else ""
    if any(t.key == stored for t in modes):
        return stored
    return next((t.key for t in modes if t.is_default), modes[0].key if modes else "")


def measurement_mode(display: DisplayInfo | None) -> tuple[str, str]:
    """(-y key, name) for `display`, e.g. ("r", "Refresh display"); ("", "") if no -y is passed."""
    key = display_type_for(display)
    t = _instrument.display_type(key)
    return key, t.label if t else ""


def correction_label(c: Correction) -> str:
    """List text. A manufacturer's family correction is named by its technology, e.g. "LCD White LED IPS ·
    general (X-Rite)" (its DISPLAY only lists the panels it was made from); others by description and
    technology, e.g. "Dell U2723QE · Wide-gamut LED / PFS (KSF) phosphor"."""
    tech = next((translate("Corrections", label) for key, label, _p in TECHNOLOGIES if key == c.technology_key),
                "" if c.technology.lower() in ("", "unknown") else c.technology)
    if c.generic:
        general = (translate("Corrections", "general ({maker})").format(maker=c.originator) if c.originator
                   else translate("Corrections", "general"))
        return f"{c.technology or tech or c.path.stem} · {general}"
    return f"{c.description} · {tech}" if tech else c.description


def _list_order(c: Correction) -> tuple[bool, str]:
    """Family corrections first, then the ones made for a display."""
    return not c.generic, correction_label(c).lower()


class CorrectionPicker(QWidget):
    """Correction file for the selected display (expert mode); every change is saved at once.

    Without a file the instrument measures with its built-in calibration and the chosen mode.
    """

    changed = Signal(str)  # path or ""
    measure_requested = Signal()   # "Measure own correction…" (needs a spectrometer)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.display: DisplayInfo | None = None
        self.corrections: list[Correction] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        grid.addWidget(SecondaryLabel(translate("Corrections", "Spectral correction")), 0, 0)
        self.combo_file = QComboBox()
        self.combo_file.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_file.setMinimumContentsLength(32)
        self.combo_file.setToolTip(translate(
            "Corrections", "Colorimeter correction for the backlight of this display (.ccss for a technology, "
            ".ccmx for a display/instrument pair). Without a file the instrument uses its built-in calibration."))
        self.combo_file.activated.connect(self._on_file)
        grid.addWidget(self.combo_file, 0, 1)
        btn = QToolButton()
        btn.setIcon(QIcon.fromTheme("document-import"))
        btn.setText(translate("Corrections", "Import…"))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.clicked.connect(self._import)
        grid.addWidget(btn, 0, 2)
        self.btn_measure = QToolButton()
        self.btn_measure.setIcon(QIcon.fromTheme("color-picker"))
        self.btn_measure.setText(translate("Corrections", "Measure Own…"))
        self.btn_measure.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_measure.clicked.connect(self.measure_requested)
        grid.addWidget(self.btn_measure, 0, 3)
        self.label_mode = SecondaryLabel(translate("Corrections", "Measurement mode"))
        grid.addWidget(self.label_mode, 1, 0)
        self.combo_mode = QComboBox()
        self.combo_mode.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_mode.setMinimumContentsLength(32)
        self.combo_mode.setToolTip(translate(
            "Corrections", "Built-in measurement mode of the colorimeter (spotread/dispread -y), e.g. for "
            "displays with or without refresh (CRT, plasma, some LED backlights)."))
        self.combo_mode.activated.connect(self._on_mode)
        grid.addWidget(self.combo_mode, 1, 1)
        lay.addLayout(grid)
        self._spectrometer = ""
        self._busy = False
        self._update_measure()
        self.hint = SecondaryLabel()
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.reload()

    # ------------------------------------------------------------------ public API

    def reload(self) -> None:
        self.corrections = reload_corrections()
        self._refresh()

    def set_display(self, display: DisplayInfo | None) -> None:
        self.display = display
        self.setEnabled(display is not None)
        self._refresh()

    def current_path(self) -> str:
        return str(self.combo_file.currentData() or "")

    def set_instrument(self, status: InstrumentStatus) -> None:
        """Connected instruments: offers their -y modes and the correction files the first one accepts."""
        set_instrument(status)
        spectro = status.spectrometers()
        self.set_spectrometer(spectro[0][1] if spectro else "")
        self._refresh()

    def set_spectrometer(self, name: str) -> None:
        """Name of a connected spectrometer ("" = none): only a spectrometer can measure a .ccss."""
        self._spectrometer = name
        self._update_measure()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_measure()

    def assign(self, path: str) -> None:
        """Makes `path` (e.g. a freshly measured .ccss) the correction of the current display."""
        self.corrections = reload_corrections()
        self._save(path)
        self._refresh()

    # ------------------------------------------------------------------ internals

    def _refresh(self) -> None:
        selected = correction_for(self.display) or ""
        kinds = _correction_kinds()
        self.combo_file.clear()
        self.combo_file.addItem(translate("Corrections", "None (built-in calibration)"), "")
        for c in sorted(self.corrections, key=_list_order):
            if kinds is not None and c.kind not in kinds:
                continue
            self.combo_file.addItem(correction_label(c), str(c.path))
            tip = " · ".join(t for t in (c.technology, c.display, c.instrument, str(c.path)) if t)
            self.combo_file.setItemData(self.combo_file.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        if selected and self.combo_file.findData(selected) < 0:
            self.combo_file.addItem(Path(selected).name, selected)
        self.combo_file.setCurrentIndex(max(0, self.combo_file.findData(selected)))
        self.combo_file.setEnabled(kinds != ())
        self._refresh_modes()
        hints = []
        if kinds == ():
            hints.append(translate("Corrections", "{name} measures the spectrum itself and needs no correction.")
                         .format(name=_instrument.primary))
        elif kinds == ("ccmx",):
            hints.append(translate("Corrections", "{name} cannot use spectral samples (.ccss); only correction "
                                   "matrices (.ccmx) made for this instrument are listed.").format(
                                       name=_instrument.primary))
        if not self.corrections:
            hints.append(translate(
                "Corrections", "No correction files installed. Import a .ccss/.ccmx file, or install the "
                "manufacturer's corrections with ArgyllCMS “oeminst”."))
        elif self.current_path() and not mode_needed(self.display):
            hints.append(translate("Corrections", "The instrument takes its calibration and refresh mode from "
                                   "the correction file."))
        self.hint.setText("\n".join(hints))
        self.hint.setVisible(bool(hints))

    def _refresh_modes(self) -> None:
        modes = builtin_modes()
        self.combo_mode.clear()
        for t in modes:
            self.combo_mode.addItem(t.label, t.key)
            self.combo_mode.setItemData(self.combo_mode.count() - 1, f"{t.description} (-y {t.key})",
                                        Qt.ItemDataRole.ToolTipRole)
        self.combo_mode.setCurrentIndex(max(0, self.combo_mode.findData(display_type_for(self.display))))
        # only while it matters: not for spectrometers, not when the correction file sets the mode
        visible = bool(modes) and mode_needed(self.display)
        self.label_mode.setVisible(visible)
        self.combo_mode.setVisible(visible)

    def _update_measure(self) -> None:
        self.btn_measure.setEnabled(bool(self._spectrometer) and not self._busy)
        self.btn_measure.setToolTip(
            translate("Corrections", "Measures white, red, green and blue of this display with {name} and creates "
                      "a .ccss correction for the colorimeter (about 2 minutes).").format(name=self._spectrometer)
            if self._spectrometer else
            translate("Corrections", "Needs a spectrometer (e.g. i1 Pro, ColorMunki); connect it and press F5."))

    def _save(self, path: str) -> None:
        if self.display is None:
            return
        QSettings().setValue(f"{_key(self.display)}/path", path)
        self.changed.emit(path)

    def _on_file(self, _index: int) -> None:
        self._save(self.current_path())
        self._refresh()

    def current_mode(self) -> str:
        return str(self.combo_mode.currentData() or "")

    def _on_mode(self, _index: int) -> None:
        if self.display is None:
            return
        QSettings().setValue(f"{_key(self.display)}/display_type", self.current_mode())
        self.changed.emit(self.current_path())

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, translate("Corrections", "Import Correction"), str(Path.home()),
            translate("Corrections", "Colorimeter corrections (*.ccss *.ccmx)"))
        if not path:
            return
        try:
            installed = import_correction(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, translate("Corrections", "Import Correction"), str(exc))
            return
        self.corrections = reload_corrections()
        self._save(str(installed.path))
        self._refresh()
