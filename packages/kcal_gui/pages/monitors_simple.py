"""Monitors page, simple mode (mockup 1b): pick a display, pick a purpose, start the full calibration."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from kcal_core.i18n import translate
from kcal_core.models import DisplayInfo
from kcal_core.targets import TARGETS, CalibrationTarget
from kcal_gui.fmt import cdm2, num
from kcal_gui.widgets import (
    Card,
    ClickableLabel,
    SecondaryLabel,
    SectionHeader,
    SegmentedControl,
    StatusDot,
    title_font,
)


def icc_label(display: DisplayInfo) -> str:
    if display.color_profile_source == "ICC" and display.icc_profile_path:
        return Path(display.icc_profile_path).name
    source = display.color_profile_source or "sRGB"
    return translate("MonitorsPage", "{source} (uncalibrated)").format(source=source)


def ddc_summary(display: DisplayInfo) -> str:
    d = display.ddc
    if d.brightness is None and d.contrast is None:
        return translate("MonitorsPage", "No DDC/CI values")
    gains = " / ".join(num(v) for v in (d.red_gain, d.green_gain, d.blue_gain))
    return translate("MonitorsPage", "Brightness {b} · Contrast {c} · RGB gain {g}").format(
        b=num(d.brightness, unit="%"), c=num(d.contrast, unit="%"), g=gains
    )


class MonitorCard(Card):
    """Selectable card for one display with live DDC values and the active ICC profile."""

    inspect_requested = Signal(str)  # connector

    def __init__(self, display: DisplayInfo, drift: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(selectable=True, parent=parent)
        self.display = display
        head = QHBoxLayout()
        conn = QLabel(display.connector)
        conn.setFont(title_font(self, 1.15))
        head.addWidget(conn)
        head.addStretch(1)
        if drift:
            dot = StatusDot("warning")
            badge = SecondaryLabel(translate("MonitorsPage", "Drift"))
            for w in (dot, badge):
                w.setToolTip(translate("MonitorsPage", "Live DDC values differ from the active preset."))
                head.addWidget(w)
        self.body.addLayout(head)
        self.body.addWidget(QLabel(display.model or translate("MonitorsPage", "Unknown model")))
        bus = f"/dev/i2c-{display.i2c_bus}" if display.i2c_bus is not None else translate("MonitorsPage", "no DDC/CI")
        self.body.addWidget(SecondaryLabel(f"SN {display.serial or '–'} · {bus}"))
        self.body.addSpacing(6)
        summary = SecondaryLabel(ddc_summary(display))
        summary.setWordWrap(True)
        self.body.addWidget(summary)
        icc_row = QHBoxLayout()
        icc_row.addWidget(SecondaryLabel(translate("MonitorsPage", "ICC active")))
        link = ClickableLabel(icc_label(display) + " ↗")
        link.setToolTip(translate("MonitorsPage", "Show profile"))
        link.clicked.connect(lambda: self.inspect_requested.emit(display.connector))
        icc_row.addWidget(link, 1)
        self.body.addLayout(icc_row)
        self.body.addStretch(1)
        self.setMinimumWidth(240)


class TargetCard(Card):
    """Selectable card for a calibration purpose; emits `changed` when its own options change."""

    changed = Signal()

    def __init__(self, target: CalibrationTarget, parent: QWidget | None = None) -> None:
        super().__init__(selectable=True, parent=parent)
        self.base = target
        self.d50 = False
        self.luminance = target.luminance
        head = QHBoxLayout()
        title = QLabel(target.display_title)
        title.setFont(title_font(self, 1.0))
        title.setWordWrap(True)
        head.addWidget(title, 1)
        if target.allow_d50:
            self.wp_switch = SegmentedControl(["D65", "D50"])
            self.wp_switch.currentChanged.connect(self._on_wp)
            head.addWidget(self.wp_switch)
        self.body.addLayout(head)
        if target.custom_luminance:
            row = QHBoxLayout()
            self.slider = QSlider(Qt.Orientation.Horizontal)
            self.slider.setRange(60, 250)
            self.slider.setSingleStep(5)
            self.slider.setPageStep(10)
            self.slider.setValue(int(target.luminance))
            self.slider_label = QLabel()
            self.slider.valueChanged.connect(self._on_lum)
            row.addWidget(self.slider, 1)
            row.addWidget(self.slider_label)
            self.body.addLayout(row)
        self.meta = SecondaryLabel()
        self.cost = SecondaryLabel()
        self.body.addWidget(self.meta)
        self.body.addWidget(self.cost)
        self.body.addStretch(1)
        self._refresh()

    def target(self) -> CalibrationTarget:
        return self.base.with_d50(self.d50).with_luminance(self.luminance)

    def _on_wp(self, index: int) -> None:
        self.d50 = index == 1
        self._refresh()
        self.clicked.emit()
        self.changed.emit()

    def _on_lum(self, value: int) -> None:
        self.luminance = float(value)
        self._refresh()
        self.clicked.emit()
        self.changed.emit()

    def _refresh(self) -> None:
        t = self.target()
        self.meta.setText(f"{cdm2(t.luminance, 0)} · {t.whitepoint_label} · {t.tone_label}")
        self.cost.setText(
            translate("MonitorsPage", "{patches} patches · approx. {minutes} min").format(
                patches=num(t.patch_count), minutes=t.estimated_minutes()
            )
        )
        if hasattr(self, "slider_label"):
            self.slider_label.setText(cdm2(t.luminance, 0))


class MonitorsSimplePage(QWidget):
    """Simple mode: three numbered steps, one button."""

    display_selected = Signal(str)
    inspect_requested = Signal(str)
    start_requested = Signal(str, object)  # connector, CalibrationTarget

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.displays: list[DisplayInfo] = []
        self.selected_connector = ""
        self._busy = False
        self.monitor_cards: list[MonitorCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 8, 16, 16)

        lay.addWidget(SectionHeader("1", translate("MonitorsPage", "Select display")))
        self.monitor_grid = QGridLayout()
        self.monitor_grid.setSpacing(12)
        lay.addLayout(self.monitor_grid)
        self.empty_label = SecondaryLabel(translate("MonitorsPage", "Detecting displays…"))
        lay.addWidget(self.empty_label)

        lay.addWidget(SectionHeader("2", translate("MonitorsPage", "Purpose")))
        target_grid = QGridLayout()
        target_grid.setSpacing(12)
        self.target_cards: list[TargetCard] = []
        for i, target in enumerate(TARGETS):
            card = TargetCard(target)
            card.clicked.connect(lambda c=card: self._select_target(c))
            card.changed.connect(self._update_summary)
            target_grid.addWidget(card, i // 4, i % 4)
            self.target_cards.append(card)
        lay.addLayout(target_grid)

        lay.addWidget(SectionHeader("3", translate("MonitorsPage", "Calibration")))
        summary_card = Card()
        self.summary_title = QLabel()
        self.summary_title.setFont(title_font(self, 1.05))
        self.summary_text = SecondaryLabel()
        self.summary_text.setWordWrap(True)
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.addWidget(self.summary_title)
        col.addWidget(self.summary_text)
        row.addLayout(col, 1)
        self.btn_start = QPushButton(translate("MonitorsPage", "Start Full Calibration"))
        self.btn_start.setDefault(True)
        self.btn_start.setMinimumHeight(36)
        self.btn_start.clicked.connect(self._start)
        row.addWidget(self.btn_start, 0, Qt.AlignmentFlag.AlignVCenter)
        summary_card.body.addLayout(row)
        lay.addWidget(summary_card)
        lay.addStretch(1)

        self.selected_target = self.target_cards[0]
        self.selected_target.setChecked(True)
        self._update_summary()

    # ------------------------------------------------------------------ public API

    def set_displays(self, displays: list[DisplayInfo], selected: str, drift: set[str] | None = None) -> None:
        for card in self.monitor_cards:
            self.monitor_grid.removeWidget(card)
            card.deleteLater()
        self.monitor_cards = []
        self.displays = displays
        for i, d in enumerate(displays):
            card = MonitorCard(d, drift=d.connector in (drift or set()))
            card.clicked.connect(lambda c=d.connector: self.display_selected.emit(c))
            card.inspect_requested.connect(self.inspect_requested)
            self.monitor_grid.addWidget(card, 0, i)
            self.monitor_cards.append(card)
        self.empty_label.setVisible(not displays)
        self.empty_label.setText(translate("MonitorsPage", "No displays detected."))
        self.set_selected(selected)

    def set_selected(self, connector: str) -> None:
        self.selected_connector = connector
        for card in self.monitor_cards:
            card.setChecked(card.display.connector == connector)
        self._update_summary()

    def set_target_key(self, key: str) -> None:
        for card in self.target_cards:
            if card.base.key == key:
                self._select_target(card)

    def current_target(self) -> CalibrationTarget:
        return self.selected_target.target()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_summary()

    # ------------------------------------------------------------------ internals

    def _selected_display(self) -> DisplayInfo | None:
        return next((d for d in self.displays if d.connector == self.selected_connector), None)

    def _select_target(self, card: TargetCard) -> None:
        self.selected_target = card
        for c in self.target_cards:
            c.setChecked(c is card)
        self._update_summary()

    def _update_summary(self) -> None:
        disp = self._selected_display()
        t = self.current_target()
        if disp is None:
            self.summary_title.setText(translate("MonitorsPage", "No display selected"))
            self.summary_text.setText("")
            self.btn_start.setEnabled(False)
            return
        self.summary_title.setText(f"{disp.model} ({disp.connector}) → {t.display_title}")
        if disp.i2c_bus is None:
            self.summary_text.setText(translate(
                "MonitorsPage",
                "This display has no DDC/CI. Contrast, whitepoint and luminance cannot be set in hardware.",
            ))
            self.btn_start.setEnabled(False)
            return
        self.summary_text.setText(translate(
            "MonitorsPage",
            "Place the sensor once in the centre. Contrast, whitepoint, luminance and profile then run "
            "automatically, approx. {minutes} minutes.",
        ).format(minutes=t.estimated_minutes()))
        self.btn_start.setEnabled(not self._busy)

    def _start(self) -> None:
        if self._selected_display() is not None:
            self.start_requested.emit(self.selected_connector, self.current_target())
