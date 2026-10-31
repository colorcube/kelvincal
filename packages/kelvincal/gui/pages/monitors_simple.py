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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kelvincal.core.i18n import translate
from kelvincal.core.models import DisplayInfo
from kelvincal.core.targets import TARGETS, CalibrationTarget
from kelvincal.gui.fmt import cdm2, num
from kelvincal.gui.pages.correction import CorrectionPicker, correction_for
from kelvincal.gui.screens import screen_geometries
from kelvincal.gui.widgets import (
    ArrangedDisplay,
    Card,
    DdcBars,
    DisplayArrangement,
    ElidedLabel,
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
                                     warning=d.connector in (drift or set()), enabled=d.i2c_bus is not None))
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
        self.body.addWidget(ElidedLabel(f"SN {display.serial or '–'} · {bus}", mono=True, secondary=True,
                                        mode=Qt.TextElideMode.ElideRight))
        self.body.addSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        rows = ddc_rows(display)
        for row, (label, value) in enumerate(rows):
            grid.addWidget(SecondaryLabel(label), row, 0)
            grid.addWidget(ElidedLabel(value, mono=True), row, 1)
        grid.addWidget(SecondaryLabel(translate("MonitorsPage", "ICC active")), len(rows), 0)
        icc_row = QHBoxLayout()
        icc_row.setSpacing(6)
        icc_row.addWidget(ElidedLabel(icc_label(display), mono=True), 1)
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
        self.ident = ElidedLabel(mono=True, secondary=True, mode=Qt.TextElideMode.ElideRight)
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
            "MonitorsPage", "No DDC/CI: contrast, whitepoint and luminance cannot be set in hardware."))
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
        self.icc = ElidedLabel(mono=True)
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
            value = ElidedLabel(mono=True, mode=Qt.TextElideMode.ElideRight)
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
        self.correction = CorrectionPicker() if with_correction else None
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
        self.correction_note.setText(translate(
            "MonitorsPage", "Spectral correction: {name} (can be changed in expert mode)").format(
            name=Path(path).name) if path else "")
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
    """Simple mode: three numbered steps, one button."""

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

        lay.addWidget(SectionHeader("3", translate("MonitorsPage", "Calibration")))
        self.summary_title = QLabel()
        self.summary_title.setFont(title_font(self, 1.0))
        self.summary_title.setWordWrap(True)
        self.summary_text = SecondaryLabel()
        self.summary_text.setWordWrap(True)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
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
        self._update_summary()

    # ------------------------------------------------------------------ public API

    @property
    def monitor_cards(self) -> list[MonitorCard]:
        return self.selector.monitor_cards

    def set_displays(self, displays: list[DisplayInfo], selected: str, drift: set[str] | None = None) -> None:
        self.displays = displays
        self.selected_connector = selected
        self.selector.set_displays(displays, selected, drift)
        self._update_summary()

    def set_selected(self, connector: str) -> None:
        self.selected_connector = connector
        self.selector.set_selected(connector)
        self._update_summary()

    def set_target_key(self, key: str) -> None:
        for card in self.target_cards:
            if card.base.key == key:
                self._select_target(card)

    def current_target(self) -> CalibrationTarget:
        return self.selected_target.target()

    def targets(self) -> list[CalibrationTarget]:
        """All targets with the settings of their cards (D50, custom luminance)."""
        return [card.target() for card in self.target_cards]

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_summary()

    def set_sensor_hint(self, hint: str) -> None:
        """Empty when a sensor is ready; otherwise the reason why no calibration can start."""
        self._sensor_hint = hint
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
            self._set_start_enabled(False)
            return
        self.summary_title.setText(f"{disp.model} ({disp.connector}) → {t.display_title}")
        if disp.i2c_bus is None:
            self.summary_text.setText(translate(
                "MonitorsPage",
                "This display has no DDC/CI. Contrast, whitepoint and luminance cannot be set in hardware.",
            ))
            self._set_start_enabled(False)
            return
        if self._sensor_hint:
            self.summary_text.setText(self._sensor_hint)
            self._set_start_enabled(False)
            return
        self.summary_text.setText(translate(
            "MonitorsPage",
            "Place the sensor once in the centre. Contrast, whitepoint, luminance and profile then run "
            "automatically, approx. {minutes} minutes.",
        ).format(minutes=t.estimated_minutes()))
        self._set_start_enabled(not self._busy)

    def _set_start_enabled(self, enabled: bool) -> None:
        self.btn_start.setEnabled(enabled)
        self.btn_batch.setEnabled(enabled)

    def _start(self) -> None:
        if self._selected_display() is not None:
            self.start_requested.emit(self.selected_connector, self.current_target())
