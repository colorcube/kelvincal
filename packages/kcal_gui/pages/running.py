"""Running calibration page (mockup 1d): phase stepper, current patch, contrast search, 1b iterations."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kcal_core.i18n import translate
from kcal_core.models import ColorMeasurement, ContrastStepResult
from kcal_gui.fmt import cdm2, num
from kcal_gui.widgets import (
    Card,
    ContrastSearchView,
    LogPanel,
    MessageBanner,
    PatchSwatch,
    PhaseStepper,
    SecondaryLabel,
    SwatchStrip,
    mono_font,
    title_font,
)
from kcal_gui.widgets.run_views import STATE_DONE, STATE_FAILED, STATE_PENDING, STATE_RUNNING, STATE_SKIPPED

PHASES = ("1a", "1b", "2", "3")


class RunningPage(QWidget):
    pause_toggled = Signal(bool)
    cancel_requested = Signal()
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase_start = 0.0
        self._wp_rows = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)

        head = QHBoxLayout()
        col = QVBoxLayout()
        self.title = QLabel(translate("RunningPage", "Calibration running"))
        self.title.setFont(title_font(self, 1.4))
        self.subtitle = SecondaryLabel()
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        head.addLayout(col, 1)
        self.btn_pause = QPushButton(translate("RunningPage", "Pause"))
        self.btn_pause.setCheckable(True)
        self.btn_pause.toggled.connect(self._on_pause)
        self.btn_cancel = QPushButton(translate("RunningPage", "Cancel"))
        self.btn_cancel.clicked.connect(self.cancel_requested)
        self.btn_back = QPushButton(translate("RunningPage", "Back to Overview"))
        self.btn_back.clicked.connect(self.back_requested)
        head.addWidget(self.btn_pause)
        head.addWidget(self.btn_cancel)
        head.addWidget(self.btn_back)
        lay.addLayout(head)

        self.banner = MessageBanner(kind="information")
        lay.addWidget(self.banner)

        self.stepper = PhaseStepper([
            ("1a", translate("RunningPage", "Contrast")),
            ("1b", translate("RunningPage", "Whitepoint & luminance")),
            ("2", translate("RunningPage", "Patch measurement")),
            ("3", translate("RunningPage", "Profile computation")),
        ])
        lay.addSpacing(6)
        lay.addWidget(self.stepper)
        lay.addSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(12)
        lay.addLayout(grid, 1)

        # Left column: current patch
        patch_card = Card()
        patch_card.body.setSpacing(12)
        self.patch_title = QLabel(translate("RunningPage", "Waiting for sensor placement…"))
        self.patch_title.setFont(title_font(self, 1.05))
        self.patch_eta = SecondaryLabel()
        prow = QHBoxLayout()
        prow.addWidget(self.patch_title, 1)
        prow.addWidget(self.patch_eta)
        patch_card.body.addLayout(prow)
        current = QHBoxLayout()
        current.setSpacing(20)
        self.patch_swatch = PatchSwatch()
        current.addWidget(self.patch_swatch)
        self.patch_info = QLabel()
        self.patch_info.setFont(mono_font())
        self.patch_info.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        current.addWidget(self.patch_info, 1)
        patch_card.body.addLayout(current)
        patch_card.body.addWidget(SecondaryLabel(translate("RunningPage", "Last measured")))
        self.swatches = SwatchStrip(10)
        patch_card.body.addWidget(self.swatches)
        patch_card.body.addStretch(1)
        hint = SecondaryLabel(translate(
            "RunningPage", "Do not move the sensor. The patch window shows only a dim progress line."
        ))
        hint.setWordWrap(True)
        patch_card.body.addWidget(hint)
        grid.addWidget(patch_card, 0, 0, 2, 1)

        # Right column: 1a search, 1b iterations
        search_card = Card()
        self.search_title = QLabel(translate("RunningPage", "1a · Contrast binary search"))
        self.search_title.setFont(title_font(self, 1.0))
        search_card.body.addWidget(self.search_title)
        self.search_view = ContrastSearchView()
        search_card.body.addWidget(self.search_view)
        self.search_legend = SecondaryLabel(translate("RunningPage", "green: no clipping · red: clipping"))
        search_card.body.addWidget(self.search_legend)
        grid.addWidget(search_card, 0, 1)

        wp_card = Card()
        wp_title = QLabel(translate("RunningPage", "1b · Control loop"))
        wp_title.setFont(title_font(self, 1.0))
        wp_card.body.addWidget(wp_title)
        self.wp_table = QTableWidget(0, 5)
        self.wp_table.setHorizontalHeaderLabels([
            translate("RunningPage", "Bright."), "R/G/B", "CCT", "Δu′v′", "Y"
        ])
        self.wp_table.verticalHeader().setVisible(True)
        self.wp_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.wp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.wp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.wp_table.setFont(mono_font())
        wp_card.body.addWidget(self.wp_table, 1)
        grid.addWidget(wp_card, 1, 1)
        grid.setColumnStretch(0, 115)
        grid.setColumnStretch(1, 100)
        grid.setRowStretch(1, 1)

        self.log = LogPanel()
        self.log.setExpanded(False)
        lay.addWidget(self.log)

    # ------------------------------------------------------------------ run lifecycle

    def begin(self, subtitle: str, connector: str, phases: tuple[str, ...], contrast_range: tuple[int, int]) -> None:
        self.title.setText(translate("RunningPage", "Calibration running"))
        self.subtitle.setText(subtitle)
        self.banner.setKind("information")
        self.banner.setText(translate(
            "RunningPage",
            "<b>ColorGuard active.</b> {connector} runs as uncalibrated sRGB during the measurement, HDR/WCG "
            "off. The previous state is restored after completion or cancellation.",
        ).format(connector=connector))
        self.stepper.reset()
        for key in PHASES:
            if key not in phases:
                self.stepper.set_state(key, STATE_SKIPPED, translate("RunningPage", "skipped"))
        self.search_view.reset(*contrast_range)
        self.wp_table.setRowCount(0)
        self.swatches.clear()
        self.patch_swatch.set_rgb(None)
        self.patch_title.setText(translate("RunningPage", "Waiting for sensor placement…"))
        self.patch_info.setText(translate("RunningPage", "[Space/Enter] start · [Esc] cancel in the patch window"))
        self.patch_eta.setText("")
        self.btn_pause.setChecked(False)
        self.btn_pause.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.btn_back.hide()

    def finish(self, outcome: str, message: str = "") -> None:
        """outcome: "ok", "cancelled" or "failed"."""
        titles = {
            "ok": translate("RunningPage", "Calibration finished"),
            "cancelled": translate("RunningPage", "Calibration cancelled"),
            "failed": translate("RunningPage", "Calibration failed"),
        }
        self.title.setText(titles.get(outcome, ""))
        kinds = {"ok": "positive", "cancelled": "warning", "failed": "error"}
        self.banner.setKind(kinds.get(outcome, "information"))
        default = {
            "ok": translate("RunningPage", "All phases completed."),
            "cancelled": translate("RunningPage", "Cancelled. The previous display state was restored."),
        }.get(outcome, "")
        self.banner.setText(message or default)
        if outcome != "ok":
            for key in self.stepper.rows:
                if self.stepper.state(key) == STATE_RUNNING:
                    self.stepper.set_state(key, STATE_FAILED)
        self.btn_pause.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_back.show()

    def _on_pause(self, paused: bool) -> None:
        self.btn_pause.setText(translate("RunningPage", "Resume") if paused else translate("RunningPage", "Pause"))
        self.pause_toggled.emit(paused)

    # ------------------------------------------------------------------ observer slots

    def on_phase_started(self, phase: str) -> None:
        self._phase_start = time.monotonic()
        self.stepper.set_state(phase, STATE_RUNNING, "")
        if phase == "3":
            self.patch_title.setText(translate("RunningPage", "Phase 3 · Profile computation (colprof)"))
            self.patch_eta.setText("")

    def on_phase_finished(self, phase: str) -> None:
        self.stepper.set_state(phase, STATE_DONE)

    def on_progress(self, phase: str, current: int, total: int) -> None:
        self.stepper.set_progress(phase, current, total)
        self.stepper.set_state(phase, STATE_RUNNING, f"{current} / {total}")
        if phase == "2" and current > 3:
            elapsed = time.monotonic() - self._phase_start
            remaining = elapsed / current * (total - current)
            self.patch_eta.setText(translate("RunningPage", "approx. {minutes} min left").format(
                minutes=max(1, round(remaining / 60))))

    def on_contrast_step(self, step: ContrastStepResult) -> None:
        self.search_view.add_step(step.contrast, step.clipped)
        self.stepper.set_state("1a", STATE_RUNNING, f"C = {step.contrast} % · {cdm2(step.m_high.Y)}")
        if self.search_view.best is not None:
            self.stepper.rows["1a"][3].setText(
                f"C = {self.search_view.best} % · {len(self.search_view.steps)} "
                + translate("RunningPage", "measurements")
            )

    def on_whitepoint(self, m: ColorMeasurement, ddc: tuple[int, int, int, int]) -> None:
        row = self.wp_table.rowCount()
        self.wp_table.insertRow(row)
        b, r, g, bl = ddc if len(ddc) == 4 else (None, None, None, None)
        cells = [num(b), f"{r}/{g}/{bl}", f"{m.cct_kelvin:.0f}", num(m.delta_uv_to_d65(), 4), num(m.Y, 1)]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.wp_table.setItem(row, col, item)
        self.wp_table.scrollToBottom()
        self.stepper.set_state("1b", STATE_RUNNING, f"{m.cct_kelvin:.0f} K · {cdm2(m.Y)}")

    def on_patch(self, rgb: tuple[int, int, int], index: int, total: int) -> None:
        self.patch_title.setText(translate("RunningPage", "Phase 2 · Patch measurement"))
        self.patch_info.setText(
            translate("RunningPage", "Patch {index} / {total}\nTarget RGB {r} {g} {b}").format(
                index=index, total=total, r=rgb[0], g=rgb[1], b=rgb[2])
        )
        self.patch_swatch.set_rgb(rgb)
        self.swatches.push(rgb)

    def on_status(self, message: str) -> None:
        self.log.append(message)

    def mark_pending(self, phase: str) -> None:
        self.stepper.set_state(phase, STATE_PENDING)
