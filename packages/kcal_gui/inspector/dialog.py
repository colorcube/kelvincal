"""Profile inspector & live preview (mockup 1g): KPIs, kink check, curve/gamut views, A/B preview, saving."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from kcal_argyll.profile_inspector import (
    REFERENCE_GAMUTS,
    ProfileInspection,
    inspect_profile,
    read_profile_summary,
    xy_to_uv,
)
from kcal_argyll.profile_pipeline import StagedProfile
from kcal_core.compositor.base import CompositorBackend
from kcal_core.i18n import translate
from kcal_core.models import D65_X, D65_Y, DisplayInfo
from kcal_core.paths import user_icc_dir
from kcal_core.targets import CalibrationTarget
from kcal_gui.fmt import cdm2, num
from kcal_gui.inspector.verification_page import VerificationPage, VerifyStarter
from kcal_gui.workers import TaskThread
from kcal_gui.inspector.plots import CHANNELS, VIEW_GAMMA, VIEW_KNICK, VIEW_TRC, CurvePlot, GamutPlot
from kcal_gui.widgets import Card, ElidedLabel, MessageBanner, SecondaryLabel, SegmentedControl, mono_font, title_font
from kcal_gui.widgets.run_views import ThinBar

PREVIEW_NEW, PREVIEW_PREVIOUS, PREVIEW_UNCALIBRATED = range(3)
DdcValues = tuple[int, int, int, int, int]  # brightness, contrast, red, green, blue gain
TAB_TRC, TAB_GAMMA, TAB_KNICK, TAB_GAMUT = range(4)


class KpiItem(QWidget):
    """Caption, large value, small note (one cell of the KPI strip)."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(SecondaryLabel(caption))
        self.value = QLabel("–")
        font = mono_font()
        font.setPointSizeF(self.font().pointSizeF() * 1.45)
        self.value.setFont(font)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.note = SecondaryLabel()
        lay.addWidget(self.value)
        lay.addWidget(self.note)

    def set(self, value: str, note: str = "") -> None:
        self.value.setText(value)
        self.note.setText(note)


