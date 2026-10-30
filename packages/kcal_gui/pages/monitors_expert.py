"""Monitors page, expert mode (mockup 1c): outputs + live DDC | parameters | single phases, log below."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kcal_argyll.profile_pipeline import ProfileConfig
from kcal_core.i18n import translate
from kcal_core.models import DisplayInfo
from kcal_core.targets import TARGETS, CalibrationTarget, TONE_BT1886, TONE_GAMMA, TONE_LSTAR, TONE_SRGB, cct_to_xy
from kcal_ddc.contrast_optimizer import ContrastOptimizationConfig
from kcal_gui.pages.monitors_simple import MonitorSelector
from kcal_gui.widgets import LogPanel, SecondaryLabel, SectionHeader, SegmentedControl

PHASE_TEST, PHASE_1A, PHASE_1B, PHASE_23, PHASE_ALL = "test", "1a", "1b", "23", "all"

WHITEPOINTS = ((6504, "D65 · 6504 K"), (5003, "D50 · 5003 K"), (5500, "D55 · 5500 K"), (5800, "5800 K"))
TONE_CURVES = ((TONE_GAMMA, 2.2), (TONE_SRGB, 2.2), (TONE_BT1886, 2.4), (TONE_LSTAR, 2.2))
QUALITIES = ("m", "h", "u")


@dataclass
class ExpertParameters:
    contrast: ContrastOptimizationConfig
    luminance: float
    whitepoint_xy: tuple[float, float]
    patch_count: int
    profile_quality: str
    profile_type: str
    gamma: float

    def profile_config(self, display: DisplayInfo) -> ProfileConfig:
        return ProfileConfig(
            monitor_name=f"{display.connector}_{display.model}",
            patch_count=self.patch_count,
            gamma=self.gamma,
            profile_quality=self.profile_quality,
            profile_type=self.profile_type,
        )


class MonitorsExpertPage(QWidget):
    display_selected = Signal(str)
    inspect_requested = Signal(str)
    phase_requested = Signal(str)  # PHASE_*

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.displays: list[DisplayInfo] = []
        self._busy = False
        self._sensor_hint = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        self.vsplit = QSplitter(Qt.Orientation.Vertical)
        lay.addWidget(self.vsplit)
        # same three steps as the simple mode, but with all parameters and the single phases
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        steps = QVBoxLayout(content)
        steps.setContentsMargins(16, 8, 16, 16)
        steps.addWidget(SectionHeader("1", translate("MonitorsPage", "Select display")))
        self.selector = MonitorSelector(with_correction=True)
        self.selector.display_selected.connect(self.display_selected)
        self.selector.inspect_requested.connect(self.inspect_requested)
        self.arrangement = self.selector.arrangement
        steps.addWidget(self.selector)
        steps.addWidget(SectionHeader("2", translate("ExpertPage", "Parameters")))
        steps.addWidget(self._build_parameters())
        steps.addWidget(SectionHeader("3", translate("ExpertPage", "Calibration")))
        steps.addWidget(self._build_phases())
        steps.addStretch(1)
        self.vsplit.addWidget(scroll)
        self.log = LogPanel()
        self.log.layout().setContentsMargins(16, 0, 16, 0)  # directly in the splitter so collapsing frees space
        self.vsplit.addWidget(self.log)
        self.log.setExpanded(False)  # default; restore_settings applies the saved state
        self.vsplit.setStretchFactor(0, 3)
        self.vsplit.setStretchFactor(1, 1)
        self.selected_connector = ""
        self.apply_target(TARGETS[0])

    # ------------------------------------------------------------------ columns

    def _build_parameters(self) -> QWidget:
        inner = QWidget()
        inner.setMaximumWidth(1240)  # keep the fields compact on very wide windows
        # two columns, label above field (mockup 1c); wide fields span both columns
        grid = QGridLayout(inner)
        grid.setContentsMargins(4, 0, 4, 0)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)
        columns = 4
        for c in range(columns):
            grid.setColumnStretch(c, 1)
        self._grid_pos = 0

        def field(label: str, widget_or_layout, span: int = 1) -> None:  # noqa: ANN001
            if self._grid_pos % columns + span > columns:  # does not fit into the row: next row
                self._grid_pos += columns - self._grid_pos % columns
            row, col = divmod(self._grid_pos, columns)
            box = QVBoxLayout()
            box.setSpacing(4)
            caption = SecondaryLabel(label)
            box.addWidget(caption)
            if isinstance(widget_or_layout, QWidget):
                caption.setBuddy(widget_or_layout)
                box.addWidget(widget_or_layout)
            else:
                box.addLayout(widget_or_layout)
            grid.addLayout(box, row, col, 1, span)
            self._grid_pos += span

        self.combo_target = QComboBox()
        for t in TARGETS:
            self.combo_target.addItem(t.display_title, t.key)
        self.combo_target.activated.connect(lambda i: self.apply_target(TARGETS[i]))
        field(translate("ExpertPage", "Target template"), self.combo_target, span=2)

        self.spin_luminance = QDoubleSpinBox()
        self.spin_luminance.setRange(60.0, 400.0)
        self.spin_luminance.setDecimals(0)
        self.spin_luminance.setSuffix(" cd/m²")
        field(translate("ExpertPage", "Target luminance"), self.spin_luminance)

        self.combo_wp = QComboBox()
        for cct, label in WHITEPOINTS:
            self.combo_wp.addItem(label, cct)
        field(translate("ExpertPage", "Whitepoint"), self.combo_wp)

        self.combo_tone = QComboBox()
        for key, gamma in TONE_CURVES:
            label = CalibrationTarget("", "", 0.0, 6504, tone_curve=key, gamma=gamma).tone_label
            self.combo_tone.addItem(label, (key, gamma))
        self.combo_tone.setToolTip(translate(
            "ExpertPage", "Reference curve for the profile check. Calibration curves are not generated yet."
        ))
        field(translate("ExpertPage", "Tone curve"), self.combo_tone)

        self.seg_type = SegmentedControl([translate("ExpertPage", "cLUT + Matrix"), translate("ExpertPage", "Matrix")],
                                         expanding=True)
        field(translate("ExpertPage", "Profile type"), self.seg_type)

        rng = QHBoxLayout()
        self.spin_min_c = QSpinBox()
        self.spin_min_c.setRange(20, 80)
        self.spin_min_c.setPrefix(translate("ExpertPage", "Min "))
        self.spin_min_c.setSuffix(" %")
        self.spin_max_c = QSpinBox()
        self.spin_max_c.setRange(50, 100)
        self.spin_max_c.setPrefix(translate("ExpertPage", "Max "))
        self.spin_max_c.setSuffix(" %")
        rng.addWidget(self.spin_min_c)
        rng.addWidget(self.spin_max_c)
        field(translate("ExpertPage", "Contrast search range"), rng)

        thr = QHBoxLayout()
        self.spin_duv = QDoubleSpinBox()
        self.spin_duv.setRange(0.0005, 0.0100)
        self.spin_duv.setDecimals(4)
        self.spin_duv.setSingleStep(0.0005)
        self.spin_duv.setPrefix("Δu′v′ ")
        self.spin_step = QDoubleSpinBox()
        self.spin_step.setRange(0.30, 0.95)
        self.spin_step.setDecimals(2)
        self.spin_step.setSingleStep(0.02)
        self.spin_step.setPrefix(translate("ExpertPage", "ΔY ratio "))
        self.spin_step.setToolTip(translate(
            "ExpertPage", "Minimum share of the ideal luminance step between 248 and 255 (highlight compression)."
        ))
        thr.addWidget(self.spin_duv)
        thr.addWidget(self.spin_step)
        field(translate("ExpertPage", "Clipping thresholds"), thr)

        patches = QHBoxLayout()
        self.slider_patches = QSlider(Qt.Orientation.Horizontal)
        self.slider_patches.setRange(50, 2000)
        self.slider_patches.setSingleStep(25)
        self.slider_patches.setPageStep(100)
        self.spin_patches = QSpinBox()
        self.spin_patches.setRange(50, 2000)
        self.spin_patches.setSingleStep(25)
        self.slider_patches.valueChanged.connect(self.spin_patches.setValue)
        self.spin_patches.valueChanged.connect(self.slider_patches.setValue)
        patches.addWidget(self.slider_patches, 1)
        patches.addWidget(self.spin_patches)
        field(translate("ExpertPage", "Patch count (targen)"), patches, span=2)

        self.seg_quality = SegmentedControl(["Medium -qm", "High -qh", "Ultra -qu"], expanding=True)
        field(translate("ExpertPage", "3D-LUT quality"), self.seg_quality, span=2)

        defaults = ContrastOptimizationConfig()
        self.spin_min_c.setValue(defaults.min_contrast)
        self.spin_max_c.setValue(defaults.max_contrast)
        self.spin_duv.setValue(defaults.max_delta_uv)
        self.spin_step.setValue(defaults.min_relative_step_ratio)
        self.seg_quality.setCurrentIndex(1)
        return inner

    def _build_phases(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.phase_buttons: list[QToolButton] = []
        for key, title, sub in (
            (PHASE_TEST, translate("ExpertPage", "Test patch window"),
             translate("ExpertPage", "Check placement on the display")),
            (PHASE_1A, translate("ExpertPage", "Phase 1a · Contrast binary search"),
             translate("ExpertPage", "6–7 measurements · approx. 20 s")),
            (PHASE_1B, translate("ExpertPage", "Phase 1b · Whitepoint & luminance"),
             translate("ExpertPage", "RGB gains + backlight via DDC")),
            (PHASE_23, translate("ExpertPage", "Phase 2+3 · Profiling"),
             translate("ExpertPage", "DDC values stay unchanged")),
        ):
            btn = QToolButton()
            btn.setText(f"{title}\n{sub}".replace("&", "&&"))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            btn.setMinimumHeight(52)
            btn.clicked.connect(lambda _=False, k=key: self.phase_requested.emit(k))
            row.addWidget(btn, 1)
            self.phase_buttons.append(btn)
        self.phase_buttons[0].setCheckable(True)   # the test window is toggled: a second click closes it
        row.addSpacing(16)
        self.btn_all = QPushButton(QIcon.fromTheme("media-playback-start"), translate("ExpertPage", "Run All Phases"))
        self.btn_all.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.btn_all.setMinimumHeight(52)  # same height as the phase buttons
        self.btn_all.clicked.connect(lambda: self.phase_requested.emit(PHASE_ALL))
        row.addWidget(self.btn_all)
        return box

    # ------------------------------------------------------------------ public API

    def set_displays(self, displays: list[DisplayInfo], selected: str, drift: set[str] | None = None) -> None:
        self.displays = displays
        self.selector.set_displays(displays, selected, drift)
        self.set_selected(selected)

    def set_selected(self, connector: str) -> None:
        self.selected_connector = connector
        self.selector.set_selected(connector)
        self._update_enabled()

    def apply_target(self, target: CalibrationTarget) -> None:
        idx = self.combo_target.findData(target.key)
        self.combo_target.setCurrentIndex(max(0, idx))
        self.spin_luminance.setValue(target.luminance)
        wp_idx = self.combo_wp.findData(target.cct)
        if wp_idx < 0:
            self.combo_wp.addItem(f"{target.cct} K", target.cct)
            wp_idx = self.combo_wp.count() - 1
        self.combo_wp.setCurrentIndex(wp_idx)
        for i in range(self.combo_tone.count()):
            key, gamma = self.combo_tone.itemData(i)
            if key == target.tone_curve and abs(gamma - target.gamma) < 0.01:
                self.combo_tone.setCurrentIndex(i)
        self.spin_patches.setValue(target.patch_count)

    def parameters(self) -> ExpertParameters:
        _tone, gamma = self.combo_tone.currentData()
        contrast = ContrastOptimizationConfig(
            min_contrast=self.spin_min_c.value(),
            max_contrast=self.spin_max_c.value(),
            max_delta_uv=self.spin_duv.value(),
            min_relative_step_ratio=self.spin_step.value(),
        )
        return ExpertParameters(
            contrast=contrast,
            luminance=self.spin_luminance.value(),
            whitepoint_xy=cct_to_xy(int(self.combo_wp.currentData())),
            patch_count=self.spin_patches.value(),
            profile_quality=QUALITIES[max(0, self.seg_quality.currentIndex())],
            profile_type="X" if self.seg_type.currentIndex() == 0 else "M",
            gamma=gamma,
        )

    def current_target(self) -> CalibrationTarget:
        """The parameter set as a calibration target (for the inspector's target values)."""
        tone, gamma = self.combo_tone.currentData()
        base = TARGETS[max(0, self.combo_target.currentIndex())]
        return CalibrationTarget(base.key, base.title, self.spin_luminance.value(), int(self.combo_wp.currentData()),
                                 tone_curve=tone, gamma=gamma, patch_count=self.spin_patches.value())

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_enabled()

    def set_sensor_hint(self, hint: str) -> None:
        """Empty when a sensor is ready; otherwise measuring phases are disabled with `hint` as tooltip."""
        self._sensor_hint = hint
        for btn in (*self.phase_buttons[1:], self.btn_all):
            btn.setToolTip(hint)
        self._update_enabled()

    def _update_enabled(self) -> None:
        disp = next((d for d in self.displays if d.connector == self.selected_connector), None)
        has_disp = disp is not None and not self._busy
        can_measure = has_disp and not self._sensor_hint
        has_ddc = can_measure and disp.i2c_bus is not None
        self.phase_buttons[0].setEnabled(has_disp)
        self.phase_buttons[1].setEnabled(has_ddc)
        self.phase_buttons[2].setEnabled(has_ddc)
        self.phase_buttons[3].setEnabled(can_measure)
        self.btn_all.setEnabled(has_ddc)
        self.selector.setEnabled(not self._busy)

    # ------------------------------------------------------------------ settings

    def save_settings(self, st: QSettings) -> None:
        st.setValue("expert/steps_vsplit", self.vsplit.saveState())
        st.setValue("expert/log_expanded", self.log.isExpanded())
        p = self.parameters()
        st.setValue("params/target", self.combo_target.currentData())
        st.setValue("params/luminance", p.luminance)
        st.setValue("params/whitepoint_cct", self.combo_wp.currentData())
        st.setValue("params/tone_index", self.combo_tone.currentIndex())
        st.setValue("params/contrast_min", p.contrast.min_contrast)
        st.setValue("params/contrast_max", p.contrast.max_contrast)
        st.setValue("params/max_delta_uv", p.contrast.max_delta_uv)
        st.setValue("params/min_step_ratio", p.contrast.min_relative_step_ratio)
        st.setValue("params/patches", p.patch_count)
        st.setValue("params/quality", self.seg_quality.currentIndex())
        st.setValue("params/profile_type", self.seg_type.currentIndex())

    def restore_settings(self, st: QSettings) -> None:
        state = st.value("expert/steps_vsplit")  # new key: the former layout's state does not fit
        if state is not None:
            self.vsplit.restoreState(state)
        self.log.setExpanded(str(st.value("expert/log_expanded", "false")).lower() == "true")
        target_key = st.value("params/target")
        if target_key:
            self.combo_target.setCurrentIndex(max(0, self.combo_target.findData(target_key)))
        self.spin_luminance.setValue(float(st.value("params/luminance", self.spin_luminance.value())))
        cct = int(st.value("params/whitepoint_cct", self.combo_wp.currentData()))
        self.combo_wp.setCurrentIndex(max(0, self.combo_wp.findData(cct)))
        self.combo_tone.setCurrentIndex(int(st.value("params/tone_index", self.combo_tone.currentIndex())))
        self.spin_min_c.setValue(int(st.value("params/contrast_min", self.spin_min_c.value())))
        self.spin_max_c.setValue(int(st.value("params/contrast_max", self.spin_max_c.value())))
        self.spin_duv.setValue(float(st.value("params/max_delta_uv", self.spin_duv.value())))
        self.spin_step.setValue(float(st.value("params/min_step_ratio", self.spin_step.value())))
        self.spin_patches.setValue(int(st.value("params/patches", self.spin_patches.value())))
        self.seg_quality.setCurrentIndex(int(st.value("params/quality", 1)))
        self.seg_type.setCurrentIndex(int(st.value("params/profile_type", 0)))
