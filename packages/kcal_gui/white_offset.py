"""Visual whitepoint matching (dialog) and the per-display whitepoint offset it produces (QSettings).

The offset (Δx, Δy) is added to the whitepoint target of every calibration of that display, so a display
whose white looks different from the others despite identical measurements is calibrated to what the
user sees as the same white. See `kcal_ddc.visual_match`.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QLocale, QSettings, QSize, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kcal_core.i18n import translate
from kcal_core.models import D65_X, D65_Y, ColorMeasurement, DisplayInfo
from kcal_ddc.ddc_client import DDCClient
from kcal_ddc.visual_match import COOLER, GREENER, MAGENTA, WARMER, Gains, nudge, white_offset
from kcal_gui.widgets import SecondaryLabel, title_font
from kcal_gui.widgets.white_pad import MOVES, WhitePad, direction_icon
from kcal_gui.workers import TaskThread


def _key(display: DisplayInfo) -> str:
    return f"whiteoffset/{display.edid_hash or display.connector}"


def white_offset_for(display: DisplayInfo | None) -> tuple[float, float]:
    """The visual whitepoint offset (Δx, Δy) of `display`, (0, 0) if none was set."""
    if display is None:
        return 0.0, 0.0
    st = QSettings()
    return float(st.value(f"{_key(display)}/dx", 0.0) or 0.0), float(st.value(f"{_key(display)}/dy", 0.0) or 0.0)


def set_white_offset(display: DisplayInfo, offset: tuple[float, float]) -> None:
    st = QSettings()
    if offset == (0.0, 0.0):
        st.remove(_key(display))
    else:
        st.setValue(f"{_key(display)}/dx", offset[0])
        st.setValue(f"{_key(display)}/dy", offset[1])


def shifted_whitepoint(display: DisplayInfo | None, xy: tuple[float, float] | None) -> tuple[float, float]:
    """Whitepoint target for `display`: `xy` (D65 if None) plus its visual offset."""
    x, y = xy or (D65_X, D65_Y)
    dx, dy = white_offset_for(display)
    return x + dx, y + dy


def offset_text(offset: tuple[float, float]) -> str:
    loc = QLocale()

    def num(v: float) -> str:
        return ("+" if v > 0 else "") + loc.toString(v, "f", 4)

    return f"Δx {num(offset[0])} · Δy {num(offset[1])}"


# Runs the measurement job: (start_gains, final_gains, on_done(start, final), on_failed(message)).
MeasureFn = Callable[[Gains, Gains, Callable[[ColorMeasurement, ColorMeasurement], None], Callable[[str], None]],
                     None]


class VisualWhiteDialog(QDialog):
    """Moves the white of one display by eye (arrow keys / buttons, one DDC step each) until it matches a
    reference display, then measures the shift and stores it as the display's whitepoint offset.

    Cancel restores the gains the dialog started with.
    """

    def __init__(self, display: DisplayInfo, displays: list[DisplayInfo], ddc: DDCClient, measure: MeasureFn,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.display = display
        self.ddc = ddc
        self.measure = measure
        self.start: Gains | None = None
        self.gains: Gains | None = None
        self._written: Gains | None = None
        self._writer: TaskThread | None = None
        self._tasks: set[TaskThread] = set()
        self._closing = False
        self.accepted_offset: tuple[float, float] | None = None
        self.setWindowTitle(translate("VisualWhite", "Visual Whitepoint Matching"))
        # Only block the main window: an application-modal dialog would also swallow the keys of the patch
        # window (Space to start the measurement), which is a separate top-level window.
        self.setWindowModality(Qt.WindowModality.WindowModal)

        lay = QVBoxLayout(self)
        head = QLabel(translate("VisualWhite", "Match the white of {display} by eye").format(
            display=display.display_label))
        head.setFont(title_font(self, 1.1))
        head.setWordWrap(True)
        lay.addWidget(head)
        self.combo_ref = QComboBox()
        for d in displays:
            if d.connector != display.connector:
                self.combo_ref.addItem(d.display_label, d.connector)
        self.combo_ref.currentIndexChanged.connect(self._update)
        form = QFormLayout()
        form.addRow(translate("VisualWhite", "Compare with:"), self.combo_ref)
        lay.addLayout(form)
        self.intro = SecondaryLabel()
        self.intro.setWordWrap(True)
        lay.addWidget(self.intro)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.pad = WhitePad()
        self.pad.stepRequested.connect(self.step)
        self.buttons: dict[str, QToolButton] = {}
        for direction, text, key, row, col, align in (
            (GREENER, translate("VisualWhite", "Greener"), Qt.Key.Key_Up, 0, 1, Qt.AlignmentFlag.AlignHCenter),
            (WARMER, translate("VisualWhite", "Warmer"), Qt.Key.Key_Left, 1, 0, Qt.AlignmentFlag.AlignVCenter),
            (COOLER, translate("VisualWhite", "Cooler"), Qt.Key.Key_Right, 1, 2, Qt.AlignmentFlag.AlignVCenter),
            (MAGENTA, translate("VisualWhite", "Magenta"), Qt.Key.Key_Down, 2, 1, Qt.AlignmentFlag.AlignHCenter),
        ):
            btn = QToolButton()
            btn.setIcon(direction_icon(direction))
            btn.setIconSize(QSize(28, 28))
            btn.setText(text)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setMinimumWidth(96)
            btn.clicked.connect(lambda _=False, d=direction: self.step(d))
            grid.addWidget(btn, row, col, align)
            self.buttons[direction] = btn
            QShortcut(QKeySequence(key), self, activated=lambda d=direction: self.step(d))
        grid.addWidget(self.pad, 1, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid, 1)
        self.lbl_gains = QLabel()
        self.lbl_gains.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_gains)

        self.btn_reset = QPushButton(QIcon.fromTheme("edit-undo"), translate("VisualWhite", "Back to Start"))
        self.btn_reset.clicked.connect(self.reset)
        lay.addWidget(self.btn_reset, 0, Qt.AlignmentFlag.AlignHCenter)

        self.lbl_offset = SecondaryLabel()
        self.lbl_offset.setWordWrap(True)
        lay.addWidget(self.lbl_offset)
        self.btn_clear = QPushButton(translate("VisualWhite", "Remove Stored Offset"))
        self.btn_clear.clicked.connect(self._clear_offset)
        lay.addWidget(self.btn_clear, 0, Qt.AlignmentFlag.AlignLeft)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.btn_accept = box.addButton(translate("VisualWhite", "Measure && Save…"),
                                        QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_accept.setToolTip(translate(
            "VisualWhite", "Measures white with the matched and with the original settings (sensor on this "
            "display) and stores the difference as whitepoint offset for its calibrations."))
        box.accepted.connect(self._measure_and_save)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

        self._update()
        geometry = QSettings().value("visualwhite/geometry")
        if geometry is None or not self.restoreGeometry(geometry):
            self.resize(640, 760)
        self._run(lambda: self.ddc.read_state(display.i2c_bus), self._on_state)

    # ------------------------------------------------------------------ state

    def _run(self, fn, on_success, on_failed=None) -> TaskThread:  # noqa: ANN001
        task = TaskThread(fn, self)
        self._tasks.add(task)
        task.succeeded.connect(on_success)
        task.failed.connect(on_failed or (lambda msg: QMessageBox.warning(
            self, translate("VisualWhite", "Visual Whitepoint Matching"), msg)))
        task.finished.connect(lambda: self._tasks.discard(task))
        task.start()
        return task

    def _on_state(self, state) -> None:  # noqa: ANN001
        gains = (state.red_gain, state.green_gain, state.blue_gain)
        if None in gains:
            QMessageBox.warning(self, self.windowTitle(), translate(
                "VisualWhite", "The RGB gains of this display cannot be read via DDC/CI."))
            return
        self.start = self.gains = self._written = gains   # type: ignore[assignment]
        self._update()

    def step(self, direction: str) -> None:
        if self.gains is None:
            return
        gains = nudge(self.gains, direction)
        if gains == self.gains:             # a gain is at its limit
            return
        self.gains = gains
        h, v = self.pad.position
        self.pad.set_position((h + MOVES[direction][0], v + MOVES[direction][1]))
        self._write()
        self._update()

    def reset(self) -> None:
        if self.start is not None:
            self.gains = self.start
            self.pad.set_position((0, 0))
            self._write()
            self._update()

    def _write(self) -> None:
        """Writes the latest gains; steps made while a write is running are coalesced into the next one."""
        if self._closing or self._writer is not None or self.gains is None or self.gains == self._written:
            return
        target = self.gains
        bus = self.display.i2c_bus

        def done(_r: object) -> None:
            self._written = target

        def finished() -> None:
            self._writer = None
            self._write()

        self._writer = self._run(
            lambda: self.ddc.set_vcp_values(bus, dict(zip(("16", "18", "1A"), target))), done)
        self._writer.finished.connect(finished)

    def _update(self) -> None:
        ref = self.combo_ref.currentText() or translate("VisualWhite", "the other display")
        self.intro.setText(translate(
            "VisualWhite",
            "Put the same neutral content on both displays (white areas, a black & white photo) and look at them "
            "straight on. Move the white of this display with the arrow keys until it looks like {reference}: "
            "one step changes one RGB gain. For the measurement the sensor has to be on this display."
        ).format(reference=ref))
        ready = self.gains is not None
        for btn in self.buttons.values():
            btn.setEnabled(ready)
        self.pad.setEnabled(ready)
        self.btn_reset.setEnabled(ready and self.gains != self.start)
        self.btn_accept.setEnabled(ready and self.gains != self.start)
        if ready:
            self.lbl_gains.setText(translate("VisualWhite", "R/G/B {now} · Start {start}").format(
                now="/".join(map(str, self.gains)), start="/".join(map(str, self.start))))
        else:
            self.lbl_gains.setText(translate("VisualWhite", "Reading DDC…"))
        current = white_offset_for(self.display)
        self.lbl_offset.setText(
            translate("VisualWhite", "Stored offset for this display: {offset}").format(offset=offset_text(current))
            if current != (0.0, 0.0) else translate("VisualWhite", "No offset stored for this display yet."))
        self.btn_clear.setVisible(current != (0.0, 0.0))

    # ------------------------------------------------------------------ results

    def _clear_offset(self) -> None:
        set_white_offset(self.display, (0.0, 0.0))
        self._update()

    def _measure_and_save(self) -> None:
        if self.start is None or self.gains is None:
            return
        self._wait_for_tasks()
        self.setEnabled(False)

        def done(start: ColorMeasurement, final: ColorMeasurement) -> None:
            self.setEnabled(True)
            offset = white_offset(start.xy, final.xy, white_offset_for(self.display))
            set_white_offset(self.display, offset)
            self.accepted_offset = offset
            self.start = self.gains    # the display keeps the matched gains
            QMessageBox.information(self, self.windowTitle(), translate(
                "VisualWhite",
                "White moved from xy {start} to {final}.\n\nStored whitepoint offset for this display: {offset}. "
                "Calibrations of this display now aim at the shifted white. Recalibrate it so that luminance and "
                "profile match the new white.").format(
                start=f"{start.xy[0]:.4f}/{start.xy[1]:.4f}", final=f"{final.xy[0]:.4f}/{final.xy[1]:.4f}",
                offset=offset_text(offset)))
            self.accept()

        def failed(msg: str) -> None:
            self.setEnabled(True)
            if msg:
                QMessageBox.critical(self, self.windowTitle(), msg)

        self.measure(self.start, self.gains, done, failed)

    def _wait_for_tasks(self) -> None:
        for task in list(self._tasks):
            task.wait(10000)

    def reject(self) -> None:
        """Cancel: the display goes back to the gains it had when the dialog was opened."""
        self._closing = True
        self._wait_for_tasks()
        if self.start is not None and (self.gains != self.start or self._written != self.start):
            try:
                self.ddc.set_vcp_values(self.display.i2c_bus, dict(zip(("16", "18", "1A"), self.start)))
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, self.windowTitle(), str(exc))
            self.gains = self._written = self.start
        super().reject()

    def done(self, result: int) -> None:  # noqa: D401 - QDialog API
        QSettings().setValue("visualwhite/geometry", self.saveGeometry())
        self._closing = True
        self._wait_for_tasks()
        super().done(result)
