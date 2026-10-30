"""Qt glue that runs the Qt-free `CalibrationController` in a worker thread.

- `QtPatchDisplay`: `PatchDisplay` implementation that forwards calls from the worker thread to a
  `WaylandPatchWindow` living in the GUI thread (blocking, so a patch is shown before it is measured).
- `QtCalibrationObserver`: `CalibrationObserver` that re-emits progress as Qt signals (queued to the GUI).
- `QtMeasurementReviewer`: asks the user (dialog 1i) what to do with implausible patches; blocks the
  worker until the dialog is closed.
- `CalibrationThread`: runs one controller job in a `QThread` and reports result/error/cancel.
- `TaskThread`: runs any short blocking call (discovery, preset apply) off the GUI thread.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from kcal_core.models import ColorMeasurement, ContrastStepResult
from kcal_gui.controller import (
    CalibrationCancelled,
    CalibrationController,
    CalibrationObserver,
    CancelToken,
)
from kcal_gui.inhibit import SleepInhibitor
from kcal_gui.patch_window import WaylandPatchWindow


class _PatchBridge(QObject):
    """Lives in the GUI thread; its slots are invoked from the worker via blocking queued signals."""

    request_show_placement = Signal(str)
    request_show_patch = Signal(tuple, str, float)
    request_close = Signal()

    def __init__(self, window: WaylandPatchWindow) -> None:
        super().__init__()
        self.window = window
        conn = Qt.ConnectionType.BlockingQueuedConnection
        self.request_show_placement.connect(self._show_placement, conn)
        self.request_show_patch.connect(self._show_patch, conn)
        self.request_close.connect(self._close, conn)

    @Slot(str)
    def _show_placement(self, prompt: str) -> None:
        self.window.show_placement(prompt)

    @Slot(tuple, str, float)
    def _show_patch(self, rgb: tuple, status: str, progress: float) -> None:
        self.window.set_patch_rgb(rgb, status_text=status, progress=progress if progress >= 0 else None)

    @Slot()
    def _close(self) -> None:
        self.window.hide()


class QtPatchDisplay:
    """Thread-safe `PatchDisplay` backed by a `WaylandPatchWindow`. Create it in the GUI thread.

    Esc (or closing the window) aborts the placement prompt and, during a running measurement,
    cancels the whole run through the bound `CancelToken`.
    While it exists, screen locker, dimming and suspend are inhibited (released in `dispose`).
    """

    def __init__(self, connector: str, cancel: CancelToken) -> None:
        self.window = WaylandPatchWindow(connector=connector)  # raises if the screen is unknown
        self.cancel = cancel
        self._bridge = _PatchBridge(self.window)
        self._placement_done = threading.Event()
        self._placement_ok = False
        self._closing = False
        self.window.confirmed.connect(self._on_confirmed)
        self.window.aborted.connect(self._on_aborted)
        self.inhibitor = SleepInhibitor("Measuring display colours")
        self.inhibitor.acquire()

    def _on_confirmed(self) -> None:
        self._placement_ok = True
        self._placement_done.set()

    def _on_aborted(self) -> None:
        if self._closing:
            return
        if not self._placement_done.is_set():
            self._placement_ok = False
            self._placement_done.set()
        else:
            self.cancel.cancel()

    def _call(self, name: str, *args: Any) -> None:  # noqa: ANN401
        """Invokes bridge slot `_<name>` in the GUI thread via signal `request_<name>`."""
        if QThread.currentThread() == self._bridge.thread():
            # Already in the GUI thread (e.g. tests): a blocking queued connection would dead-lock.
            getattr(self._bridge, f"_{name}")(*args)
        else:
            getattr(self._bridge, f"request_{name}").emit(*args)

    # PatchDisplay protocol ---------------------------------------------------------------

    def wait_for_placement(self, prompt: str, cancel: CancelToken) -> bool:
        self._placement_done.clear()
        self._placement_ok = False
        self._closing = False
        self._call("show_placement", prompt)
        while not self._placement_done.wait(0.1):
            if cancel.cancelled:
                return False
        return self._placement_ok

    def show_patch(self, rgb: tuple[int, int, int], status: str, progress: float | None = None) -> None:
        self._closing = False
        self._call("show_patch", tuple(rgb), status, -1.0 if progress is None else float(progress))

    def close(self) -> None:
        self._closing = True
        self._call("close")

    def dispose(self) -> None:
        """Destroys the window (GUI thread only, after the worker has finished)."""
        self._closing = True
        self.inhibitor.release()
        self.window.close()
        self.window.deleteLater()


class QtCalibrationObserver(QObject, CalibrationObserver):
    """Re-emits controller callbacks as Qt signals; connect them with the default (auto/queued) type."""

    status_changed = Signal(str)
    phase_begun = Signal(str)
    phase_done = Signal(str)
    progress_changed = Signal(str, int, int)
    contrast_step_measured = Signal(object)
    whitepoint_measured = Signal(object, object)
    patch_shown = Signal(object, int, int)
    batch_begun = Signal(int, int, str)
    batch_done = Signal(object)

    def status(self, message: str) -> None:
        self.status_changed.emit(message)

    def phase_started(self, phase: str) -> None:
        self.phase_begun.emit(phase)

    def phase_finished(self, phase: str) -> None:
        self.phase_done.emit(phase)

    def progress(self, phase: str, current: int, total: int) -> None:
        self.progress_changed.emit(phase, current, total)

    def contrast_step(self, step: ContrastStepResult) -> None:
        self.contrast_step_measured.emit(step)

    def whitepoint_reading(
        self, measurement: ColorMeasurement, ddc: tuple[int, int, int, int]
    ) -> None:
        self.whitepoint_measured.emit(measurement, ddc)

    def patch_measured(self, rgb: tuple[int, int, int], index: int, total: int) -> None:
        self.patch_shown.emit(rgb, index, total)

    def batch_item_started(self, index: int, total: int, label: str) -> None:
        self.batch_begun.emit(index, total, label)

    def batch_item_finished(self, result) -> None:  # noqa: ANN001
        self.batch_done.emit(result)


class QtMeasurementReviewer(QObject):
    """Controller `reviewer` callable: shows `OutlierDialog` in the GUI thread and returns its decision."""

    _request = Signal(object, int)

    def __init__(self, parent_widget, before_dialog: Callable[[], None] | None = None) -> None:  # noqa: ANN001
        super().__init__()
        self._parent_widget = parent_widget
        self._before_dialog = before_dialog
        self._decision = ""
        self._request.connect(self._ask, Qt.ConnectionType.BlockingQueuedConnection)

    def __call__(self, check, attempt: int) -> str:  # noqa: ANN001 - MeasurementCheck
        if QThread.currentThread() == self.thread():
            self._ask(check, attempt)
        else:
            self._request.emit(check, attempt)
        return self._decision

    @Slot(object, int)
    def _ask(self, check, attempt: int) -> None:  # noqa: ANN001
        from kcal_gui.outlier_dialog import OutlierDialog  # GUI-only import

        if self._before_dialog is not None:
            self._before_dialog()
        dlg = OutlierDialog(check, attempt, self._parent_widget)
        dlg.exec()
        self._decision = dlg.decision


class CalibrationThread(QThread):
    """Runs `job(controller)` in a worker thread. Exactly one of the result signals fires."""

    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        controller: CalibrationController,
        job: Callable[[CalibrationController], Any],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.job = job

    def run(self) -> None:
        try:
            result = self.job(self.controller)
        except CalibrationCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            if self.controller.cancel.cancelled:
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(result)


class TaskThread(QThread):
    """Runs a blocking callable off the GUI thread (discovery, preset apply, …)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.fn = fn

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(result)