class PreviewCard(Card):
    """One A/B preview option with its keyboard shortcut."""

    def __init__(self, title: str, sub: str, key: str, parent: QWidget | None = None) -> None:
        super().__init__(selectable=True, parent=parent)
        self.body.setContentsMargins(10, 6, 10, 6)
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(QLabel(title))
        self.sub = ElidedLabel(sub, mono=True, secondary=True)
        col.addWidget(self.sub)
        row.addLayout(col, 1)
        key_label = SecondaryLabel(key, mono=True)
        key_label.setToolTip(translate("Inspector", "Key {key}").format(key=key))
        row.addWidget(key_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(row)


class InspectorDialog(QDialog):
    """Inspects an ICC profile; for a freshly staged profile it also offers saving and A/B preview."""

    def __init__(
        self,
        inspection: ProfileInspection,
        connector: str | None = None,
        compositor: CompositorBackend | None = None,
        staged_profile: StagedProfile | None = None,
        previous_icc_path: str | None = None,
        previous_source: str = "sRGB",
        display: DisplayInfo | None = None,
        target: CalibrationTarget | None = None,
        presets: list[str] | None = None,
        preset_preselect: str = "",
        verify_starter: VerifyStarter | None = None,
        ddc_previous: DdcValues | None = None,
        ddc_new: DdcValues | None = None,
        ddc_apply: Callable[[DdcValues], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.inspection = inspection
        self.connector = connector
        self.compositor = compositor
        self.staged_profile = staged_profile
        self.previous_icc_path = previous_icc_path
        self.previous_source = previous_source
        self.display = display
        self.target = target
        self.presets = list(presets or [])
        self.verify_starter = verify_starter
        # Hardware state for the A/B preview: (brightness, contrast, red, green, blue) before and after the
        # calibration. ddc_apply blocks (ddcutil) and is run in a worker thread while previewing.
        self.ddc_previous, self.ddc_new, self.ddc_apply = ddc_previous, ddc_new, ddc_apply
        self._ddc_current = ddc_new
        self._ddc_task: TaskThread | None = None
        self.saved_profile_path: Path | None = None
        self.preset_to_update: str | None = None
        # a staged profile is already active; an inspected file is only shown until previewed
        self.preview_mode = PREVIEW_NEW if staged_profile is not None else PREVIEW_PREVIOUS

        self.setWindowTitle(translate("Inspector", "Profile Inspector – KelvinCal"))
        self.resize(1240, 880)
        self._build_ui(preset_preselect)
        self._refresh()

    # ------------------------------------------------------------------ layout

    def _build_ui(self, preset_preselect: str) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.lbl_title = QLabel()
        self.lbl_title.setFont(title_font(self, 1.3))
        self.lbl_sub = SecondaryLabel(mono=True)
        titles.addWidget(self.lbl_title)
        titles.addWidget(self.lbl_sub)
        head.addLayout(titles, 1)
        self.seg_page = SegmentedControl([translate("Inspector", "Profile"), translate("Inspector", "Verification")])
        head.addWidget(self.seg_page, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)

        lay.addWidget(self._build_kpis())
        self.banner = MessageBanner()
        lay.addWidget(self.banner)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_profile_page())
        self.verification = VerificationPage(self.verify_starter, self.active_profile_label)
        self.pages.addWidget(self.verification)
        self.seg_page.currentChanged.connect(self.pages.setCurrentIndex)
        lay.addWidget(self.pages, 1)
        if self.staged_profile is not None and preset_preselect in self.presets:
            self.chk_preset.setChecked(True)
            self.combo_preset.setCurrentText(preset_preselect)

    def _build_kpis(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(28)
        self.kpi_white = KpiItem(translate("Inspector", "White Y max"))
        self.kpi_black = KpiItem(translate("Inspector", "Black Y min"))
        self.kpi_contrast = KpiItem(translate("Inspector", "Contrast"))
        self.kpi_wp = KpiItem(translate("Inspector", "Whitepoint"))
        self.kpi_gamma = KpiItem(translate("Inspector", "Effective gamma"))
        for item in (self.kpi_white, self.kpi_black, self.kpi_contrast, self.kpi_wp, self.kpi_gamma):
            row.addWidget(item)
        cov = QVBoxLayout()
        cov.setSpacing(2)
        cov.addWidget(SecondaryLabel(translate("Inspector", "Coverage (2D, u′v′)")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(1)
        self.cov_bars: dict[str, tuple[ThinBar, QLabel]] = {}
        for i, name in enumerate(REFERENCE_GAMUTS):
            bar = ThinBar()
            bar.setMinimumWidth(80)
            value = QLabel("–")
            value.setFont(mono_font())
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(SecondaryLabel(name), i, 0)
            grid.addWidget(bar, i, 1)
            grid.addWidget(value, i, 2)
            self.cov_bars[name] = (bar, value)
        grid.setColumnStretch(1, 1)
        cov.addLayout(grid)
        row.addLayout(cov, 1)
        card.body.addLayout(row)
        return card

    def _build_profile_page(self) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        left = Card()
        self.tabs = QTabBar()
        self.tabs.setDocumentMode(True)
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        for text in (translate("Inspector", "Tone Curves"), translate("Inspector", "Gamma γ(x)"),
                     translate("Inspector", "Kink Magnifier Δ%"), translate("Inspector", "Gamut")):
            self.tabs.addTab(text)
        self.tabs.currentChanged.connect(self._on_tab)
        left.body.addWidget(self.tabs)

        options = QHBoxLayout()
        self.curve_options = QWidget()
        co = QHBoxLayout(self.curve_options)
        co.setContentsMargins(0, 0, 0, 0)
        self.chk_channels: dict[str, QCheckBox] = {}
        for key, text in zip(CHANNELS, (translate("Inspector", "Red"), translate("Inspector", "Green"),
                                        translate("Inspector", "Blue"))):
            chk = QCheckBox(text)
            chk.setChecked(True)
            chk.toggled.connect(self._on_options)
            co.addWidget(chk)
            self.chk_channels[key] = chk
        self.chk_points = QCheckBox(translate("Inspector", "Measured points"))
        self.chk_ref = QCheckBox(translate("Inspector", "Reference"))
        for chk in (self.chk_points, self.chk_ref):
            chk.setChecked(True)
            chk.toggled.connect(self._on_options)
            co.addWidget(chk)
        co.addStretch(1)
        self.seg_lstar = SegmentedControl(["Y %", "L*"])
        self.seg_lstar.currentChanged.connect(self._on_options)
        co.addWidget(self.seg_lstar)

        self.gamut_options = QWidget()
        go = QHBoxLayout(self.gamut_options)
        go.setContentsMargins(0, 0, 0, 0)
        self.chk_display = QCheckBox(translate("Inspector", "Display"))
        self.chk_display.setChecked(True)
        self.chk_display.toggled.connect(self._on_options)
        go.addWidget(self.chk_display)
        self.chk_refs: dict[str, QCheckBox] = {}
        for name in REFERENCE_GAMUTS:
            chk = QCheckBox(name)
            chk.setChecked(name in ("sRGB", "DCI-P3"))
            chk.toggled.connect(self._on_options)
            go.addWidget(chk)
            self.chk_refs[name] = chk
        go.addStretch(1)
        self.seg_cie = SegmentedControl(["CIE 1976 u′v′", "CIE 1931 xy"])
        self.seg_cie.currentChanged.connect(self._on_options)
        go.addWidget(self.seg_cie)
        # one stack for both option rows: its width is the larger of the two from the start, so
        # switching views never resizes the plot or the dialog
        self.option_stack = QStackedWidget()
        self.option_stack.addWidget(self.curve_options)
        self.option_stack.addWidget(self.gamut_options)
        self.option_stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        options.addWidget(self.option_stack)
        left.body.addLayout(options)

        self.plots = QStackedWidget()
        self.curve_plot = CurvePlot(self.inspection)
        self.gamut_plot = GamutPlot(self.inspection)
        for plot in (self.curve_plot, self.gamut_plot):
            plot.readout_changed.connect(self._on_readout)
            self.plots.addWidget(plot)
        left.body.addWidget(self.plots, 1)
        self.readout = SecondaryLabel(mono=True)
        # live text: must not widen the dialog while the mouse moves or the view changes
        self.readout.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        left.body.addWidget(self.readout)
        row.addWidget(left, 1)

        right = QVBoxLayout()
        right.setSpacing(12)
        if self.compositor is not None and self.connector:
            right.addWidget(self._build_preview())
        if self.staged_profile is not None:
            right.addWidget(self._build_save())
        right.addStretch(1)
        right.addLayout(self._build_buttons())
        side = QWidget()
        side.setLayout(right)
        side.setFixedWidth(320)
        row.addWidget(side)
        self._on_tab(TAB_TRC)
        return page

    def _build_preview(self) -> QWidget:
        card = Card()
        heading = QLabel(translate("Inspector", "Live preview on {connector}").format(connector=self.connector))
        heading.setFont(title_font(self, 1.0))
        card.body.addWidget(heading)
        prev_name = Path(self.previous_icc_path).name if self.previous_icc_path and self.previous_source == "ICC" \
            else translate("Inspector", "{source} · no ICC").format(source=self.previous_source or "sRGB")
        if self.staged_profile is not None:
            first = translate("Inspector", "New profile")
            second = translate("Inspector", "Previous profile")
        else:
            first = translate("Inspector", "This profile")
            second = translate("Inspector", "Current profile")
        options = (
            (first, self.inspection.profile_path.name),
            (second, prev_name),
            (translate("Inspector", "Uncalibrated"), translate("Inspector", "sRGB · no ICC")),
        )
        self.preview_cards: list[PreviewCard] = []
        for i, (title, sub) in enumerate(options):
            pc = PreviewCard(title, sub, str(i + 1))
            pc.clicked.connect(lambda i=i: self.set_preview(i))
            card.body.addWidget(pc)
            self.preview_cards.append(pc)
            QShortcut(QKeySequence(str(i + 1)), self, activated=lambda i=i: self.set_preview(i))
        text = translate(
            "Inspector", "Visual A/B comparison: switches the profile on the real desktop of {connector}, e.g. to "
            "judge photos or gradients. The graphs always show the inspected profile."
        ).format(connector=self.connector)
        if self._ddc_switching():
            text += " " + translate(
                "Inspector", "1 and 3 use the display settings (DDC) from the calibration, 2 those from before.")
        hint = SecondaryLabel(text)
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        self.ddc_status = SecondaryLabel(mono=False)
        self.ddc_status.setWordWrap(True)
        self.ddc_status.setText(self._ddc_text())
        card.body.addWidget(self.ddc_status)
        self._sync_preview_cards()
        return card

    def _build_save(self) -> QWidget:
        card = Card()
        heading = QLabel(translate("Inspector", "Save"))
        heading.setFont(title_font(self, 1.0))
        card.body.addWidget(heading)
        self.chk_activate = QCheckBox(translate("Inspector", "Activate in KWin for {connector}").format(
            connector=self.connector or "–"))
        self.chk_activate.setChecked(True)
        self.chk_activate.setEnabled(self.compositor is not None and bool(self.connector))
        self.chk_activate.toggled.connect(self._update_save_buttons)
        card.body.addWidget(self.chk_activate)
        self.chk_preset = QCheckBox(translate("Inspector", "Also update in preset"))
        self.chk_preset.setEnabled(bool(self.presets) and self.display is not None)
        card.body.addWidget(self.chk_preset)
        self.combo_preset = QComboBox()
        self.combo_preset.addItems(self.presets)
        self.combo_preset.setEnabled(False)
        self.chk_preset.toggled.connect(self.combo_preset.setEnabled)
        card.body.addWidget(self.combo_preset)
        hint = SecondaryLabel(translate(
            "Inspector", "Only {connector} is overwritten: its current DDC values and this ICC profile. Other "
            "displays in the preset stay unchanged."
        ).format(connector=self.connector or "–"))
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        return card

    def _build_buttons(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(6)
        if self.staged_profile is not None:
            self.btn_save = QPushButton()
            self.btn_save.setDefault(True)
            self.btn_save.setMinimumHeight(36)
            self.btn_save.clicked.connect(self._on_save_default)
            btn_save_as = QPushButton(translate("Inspector", "Save As…"))
            btn_save_as.clicked.connect(self._on_save_as)
            btn_discard = QPushButton(translate("Inspector", "Discard && Restore Previous Profile"))
            btn_discard.clicked.connect(self.reject)
            for b in (self.btn_save, btn_save_as, btn_discard):
                col.addWidget(b)
            self._update_save_buttons()
        else:
            btn_open = QPushButton(translate("Inspector", "Open Another Profile…"))
            btn_open.clicked.connect(self._on_open_other)
            btn_close = QPushButton(translate("Inspector", "Close"))
            btn_close.setDefault(True)
            btn_close.clicked.connect(self.reject)
            col.addWidget(btn_open)
            col.addWidget(btn_close)
        return col

    # ------------------------------------------------------------------ content

    def _refresh(self) -> None:
        insp = self.inspection
        if self.staged_profile is not None and self.connector:
            model = self.display.model if self.display else ""
            self.lbl_title.setText(translate("Inspector", "New profile for {connector}").format(
                connector=self.connector) + (f" · {model}" if model else ""))
        else:
            self.lbl_title.setText(insp.description)
        parts = [insp.profile_path.name]
        try:
            ptype = read_profile_summary(insp.profile_path).profile_type
        except Exception:  # noqa: BLE001 - informational only
            ptype = ""
        if ptype:
            parts.append(ptype)
        if insp.total_measured_patches:
            parts.append(translate("Inspector", "{count} patches").format(count=num(insp.total_measured_patches)))
        self.lbl_sub.setText(" · ".join(parts))

        t = self.target
        self.kpi_white.set(cdm2(insp.luminance_cdm2, 1),
                           translate("Inspector", "Target {value}").format(value=num(t.luminance)) if t else "")
        self.kpi_black.set(num(insp.black_luminance_cdm2, 3, "cd/m²") if insp.black_luminance_cdm2 is not None
                           else "–", translate("Inspector", "measured") if insp.gray_ramp else "")
        self.kpi_contrast.set(f"{num(insp.contrast_ratio)} : 1" if insp.contrast_ratio else "–",
                              translate("Inspector", "static"))
        if insp.white_cct_kelvin is not None and insp.white_xy is not None:
            ref_xy, ref_name = (t.whitepoint_xy, t.whitepoint_label) if t else ((D65_X, D65_Y), "D65")
            u1, v1 = xy_to_uv(*insp.white_xy)
            u2, v2 = xy_to_uv(*ref_xy)
            duv = ((u1 - u2) ** 2 + (v1 - v2) ** 2) ** 0.5
            self.kpi_wp.set(num(insp.white_cct_kelvin, 0, "K"), translate("Inspector", "Δu′v′ {value} to {ref}")
                            .format(value=num(duv, 4), ref=ref_name))
        else:
            self.kpi_wp.set("–")
        self.kpi_gamma.set(f"γ {num(insp.effective_gamma, 2)}" if insp.effective_gamma is not None else "–",
                           translate("Inspector", "Target {value}").format(value=num(insp.target_gamma, 1)))
        for name, (bar, label) in self.cov_bars.items():
            value = insp.coverage_pct.get(name)
            bar.setValue(value)
            label.setText(num(value, 1, "%") if value is not None else "–")

        if insp.is_clean:
            self.banner.setKind("positive")
            self.banner.setText(translate(
                "Inspector", "<b>Kink check: no findings.</b> Curves are smooth and monotonic, gray balance is "
                "continuous."))
        else:
            self.banner.setKind("error" if insp.has_errors else "warning")
            details = " ".join(k.message for k in insp.kinks[:3])
            more = len(insp.kinks) - 3
            if more > 0:
                details += " " + translate("Inspector", "(+{count} more)").format(count=more)
            self.banner.setText(translate("Inspector", "<b>Kink check: {count} finding(s).</b> {details}")
                                .format(count=len(insp.kinks), details=details))
        self.curve_plot.set_inspection(insp)
        self.gamut_plot.set_inspection(insp)

    # ------------------------------------------------------------------ view options

    def _on_tab(self, index: int) -> None:
        gamut = index == TAB_GAMUT
        self.option_stack.setCurrentWidget(self.gamut_options if gamut else self.curve_options)
        self.seg_lstar.setVisible(index == TAB_TRC)
        self.chk_ref.setText(translate("Inspector", "Reference") if index == TAB_TRC
                             else translate("Inspector", "Target line"))
        self.plots.setCurrentWidget(self.gamut_plot if gamut else self.curve_plot)
        if not gamut:
            self.curve_plot.set_view({TAB_TRC: VIEW_TRC, TAB_GAMMA: VIEW_GAMMA, TAB_KNICK: VIEW_KNICK}[index])
        self._on_readout("")

    def _on_options(self, *_args) -> None:  # noqa: ANN002
        cp = self.curve_plot
        cp.channels = {k for k, chk in self.chk_channels.items() if chk.isChecked()}
        cp.show_points = self.chk_points.isChecked()
        cp.show_reference = self.chk_ref.isChecked()
        cp.lstar = self.seg_lstar.currentIndex() == 1
        gp = self.gamut_plot
        gp.show_display = self.chk_display.isChecked()
        gp.references = {name for name, chk in self.chk_refs.items() if chk.isChecked()}
        gp.uv = self.seg_cie.currentIndex() == 0
        cp.refresh()
        gp.refresh()

    def _on_readout(self, text: str) -> None:
        if text:
            self.readout.setText(text)
            return
        hint = translate("Inspector", "Move the mouse over the graph for live values")
        if self.tabs.currentIndex() != TAB_GAMUT:
            hint += "  ·  " + translate("Inspector", "Source rTRC/gTRC/bTRC")
        self.readout.setText(hint)

    # ------------------------------------------------------------------ live preview

    def _ddc_switching(self) -> bool:
        return self.ddc_apply is not None and self.ddc_previous is not None and self.ddc_new is not None \
            and self.ddc_previous != self.ddc_new

    def ddc_for(self, mode: int) -> DdcValues | None:
        """Hardware values belonging to a preview state: before the calibration only for "previous"."""
        return self.ddc_previous if mode == PREVIEW_PREVIOUS else self.ddc_new

    def set_preview(self, mode: int) -> None:
        if self.compositor is None or not self.connector or mode == self.preview_mode:
            return
        if self.verification.is_running() or self._ddc_task is not None:  # one state at a time
            return
        try:
            if mode == PREVIEW_NEW:
                self._apply_icc(str(self.inspection.profile_path))
            else:
                self._restore_previous(uncalibrated=mode == PREVIEW_UNCALIBRATED)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, translate("Inspector", "Preview Switch Error"), str(exc))
            return
        self.preview_mode = mode
        self._sync_preview_cards()
        self.verification._update_info()
        target = self.ddc_for(mode)
        if self._ddc_switching() and target != self._ddc_current:
            self._set_ddc_async(target)

    def _set_ddc_async(self, values: DdcValues) -> None:
        assert self.ddc_apply is not None
        apply = self.ddc_apply
        for card in getattr(self, "preview_cards", []):
            card.setEnabled(False)
        self.ddc_status.setText(translate("Inspector", "Setting display hardware (DDC/CI)…"))
        task = TaskThread(lambda: apply(values), self)

        def done(ok: bool, message: str = "") -> None:
            if ok:
                self._ddc_current = values
            self._ddc_task = None
            for card in getattr(self, "preview_cards", []):
                card.setEnabled(True)
            self.ddc_status.setText(self._ddc_text())
            if message:
                QMessageBox.warning(self, translate("Inspector", "Preview Switch Error"), message)

        task.succeeded.connect(lambda _r: done(True))
        task.failed.connect(lambda msg: done(False, msg))
        task.finished.connect(task.deleteLater)
        self._ddc_task = task
        task.start()

    def _set_ddc_now(self, values: DdcValues | None) -> None:
        """Blocking variant for saving/closing (the dialog is about to go away)."""
        if self._ddc_task is not None:
            self._ddc_task.wait()
        if self._ddc_switching() and values is not None and values != self._ddc_current:
            try:
                self.ddc_apply(values)  # type: ignore[misc]
                self._ddc_current = values
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, translate("Inspector", "Preview Switch Error"), str(exc))

    def _ddc_text(self) -> str:
        if not self._ddc_switching():
            return ""
        b, c, r, g, bl = self._ddc_current or (0, 0, 0, 0, 0)
        return translate("Inspector", "Hardware now: brightness {b} · contrast {c} · RGB {r}/{g}/{bl}").format(
            b=b, c=c, r=r, g=g, bl=bl)

    def active_profile_label(self) -> str:
        """What the display shows right now (for the verification): new / previous profile or none."""
        if self.preview_mode == PREVIEW_NEW:
            return self.inspection.profile_path.name
        if self.preview_mode == PREVIEW_PREVIOUS and self.previous_icc_path and self.previous_source == "ICC":
            return Path(self.previous_icc_path).name
        return translate("Inspector", "uncalibrated (sRGB, no ICC)")

    def _sync_preview_cards(self) -> None:
        for i, card in enumerate(getattr(self, "preview_cards", [])):
            card.setChecked(i == self.preview_mode)

    def _apply_icc(self, path: str) -> None:
        assert self.compositor is not None and self.connector
        self.compositor.apply_output_profile(connector=self.connector, icc_profile_path=path,
                                             color_profile_source="ICC", brightness=None)

    def _restore_previous(self, uncalibrated: bool = False) -> None:
        if self.compositor is None or not self.connector:
            return
        if not uncalibrated and self.previous_icc_path and self.previous_source == "ICC":
            self._apply_icc(self.previous_icc_path)
        else:
            self.compositor.reset_for_calibration(self.connector)

    # ------------------------------------------------------------------ saving

    def _update_save_buttons(self) -> None:
        if hasattr(self, "btn_save"):
            name = self.staged_profile.suggested_output_path.name if self.staged_profile else ""
            text = translate("Inspector", "Save && Activate") if self.chk_activate.isChecked() \
                else translate("Inspector", "Save")
            self.btn_save.setText(text)
            self.btn_save.setToolTip(name)

    def _on_save_default(self) -> None:
        if self.staged_profile is not None:
            self._finalize_save(self.staged_profile.suggested_output_path)

    def _on_save_as(self) -> None:
        if self.staged_profile is None:
            return
        dest_str, _ = QFileDialog.getSaveFileName(
            self, translate("Inspector", "Save ICC Profile As"), str(self.staged_profile.suggested_output_path),
            translate("Inspector", "ICC Profiles (*.icc *.icm)"))
        if dest_str:
            dest = Path(dest_str)
            self._finalize_save(dest if dest.suffix else dest.with_suffix(".icc"))

    def _finalize_save(self, dest: Path) -> None:
        assert self.staged_profile is not None
        saved = self.staged_profile.save_to(dest)
        if self.verification.is_running():
            self.verification.cancel()
        self.saved_profile_path = saved
        if self.compositor is not None and self.connector:
            if self.chk_activate.isChecked():
                self._apply_icc(str(saved))
                self._set_ddc_now(self.ddc_new)
            else:
                self._restore_previous()
                self._set_ddc_now(self.ddc_previous)
        if self.chk_preset.isChecked() and self.combo_preset.currentText():
            self.preset_to_update = self.combo_preset.currentText()
        self.accept()

    def _on_open_other(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, translate("Inspector", "Open ICC Profile"), str(user_icc_dir()),
                                              translate("Inspector", "ICC Profiles (*.icc *.icm)"))
        if not path:
            return
        try:
            self.inspection = inspect_profile(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, translate("Inspector", "Profile Load Error"), str(exc))
            return
        self._refresh()
        if self.preview_mode == PREVIEW_NEW and self.compositor is not None and self.connector:
            self._apply_icc(path)
        if hasattr(self, "preview_cards"):
            self.preview_cards[0].sub.setText(Path(path).name)

    def reject(self) -> None:
        if self.verification.is_running():
            self.verification.cancel()
        self._reject()

    def _reject(self) -> None:
        """Closing without saving restores what was active before (staged profile or a preview switch)."""
        if self.staged_profile is not None:
            if self.saved_profile_path is None:
                try:
                    self._restore_previous()
                    self._set_ddc_now(self.ddc_previous)
                finally:
                    self.staged_profile.cleanup()
        elif self.preview_mode != PREVIEW_PREVIOUS:
            try:
                self._restore_previous()
            except Exception:  # noqa: BLE001 - closing must not fail
                pass
        super().reject()
