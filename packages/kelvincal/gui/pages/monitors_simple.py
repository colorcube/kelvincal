"""Monitors page, simple mode (mockup 1b): pick a display, pick a purpose, start the full calibration."""

from __future__ import annotations

from pathlib import Path
import weakref

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kelvincal.argyll.instruments import DEFAULT_OBSERVER, is_slow_sensor, observer_label
from kelvincal.core.i18n import translate
from kelvincal.core.models import DisplayInfo
from kelvincal.core.setup_check import ddc_problem, manual_adjustment_note
from kelvincal.core.targets import (
    PATCH_PRESETS,
    PATCH_STANDARD,
    TARGETS,
    WORKFLOW_DDC,
    WORKFLOW_PROFILE,
    WORKFLOW_SOFTWARE,
    CalibrationTarget,
    PatchPreset,
    estimate_duration_minutes,
    preset_for_count,
)
from kelvincal.gui.fmt import cdm2, num
from kelvincal.gui.pages.correction import CorrectionPicker, correction_for, observer_for
from kelvincal.gui.screens import screen_geometries
from kelvincal.gui.widgets import (
    ArrangedDisplay,
    Card,
    DdcBars,
    DisplayArrangement,
    ElidedLabel,
    MessageBanner,
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


def ddc_rows(display: DisplayInfo) -> list[tuple[str, str]]:
    """(label, value) pairs for the DDC values shown on a monitor card."""
    d = display.ddc
    if d.brightness is None and d.contrast is None:
        return [(translate("MonitorsPage", "DDC/CI"), translate("MonitorsPage", "no values"))]
    gains = " / ".join(num(v) for v in (d.red_gain, d.green_gain, d.blue_gain))
    return [
        (translate("MonitorsPage", "Brightness"), num(d.brightness, unit="%")),
        (translate("MonitorsPage", "Contrast"), num(d.contrast, unit="%")),
        (translate("MonitorsPage", "RGB gain"), gains),
    ]


def arrangement_items(displays: list[DisplayInfo], drift: set[str] | None = None) -> list[ArrangedDisplay]:
    """Arrangement entries for all `displays` that have a desktop position (see `screen_geometries`)."""
    geometries = screen_geometries()
    items = []
    for d in displays:
        g = geometries.get(d.connector)
        if g is None or g.isEmpty():
            continue
        mode = f"{d.width} × {d.height}" if d.width and d.height else f"{g.width()} × {g.height()}"
        items.append(ArrangedDisplay(d.connector, d.model or d.connector, mode, g,
                                     warning=d.connector in (drift or set()), enabled=True))
    return items


def watch_screens(callback) -> None:  # noqa: ANN001
    """Calls `callback()` when outputs are added, removed or moved."""
    app = QGuiApplication.instance()
    if app is None:
        return

    def watch(screen, update: bool = True) -> None:  # noqa: ANN001 - QScreen
        screen.geometryChanged.connect(lambda _g: callback())
        if update:
            callback()

    app.screenAdded.connect(watch)
    app.screenRemoved.connect(lambda _s: callback())
    for screen in QGuiApplication.screens():
        watch(screen, update=False)


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
        model = ElidedLabel(display.model or translate("MonitorsPage", "Unknown model"),
                            mode=Qt.TextElideMode.ElideRight)
        self.body.addWidget(model)
        bus = f"/dev/i2c-{display.i2c_bus}" if display.i2c_bus is not None else translate("MonitorsPage", "no DDC/CI")
        self.body.addWidget(ElidedLabel(f"SN {display.serial or '–'} · {bus}", secondary=True,
                                        mode=Qt.TextElideMode.ElideRight))
        self.body.addSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        rows = ddc_rows(display)
        for row, (label, value) in enumerate(rows):
            grid.addWidget(SecondaryLabel(label), row, 0)
            grid.addWidget(ElidedLabel(value), row, 1)
        grid.addWidget(SecondaryLabel(translate("MonitorsPage", "ICC active")), len(rows), 0)
        icc_row = QHBoxLayout()
        icc_row.setSpacing(6)
        icc_row.addWidget(ElidedLabel(icc_label(display)), 1)
        link = QToolButton()
        link.setText("↗")
        link.setToolTip(translate("MonitorsPage", "Show profile"))
        link.clicked.connect(lambda: self.inspect_requested.emit(display.connector))
        icc_row.addWidget(link)
        grid.addLayout(icc_row, len(rows), 1)
        self.body.addLayout(grid)
        self.body.addStretch(1)
        self.setMinimumWidth(220)


class MonitorDetail(QWidget):
    """Details of the selected display under the arrangement view (no frame, on the page background).

    The header line (connector, model, serial, drift) is always visible; DDC values and colour state
    fold out. The folding state is shared by all instances and kept in QSettings.
    """

    inspect_requested = Signal(str)  # connector

    SETTINGS_KEY = "monitors/details_expanded"
    _instances: "weakref.WeakSet[MonitorDetail]" = weakref.WeakSet()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.connector = ""
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 4, 4)
        self.body.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setAutoRaise(True)
        self.toggle.setToolTip(translate("MonitorsPage", "Show or hide DDC values and colour state"))
        self.toggle.clicked.connect(lambda: self.set_expanded(not self.expanded))
        head.addWidget(self.toggle)
        self.title = QLabel()
        self.title.setFont(title_font(self, 1.15))
        head.addWidget(self.title)
        self.model = ElidedLabel(mode=Qt.TextElideMode.ElideRight)
        self.model.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        head.addWidget(self.model)
        head.addSpacing(12)
        self.ident = ElidedLabel(secondary=True, mode=Qt.TextElideMode.ElideRight)
        head.addWidget(self.ident, 1)
        self.drift_dot = StatusDot("warning")
        self.drift_label = SecondaryLabel(translate("MonitorsPage", "Drift"))
        for w in (self.drift_dot, self.drift_label):
            w.setToolTip(translate("MonitorsPage", "Live DDC values differ from the active preset."))
            head.addWidget(w)
        self.body.addLayout(head)

        cols = QHBoxLayout()
        cols.setSpacing(32)
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(SecondaryLabel(translate("MonitorsPage", "DDC/CI live")))
        self.ddc_bars = DdcBars({
            "brightness": translate("MonitorsPage", "Brightness"),
            "contrast": translate("MonitorsPage", "Contrast"),
            "red_gain": translate("MonitorsPage", "Red"),
            "green_gain": translate("MonitorsPage", "Green"),
            "blue_gain": translate("MonitorsPage", "Blue"),
        })
        left.addWidget(self.ddc_bars)
        self.no_ddc = SecondaryLabel(translate(
            "MonitorsPage", "No DDC/CI: contrast, whitepoint and luminance cannot be set in hardware. "
            "Software calibration (vcgt) or profiling only can be used."))
        self.no_ddc.setWordWrap(True)
        left.addWidget(self.no_ddc)
        left.addStretch(1)
        cols.addLayout(left, 3)

        right = QGridLayout()
        right.setHorizontalSpacing(12)
        right.setVerticalSpacing(6)
        right.setColumnStretch(1, 1)
        right.addWidget(SecondaryLabel(translate("MonitorsPage", "ICC active")), 0, 0)
        icc_row = QHBoxLayout()
        icc_row.setSpacing(6)
        self.icc = ElidedLabel()
        icc_row.addWidget(self.icc, 1)
        link = QToolButton()
        link.setText("↗")
        link.setToolTip(translate("MonitorsPage", "Show profile"))
        link.clicked.connect(lambda: self.connector and self.inspect_requested.emit(self.connector))
        icc_row.addWidget(link)
        right.addLayout(icc_row, 0, 1)
        self.info: dict[str, ElidedLabel] = {}
        for row, (key, label) in enumerate((
            ("source", translate("MonitorsPage", "Colour source")),
            ("mode", translate("MonitorsPage", "Mode")),
            ("hdr", "HDR / WCG"),
        ), start=1):
            right.addWidget(SecondaryLabel(label), row, 0)
            value = ElidedLabel(mode=Qt.TextElideMode.ElideRight)
            right.addWidget(value, row, 1)
            self.info[key] = value
        right.setRowStretch(4, 1)
        cols.addLayout(right, 2)
        self.details = QWidget()
        self.details.setLayout(cols)
        cols.setContentsMargins(28, 0, 0, 0)
        self.body.addWidget(self.details)
        self.expanded = str(QSettings().value(self.SETTINGS_KEY, "false")).lower() == "true"
        self._apply_expanded()
        MonitorDetail._instances.add(self)

    def set_expanded(self, expanded: bool) -> None:
        QSettings().setValue(self.SETTINGS_KEY, expanded)
        for inst in list(MonitorDetail._instances):  # simple and expert page show the same state
            inst.expanded = expanded
            inst._apply_expanded()

    def _apply_expanded(self) -> None:
        self.details.setVisible(self.expanded)
        self.toggle.setIcon(QIcon.fromTheme("arrow-down" if self.expanded else "arrow-right"))

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        """A click on the header line folds as well (not only the arrow)."""
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= self.toggle.geometry().bottom():
            self.set_expanded(not self.expanded)
            return
        super().mousePressEvent(event)

    def set_display(self, display: DisplayInfo | None, drift: bool = False) -> None:
        self.setVisible(display is not None)
        if display is None:
            self.connector = ""
            return
        self.connector = display.connector
        self.title.setText(display.connector)
        self.model.setText(display.model or translate("MonitorsPage", "Unknown model"))
        bus = f"/dev/i2c-{display.i2c_bus}" if display.i2c_bus is not None else translate("MonitorsPage", "no DDC/CI")
        self.ident.setText(f"SN {display.serial or '–'} · {bus}")
        self.drift_dot.setVisible(drift)
        self.drift_label.setVisible(drift)
        has_ddc = display.i2c_bus is not None
        self.ddc_bars.setVisible(has_ddc)
        self.no_ddc.setVisible(not has_ddc)
        self.ddc_bars.set_values(display.ddc)
        self.icc.setText(icc_label(display))
        self.info["source"].setText(display.color_profile_source or "–")
        mode = f"{display.width} × {display.height}" if display.width and display.height else "–"
        if display.width:
            mode += f" @ {num(display.refresh_hz, 0)} Hz · {num(display.scale * 100)} %"
        self.info["mode"].setText(mode)
        on, off = translate("MonitorsPage", "on"), translate("MonitorsPage", "off")
        self.info["hdr"].setText(f"{on if display.hdr_enabled else off} / {on if display.wcg_enabled else off}")


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
        self.body.addWidget(self.meta)
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
        if hasattr(self, "slider_label"):
            self.slider_label.setText(cdm2(t.luminance, 0))


