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


class CorrectionPicker(QWidget):
    """Panel technology and correction file for the selected display; every change is saved at once."""

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
        self.combo_tech = QComboBox()
        self.combo_tech.addItem(translate("Corrections", "Panel technology: unknown"), "")
        for key, label, _pattern in TECHNOLOGIES:
            self.combo_tech.addItem(translate("Corrections", label), key)
        self.combo_tech.setToolTip(translate(
            "Corrections", "Backlight / panel type of this display. Selects a matching correction file."))
        self.combo_tech.activated.connect(self._on_technology)
        row.addWidget(self.combo_tech)
        self.combo_file = QComboBox()
        self.combo_file.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_file.setMinimumContentsLength(24)
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

    def _settings_value(self, name: str) -> str:
        return str(QSettings().value(f"{_key(self.display)}/{name}", "") or "") if self.display else ""

    def _save(self, technology: str, path: str) -> None:
        if self.display is None:
            return
        st = QSettings()
        st.setValue(f"{_key(self.display)}/technology", technology)
        st.setValue(f"{_key(self.display)}/path", path)
        self.changed.emit(path)

    def _refresh(self) -> None:
        tech = self._settings_value("technology")
        path = self._settings_value("path")
        self.combo_tech.setCurrentIndex(max(0, self.combo_tech.findData(tech)))
        self._fill_files(tech, path)

    def _matching(self, tech: str) -> list[Correction]:
        if not tech:
            return self.corrections
        return [c for c in self.corrections if c.technology_key == tech]

    def _fill_files(self, tech: str, selected: str) -> None:
        self.combo_file.clear()
        self.combo_file.addItem(translate("Corrections", "No correction (instrument default)"), "")
        for c in self._matching(tech):
            self.combo_file.addItem(c.label, str(c.path))
            tip = " · ".join(t for t in (c.technology, c.display, c.instrument, str(c.path)) if t)
            self.combo_file.setItemData(self.combo_file.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        if selected and self.combo_file.findData(selected) < 0 and Path(selected).is_file():
            self.combo_file.addItem(Path(selected).name, selected)  # chosen earlier, other technology
        self.combo_file.setCurrentIndex(max(0, self.combo_file.findData(selected)))
        if not self.corrections:
            self.hint.setText(translate(
                "Corrections", "No correction files installed. Import a .ccss/.ccmx file, or install the "
                "manufacturer's corrections with ArgyllCMS “oeminst”."))
        elif tech and not self._matching(tech):
            self.hint.setText(translate("Corrections", "No installed correction matches this technology."))
        else:
            self.hint.setText("")
        self.hint.setVisible(bool(self.hint.text()))

    def _on_technology(self, _index: int) -> None:
        tech = str(self.combo_tech.currentData() or "")
        matches = self._matching(tech)
        path = str(matches[0].path) if tech and matches else self.current_path() if not tech else ""
        self._fill_files(tech, path)
        self._save(tech, path)

    def _on_file(self, _index: int) -> None:
        self._save(str(self.combo_tech.currentData() or ""), self.current_path())

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
        tech = installed.technology_key
        self.combo_tech.setCurrentIndex(max(0, self.combo_tech.findData(tech)))
        self._fill_files(tech, str(installed.path))
        self._save(tech, str(installed.path))
