"""Per-display spectral correction picker (panel technology → .ccss/.ccmx), stored in QSettings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QMessageBox, QToolButton, QVBoxLayout, QWidget

from kcal_argyll.corrections import TECHNOLOGIES, Correction, find_corrections, import_correction
from kcal_core.i18n import translate
from kcal_core.models import DisplayInfo
from kcal_gui.widgets import SecondaryLabel


def _key(display: DisplayInfo) -> str:
    return f"corrections/{display.edid_hash or display.connector}"


def correction_for(display: DisplayInfo | None) -> str | None:
    """The correction file chosen for `display`, if it still exists."""
    if display is None:
        return None
    path = str(QSettings().value(f"{_key(display)}/path", "") or "")
    return path if path and Path(path).is_file() else None


def correction_label(c: Correction) -> str:
    """List text: description plus the backlight technology, e.g. "WLED PFS Phosphor Family · Wide-gamut…"."""
    tech = next((translate("Corrections", label) for key, label, _p in TECHNOLOGIES if key == c.technology_key),
                c.technology)
    return f"{c.description} · {tech}" if tech else c.description


class CorrectionPicker(QWidget):
    """Correction file for the selected display (expert mode); every change is saved at once.

    Only a file has an effect: without one the instrument uses its built-in default calibration.
    """

    changed = Signal(str)  # path or ""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.display: DisplayInfo | None = None
        self.corrections: list[Correction] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(SecondaryLabel(translate("Corrections", "Spectral correction")))
        self.combo_file = QComboBox()
        self.combo_file.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_file.setMinimumContentsLength(32)
        self.combo_file.setToolTip(translate(
            "Corrections", "Colorimeter correction for the backlight of this display (.ccss for a technology, "
            ".ccmx for a display/instrument pair). Without a file the instrument uses its default calibration."))
        self.combo_file.activated.connect(self._on_file)
        row.addWidget(self.combo_file, 1)
        btn = QToolButton()
        btn.setIcon(QIcon.fromTheme("document-import"))
        btn.setText(translate("Corrections", "Import…"))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.clicked.connect(self._import)
        row.addWidget(btn)
        lay.addLayout(row)
        self.hint = SecondaryLabel()
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.reload()

    # ------------------------------------------------------------------ public API

    def reload(self) -> None:
        self.corrections = find_corrections()
        self._refresh()

    def set_display(self, display: DisplayInfo | None) -> None:
        self.display = display
        self.setEnabled(display is not None)
        self._refresh()

    def current_path(self) -> str:
        return str(self.combo_file.currentData() or "")

    # ------------------------------------------------------------------ internals

    def _refresh(self) -> None:
        selected = str(QSettings().value(f"{_key(self.display)}/path", "") or "") if self.display else ""
        self.combo_file.clear()
        self.combo_file.addItem(translate("Corrections", "None (instrument default)"), "")
        for c in self.corrections:
            self.combo_file.addItem(correction_label(c), str(c.path))
            tip = " · ".join(t for t in (c.technology, c.display, c.instrument, str(c.path)) if t)
            self.combo_file.setItemData(self.combo_file.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        if selected and self.combo_file.findData(selected) < 0 and Path(selected).is_file():
            self.combo_file.addItem(Path(selected).name, selected)
        self.combo_file.setCurrentIndex(max(0, self.combo_file.findData(selected)))
        self.hint.setText("" if self.corrections else translate(
            "Corrections", "No correction files installed. Import a .ccss/.ccmx file, or install the "
            "manufacturer's corrections with ArgyllCMS “oeminst”."))
        self.hint.setVisible(bool(self.hint.text()))

    def _save(self, path: str) -> None:
        if self.display is None:
            return
        QSettings().setValue(f"{_key(self.display)}/path", path)
        self.changed.emit(path)

    def _on_file(self, _index: int) -> None:
        self._save(self.current_path())

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
        self.corrections = find_corrections()
        self._save(str(installed.path))
        self._refresh()