class WorkflowCard(Card):
    """Selectable card for one of the three calibration workflows (DDC/CI, Software vcgt, Profile only)."""

    def __init__(self, key: str, title: str, badge: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(selectable=True, parent=parent)
        self.key = key
        lbl_title = QLabel(title)
        lbl_title.setFont(title_font(self, 1.0))
        lbl_title.setWordWrap(True)
        self.body.addWidget(lbl_title)
        self.lbl_badge = SecondaryLabel(badge)
        self.lbl_badge.setWordWrap(True)
        self.body.addWidget(self.lbl_badge)
        self.lbl_desc = SecondaryLabel(description)
        self.lbl_desc.setWordWrap(True)
        self.body.addWidget(self.lbl_desc)
        self.lbl_unavailable = SecondaryLabel()
        self.lbl_unavailable.setWordWrap(True)
        self.lbl_unavailable.hide()
        self.body.addWidget(self.lbl_unavailable)
        self.body.addStretch(1)

    def set_unavailable(self, reason: str) -> None:
        self.setEnabled(not reason)
        self.lbl_unavailable.setText(reason)
        self.lbl_unavailable.setVisible(bool(reason))


class PatchPresetCard(Card):
    """Selectable card for a patch count preset (Fast 79, Standard 175, High 403, or Custom spinbox)."""

    changed = Signal()

    def __init__(self, preset: PatchPreset, parent: QWidget | None = None) -> None:
        super().__init__(selectable=True, parent=parent)
        self.preset = preset
        head = QHBoxLayout()
        head.setSpacing(6)
        lbl_title = QLabel(preset.display_title)
        lbl_title.setFont(title_font(self, 1.0))
        head.addWidget(lbl_title)
        self.lbl_rec = QLabel("★")
        self.lbl_rec.setStyleSheet("color: #f59e0b; font-weight: bold;")
        self.lbl_rec.hide()
        head.addWidget(self.lbl_rec)
        head.addStretch(1)
        self.lbl_count = SecondaryLabel()
        head.addWidget(self.lbl_count)
        self.body.addLayout(head)

        if preset.key == "custom":
            self.lbl_count.hide()
            row = QHBoxLayout()
            self.spin = QSpinBox()
            self.spin.setRange(50, 2000)
            self.spin.setSingleStep(25)
            self.spin.setValue(250)
            self.spin.valueChanged.connect(self._on_spin)
            row.addWidget(self.spin)
            self.lbl_duration = SecondaryLabel()
            row.addWidget(self.lbl_duration, 1)
            self.body.addLayout(row)
        else:
            self.spin = None
            self.lbl_duration = SecondaryLabel()
            self.body.addWidget(self.lbl_duration)

        self.lbl_desc = SecondaryLabel(preset.display_description)
        self.lbl_desc.setWordWrap(True)
        self.body.addWidget(self.lbl_desc)
        self.body.addStretch(1)
        self.refresh_duration()

    def set_recommended(self, recommended: bool, target_title: str = "") -> None:
        self.lbl_rec.setVisible(recommended)
        if recommended and target_title:
            tip = translate("MonitorsPage", "Recommended for {target}").format(target=target_title)
        elif recommended:
            tip = translate("MonitorsPage", "Recommended for the selected purpose")
        else:
            tip = ""
        self.lbl_rec.setToolTip(tip)

    def patch_count(self) -> int:
        if self.spin is not None:
            return self.spin.value()
        return self.preset.patch_count or PATCH_STANDARD

    def set_patch_count(self, count: int) -> None:
        if self.spin is not None:
            self.spin.blockSignals(True)
            self.spin.setValue(count)
            self.spin.blockSignals(False)

    def _on_spin(self, _value: int) -> None:
        self.refresh_duration(self._last_workflow, self._last_instrument)
        self.clicked.emit()
        self.changed.emit()

    def refresh_duration(self, workflow: str = WORKFLOW_DDC, instrument_name: str = "") -> None:
        self._last_workflow = workflow
        self._last_instrument = instrument_name
        count = self.patch_count()
        minutes = estimate_duration_minutes(count, workflow, instrument_name)
        if self.spin is None:
            self.lbl_count.setText(translate("MonitorsPage", "{patches} patches").format(patches=num(count)))
            self.lbl_duration.setText(translate("MonitorsPage", "approx. {minutes} min").format(minutes=minutes))
        else:
            self.lbl_duration.setText(
                translate("MonitorsPage", "patches · approx. {minutes} min").format(minutes=minutes)
            )


class MonitorSelector(QWidget):
    """Step "Select display": arrangement + details of the selected display, or one card per display
    when the desktop positions are unknown. Shared by the simple and the expert page."""

    display_selected = Signal(str)
    inspect_requested = Signal(str)

    MIN_COLUMNS = 3  # a single display does not stretch over the full width

    def __init__(self, parent: QWidget | None = None, with_correction: bool = False) -> None:
        super().__init__(parent)
        self.displays: list[DisplayInfo] = []
        self.selected_connector = ""
        self.drift: set[str] = set()
        self.monitor_cards: list[MonitorCard] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # real desktop arrangement (like the KDE display settings); hidden if positions are unknown
        self.arrangement = DisplayArrangement()
        self.arrangement.selected.connect(self.display_selected)
        self.arrangement.hide()
        lay.addWidget(self.arrangement)
        self.detail = MonitorDetail()
        self.detail.inspect_requested.connect(self.inspect_requested)
        self.detail.hide()
        lay.addWidget(self.detail)
        self.monitor_grid = QGridLayout()
        self.monitor_grid.setSpacing(16)
        lay.addLayout(self.monitor_grid)
        self.empty_label = SecondaryLabel(translate("MonitorsPage", "Detecting displays…"))
        lay.addWidget(self.empty_label)
        # expert mode: correction picker; simple mode: only a note when a correction is set
        self.correction = CorrectionPicker(show_observer=True) if with_correction else None
        self.correction_note = SecondaryLabel()
        if self.correction is not None:
            self.correction.layout().setContentsMargins(4, 6, 4, 0)
            lay.addWidget(self.correction)
        else:
            self.correction_note.setContentsMargins(4, 4, 4, 0)
            lay.addWidget(self.correction_note)
        self.correction_note.hide()
        watch_screens(self._update_arrangement)

    def set_displays(self, displays: list[DisplayInfo], selected: str, drift: set[str] | None = None) -> None:
        for card in self.monitor_cards:
            self.monitor_grid.removeWidget(card)
            card.deleteLater()
        self.monitor_cards = []
        self.displays = displays
        self.drift = drift or set()
        if not self._arranged():
            for i, d in enumerate(displays):
                card = MonitorCard(d, drift=d.connector in self.drift)
                card.clicked.connect(lambda c=d.connector: self.display_selected.emit(c))
                card.inspect_requested.connect(self.inspect_requested)
                self.monitor_grid.addWidget(card, 0, i)
                self.monitor_cards.append(card)
            for col in range(max(self.MIN_COLUMNS, len(displays), self.monitor_grid.columnCount())):
                self.monitor_grid.setColumnStretch(col, 1)
        self.empty_label.setVisible(not displays)
        self.empty_label.setText(translate("MonitorsPage", "No displays detected."))
        self.set_selected(selected)
        self._update_arrangement()

    def set_selected(self, connector: str) -> None:
        self.selected_connector = connector
        for card in self.monitor_cards:
            card.setChecked(card.display.connector == connector)
        self.arrangement.set_current(connector)
        self._update_detail()
        self._update_correction()

    def selected_display(self) -> DisplayInfo | None:
        return next((d for d in self.displays if d.connector == self.selected_connector), None)

    def _update_correction(self) -> None:
        disp = self.selected_display()
        if self.correction is not None:
            self.correction.set_display(disp)
            return
        path = correction_for(disp)
        if path:
            obs = observer_for(disp)
            note = translate(
                "MonitorsPage", "Spectral correction: {name} (can be changed in expert mode)"
            ).format(name=Path(path).name)
            if obs != DEFAULT_OBSERVER:
                note += " · " + translate("MonitorsPage", "Observer: {observer}").format(
                    observer=observer_label(obs)
                )
            self.correction_note.setText(note)
        else:
            self.correction_note.setText("")
        self.correction_note.setVisible(bool(path))

    def _arranged(self) -> bool:
        """True if every detected display has a desktop position (otherwise: card view)."""
        return bool(self.displays) and len(arrangement_items(self.displays)) == len(self.displays)

    def _update_arrangement(self) -> None:
        arranged = self._arranged()
        if arranged == bool(self.monitor_cards) and self.displays:
            # the view type changed (e.g. hotplug): rebuild cards or drop them
            self.set_displays(self.displays, self.selected_connector, self.drift)
            return
        self.arrangement.setVisible(arranged)
        self.arrangement.set_items(arrangement_items(self.displays, self.drift) if arranged else [],
                                   self.selected_connector)
        self._update_detail()

    def _update_detail(self) -> None:
        disp = self.selected_display() if self._arranged() else None
        self.detail.set_display(disp, drift=disp is not None and disp.connector in self.drift)


class MonitorsSimplePage(QWidget):
    """Simple mode: four numbered steps (display, purpose, workflow, patch count) and start button."""

    display_selected = Signal(str)
    inspect_requested = Signal(str)
    start_requested = Signal(str, object)  # connector, CalibrationTarget
    batch_requested = Signal(str)          # connector

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.displays: list[DisplayInfo] = []
        self.selected_connector = ""
        self._busy = False
        self._sensor_hint = ""  # non-empty: measuring is impossible, explains why
        self._instrument_name = ""
        self._workflow = WORKFLOW_DDC
        self._workflow_user_chosen = False
        self._patch_preset_key = "high"
        self._patch_user_chosen = False

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
        self.selector = MonitorSelector()
        self.selector.display_selected.connect(self.display_selected)
        self.selector.inspect_requested.connect(self.inspect_requested)
        self.arrangement, self.detail = self.selector.arrangement, self.selector.detail
        lay.addWidget(self.selector)

        lay.addWidget(SectionHeader("2", translate("MonitorsPage", "Purpose")))
        target_grid = QGridLayout()
        target_grid.setSpacing(12)
        self.target_cards: list[TargetCard] = []
        for i, target in enumerate(TARGETS):
            card = TargetCard(target)
            card.clicked.connect(lambda c=card: self._select_target(c))
            card.changed.connect(self._update_summary)
            target_grid.addWidget(card, i // 4, i % 4)
            target_grid.setColumnStretch(i % 4, 1)
            self.target_cards.append(card)
        lay.addLayout(target_grid)

        lay.addWidget(SectionHeader("3", translate("MonitorsPage", "Workflow")))
        self.ddc_banner = MessageBanner(kind="warning")   # why hardware DDC/CI is not available on this display
        self.ddc_banner.hide()
        lay.addWidget(self.ddc_banner)
        wf_grid = QGridLayout()
        wf_grid.setSpacing(12)
        self.workflow_cards: dict[str, WorkflowCard] = {}
        workflows = (
            (
                WORKFLOW_DDC,
                translate("MonitorsPage", "Hardware Calibration + Profile"),
                translate("MonitorsPage", "DDC/CI · Default for external monitors"),
                translate("MonitorsPage", "Phase 1a contrast · Phase 1b whitepoint & luminance via DDC/CI · "
                          "Phase 2+3 ICC profile. Best greyscale accuracy without 8-bit banding."),
            ),
            (
                WORKFLOW_SOFTWARE,
                translate("MonitorsPage", "Software Calibration + Profile"),
                translate("MonitorsPage", "Notebooks & displays without DDC"),
                translate("MonitorsPage", "Phase 1s iterative greyscale & whitepoint calibration · "
                          "Phase 2+3 ICC profile with embedded calibration curves."),
            ),
            (
                WORKFLOW_PROFILE,
                translate("MonitorsPage", "Profile Only"),
                translate("MonitorsPage", "Characterise actual state"),
                translate("MonitorsPage", "Skips Phase 1. Display hardware and curves stay untouched; "
                          "Phase 2+3 measures and builds an ICC profile of the current state."),
            ),
        )
        for col, (key, title, badge, desc) in enumerate(workflows):
            wcard = WorkflowCard(key, title, badge, desc)
            wcard.clicked.connect(lambda k=key: self.set_workflow(k, user_chosen=True))
            wf_grid.addWidget(wcard, 0, col)
            wf_grid.setColumnStretch(col, 1)
            self.workflow_cards[key] = wcard
        lay.addLayout(wf_grid)

        lay.addWidget(SectionHeader("4", translate("MonitorsPage", "Patch count")))
        patch_grid = QGridLayout()
        patch_grid.setSpacing(12)
        self.patch_cards: dict[str, PatchPresetCard] = {}
        for col, preset in enumerate(PATCH_PRESETS):
            pcard = PatchPresetCard(preset)
            pcard.clicked.connect(lambda k=preset.key: self.set_patch_preset(k, user_chosen=True))
            pcard.changed.connect(self._update_summary)
            patch_grid.addWidget(pcard, 0, col)
            patch_grid.setColumnStretch(col, 1)
            self.patch_cards[preset.key] = pcard
        lay.addLayout(patch_grid)
        self.sensor_banner = MessageBanner(kind="information")
        self.sensor_banner.hide()
        lay.addWidget(self.sensor_banner)

        self.summary_title = QLabel()
        self.summary_title.setFont(title_font(self, 1.0))
        self.summary_title.setWordWrap(True)
        self.summary_text = SecondaryLabel()
        self.summary_text.setWordWrap(True)
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(24)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(self.summary_title)
        col.addWidget(self.summary_text)
        row.addLayout(col, 1)
        self.btn_start = QPushButton(QIcon.fromTheme("media-playback-start"),
                                     translate("MonitorsPage", "Start Full Calibration"))
        self.btn_start.setDefault(True)
        self.btn_start.setMinimumHeight(40)
        self.btn_start.clicked.connect(self._start)
        self.btn_batch = QPushButton(QIcon.fromTheme("media-playlist-repeat"),
                                     translate("MonitorsPage", "Several Targets…"))
        self.btn_batch.setToolTip(translate(
            "MonitorsPage", "Batch: calibrate several targets one after another with the sensor placed once"))
        self.btn_batch.setMinimumHeight(40)
        self.btn_batch.clicked.connect(lambda: self.batch_requested.emit(self.selected_connector))
        row.addWidget(self.btn_batch, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.btn_start, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(row)
        lay.addStretch(1)

        self.selected_target = self.target_cards[0]
        self.selected_target.setChecked(True)
        self._patch_preset_key = self.selected_target.base.recommended_preset
        self._sync_workflow_cards()
        self._sync_patch_cards()
        self._update_summary()

    # ------------------------------------------------------------------ public API

    @property
    def monitor_cards(self) -> list[MonitorCard]:
        return self.selector.monitor_cards

    def set_displays(self, displays: list[DisplayInfo], selected: str, drift: set[str] | None = None) -> None:
        self.displays = displays
        self.selected_connector = selected
        self.selector.set_displays(displays, selected, drift)
        self._auto_select_workflow()
        self._update_summary()

    def set_selected(self, connector: str) -> None:
        changed = connector != self.selected_connector
        self.selected_connector = connector
        self.selector.set_selected(connector)
        if changed:
            self._workflow_user_chosen = False
        self._auto_select_workflow()
        self._update_summary()

    def set_target_key(self, key: str) -> None:
        for card in self.target_cards:
            if card.base.key == key:
                self._select_target(card)

    def set_workflow(self, workflow: str, user_chosen: bool = False) -> None:
        if workflow not in self.workflow_cards:
            return
        if not self.workflow_cards[workflow].isEnabled():
            return
        self._workflow = workflow
        if user_chosen:
            self._workflow_user_chosen = True
        self._sync_workflow_cards()
        self._update_summary()

    def current_workflow(self) -> str:
        return self._workflow

    def set_patch_preset(self, key: str, user_chosen: bool = False) -> None:
        if key not in self.patch_cards:
            return
        self._patch_preset_key = key
        if user_chosen:
            self._patch_user_chosen = True
        self._sync_patch_cards()
        self._update_summary()

    def current_patch_count(self) -> int:
        card = self.patch_cards.get(self._patch_preset_key)
        return card.patch_count() if card is not None else PATCH_STANDARD

    def set_patch_count(self, count: int) -> None:
        key = preset_for_count(count)
        if key == "custom":
            self.patch_cards["custom"].set_patch_count(count)
        self.set_patch_preset(key, user_chosen=True)

    def current_target(self) -> CalibrationTarget:
        return self.selected_target.target().with_patches(self.current_patch_count())

    def targets(self) -> list[CalibrationTarget]:
        """All targets with the settings of their cards (D50, custom luminance) and patch count."""
        if self._patch_user_chosen:
            patches = self.current_patch_count()
            return [card.target().with_patches(patches) for card in self.target_cards]
        return [card.target() for card in self.target_cards]

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_summary()

    def set_sensor_hint(self, hint: str) -> None:
        """Empty when a sensor is ready; otherwise the reason why no calibration can start."""
        self._sensor_hint = hint
        self._update_summary()

    def set_instrument_name(self, name: str) -> None:
        self._instrument_name = name
        self._update_summary()

    # ------------------------------------------------------------------ internals

    def _selected_display(self) -> DisplayInfo | None:
        return next((d for d in self.displays if d.connector == self.selected_connector), None)

    def _select_target(self, card: TargetCard) -> None:
        self.selected_target = card
        for c in self.target_cards:
            c.setChecked(c is card)
        self._patch_preset_key = card.base.recommended_preset
        self._patch_user_chosen = False
        self._sync_patch_cards()
        self._update_summary()

    def _auto_select_workflow(self) -> None:
        disp = self._selected_display()
        problem = ddc_problem(disp) if disp is not None else ""
        ddc_card = self.workflow_cards[WORKFLOW_DDC]
        ddc_card.set_unavailable(
            translate("MonitorsPage", "Not available: display has no DDC/CI.") if problem else ""
        )
        if problem:
            if self._workflow == WORKFLOW_DDC:
                self._workflow = WORKFLOW_SOFTWARE
        elif not self._workflow_user_chosen:
            self._workflow = WORKFLOW_DDC
        self._sync_workflow_cards()

    def _sync_workflow_cards(self) -> None:
        for key, card in self.workflow_cards.items():
            card.setChecked(key == self._workflow)

    def _sync_patch_cards(self) -> None:
        rec_key = self.selected_target.base.recommended_preset if hasattr(self, "selected_target") else ""
        rec_title = self.selected_target.base.display_title if hasattr(self, "selected_target") else ""
        for key, card in self.patch_cards.items():
            card.setChecked(key == self._patch_preset_key)
            card.set_recommended(key == rec_key, rec_title)

    def _update_summary(self) -> None:
        disp = self._selected_display()
        t = self.current_target()
        for card in self.patch_cards.values():
            card.refresh_duration(self._workflow, self._instrument_name)

        if is_slow_sensor(self._instrument_name):
            self.sensor_banner.setText(translate(
                "MonitorsPage",
                "<b>Slow sensor detected ({sensor}).</b> Integration times on dark patches are longer; "
                "<i>Fast (79)</i> or <i>Standard (175)</i> is often sufficient.",
            ).format(sensor=self._instrument_name))
            self.sensor_banner.show()
        else:
            self.sensor_banner.hide()

        if disp is None:
            self.ddc_banner.hide()
            self.summary_title.setText(translate("MonitorsPage", "No display selected"))
            self.summary_text.setText("")
            self._set_start_enabled(False, False)
            return

        problem = ddc_problem(disp)
        self.ddc_banner.setText(f"{problem}<br>{manual_adjustment_note()}" if problem else "")
        self.ddc_banner.setVisible(bool(problem))

        if self._workflow == WORKFLOW_SOFTWARE:
            self.btn_start.setText(translate("MonitorsPage", "Start Software Calibration"))
        elif self._workflow == WORKFLOW_PROFILE:
            self.btn_start.setText(translate("MonitorsPage", "Measure Profile Only"))
        else:
            self.btn_start.setText(translate("MonitorsPage", "Start Full Calibration"))

        wf_labels = {
            WORKFLOW_DDC: translate("MonitorsPage", "Hardware + Profile (DDC/CI)"),
            WORKFLOW_SOFTWARE: translate("MonitorsPage", "Software + Profile"),
            WORKFLOW_PROFILE: translate("MonitorsPage", "Profile Only"),
        }
        self.summary_title.setText(
            f"{disp.model} ({disp.connector}) → {t.display_title} · {wf_labels.get(self._workflow, '')}"
        )

        if self._workflow == WORKFLOW_DDC and problem:
            self.summary_text.setText(translate("MonitorsPage", "The full calibration needs DDC/CI."))
            self._set_start_enabled(False, False)
            return
        if self._sensor_hint:
            self.summary_text.setText(self._sensor_hint)
            self._set_start_enabled(False, False)
            return

        minutes = estimate_duration_minutes(t.patch_count, self._workflow, self._instrument_name)
        if self._workflow == WORKFLOW_SOFTWARE:
            self.summary_text.setText(translate(
                "MonitorsPage",
                "Place the sensor once in the centre. Software calibration and profile ({patches} "
                "patches) then run automatically, approx. {minutes} minutes.",
            ).format(patches=num(t.patch_count), minutes=minutes))
        elif self._workflow == WORKFLOW_PROFILE:
            self.summary_text.setText(translate(
                "MonitorsPage",
                "Place the sensor once in the centre. Patch measurement ({patches} patches) and profile "
                "computation run automatically, approx. {minutes} minutes.",
            ).format(patches=num(t.patch_count), minutes=minutes))
        else:
            self.summary_text.setText(translate(
                "MonitorsPage",
                "Place the sensor once in the centre. Contrast, whitepoint, luminance and profile ({patches} "
                "patches) then run automatically, approx. {minutes} minutes.",
            ).format(patches=num(t.patch_count), minutes=minutes))
        self._set_start_enabled(
            not self._busy,
            not self._busy and not problem and self._workflow == WORKFLOW_DDC,
        )

    def _set_start_enabled(self, start_enabled: bool, batch_enabled: bool | None = None) -> None:
        self.btn_start.setEnabled(start_enabled)
        self.btn_batch.setEnabled(start_enabled if batch_enabled is None else batch_enabled)

    def _start(self) -> None:
        if self._selected_display() is not None:
            self.start_requested.emit(self.selected_connector, self.current_target())


