"""KelvinCal main window: sidebar navigation, page header, monitor/preset/profile pages and calibration jobs."""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kcal_argyll.instruments import InstrumentStatus, detect_instruments
from kcal_argyll.profile_inspector import inspect_profile
from kcal_core.compositor import get_compositor_backend
from kcal_core.discovery import discover_displays
from kcal_core.i18n import translate
from kcal_core.models import DisplayInfo, Preset
from kcal_core.paths import user_icc_dir
from kcal_core.targets import CalibrationTarget
from kcal_ddc.contrast_optimizer import ContrastOptimizationConfig
from kcal_ddc.ddc_client import DDCClient
from kcal_gui.controller import CalibrationController, CancelToken, FullCalibrationResult, ProfilingResult
from kcal_gui.pages.monitors_expert import (
    PHASE_1A,
    PHASE_1B,
    PHASE_23,
    PHASE_ALL,
    PHASE_TEST,
    MonitorsExpertPage,
)
from kcal_gui.inspector import InspectorDialog
from kcal_gui.pages.monitors_simple import MonitorsSimplePage
from kcal_gui.pages.presets import PresetsPage
from kcal_gui.pages.profiles import ProfilesPage
from kcal_gui.pages.running import RunningPage
from kcal_gui.patch_window import WaylandPatchWindow
from kcal_gui.theme import ThemeManager
from kcal_gui.widgets import SecondaryLabel, SegmentedControl, StatusDot, title_font
from kcal_gui.workers import CalibrationThread, QtCalibrationObserver, QtPatchDisplay, TaskThread
from kcal_presets.manager import PresetManager, preset_drift

NAV_MONITORS, NAV_PRESETS, NAV_PROFILES = range(3)
MODE_SIMPLE, MODE_EXPERT = range(2)


class KelvinCalMainWindow(QMainWindow):
    def __init__(self, theme: ThemeManager | None = None) -> None:
        super().__init__()
        self.setWindowTitle("KelvinCal")
        self.resize(1280, 820)
        self.theme = theme

        self.compositor = get_compositor_backend()
        self.ddc_client = DDCClient()
        self.preset_manager = PresetManager(compositor=self.compositor, ddc_client=self.ddc_client)
        self.displays: list[DisplayInfo] = []
        self.presets: list[Preset] = []
        self.active_preset = ""
        self._recalibrate_preset = ""  # preset to preselect in the inspector after "Recalibrate…"
        self.selected_connector = ""
        self._job: CalibrationThread | None = None
        self._job_cancel: CancelToken | None = None
        self._job_patch: QtPatchDisplay | None = None
        self._job_observer: QtCalibrationObserver | None = None
        self._tasks: set[TaskThread] = set()
        self._test_window: WaylandPatchWindow | None = None
        self._return_nav = NAV_MONITORS

        self._build_menu()
        self._build_ui()
        self._restore_settings()
        self.refresh_displays()
        self.refresh_presets()
        self.detect_sensor()

    # ------------------------------------------------------------------ construction

    def _build_menu(self) -> None:
        mb = self.menuBar()
        m_file = mb.addMenu(translate("MainWindow", "&File"))
        self.act_open = m_file.addAction(QIcon.fromTheme("document-open"),
                                         translate("MainWindow", "Open ICC Profile…"), self.action_open_profile)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_refresh = m_file.addAction(QIcon.fromTheme("view-refresh"),
                                            translate("MainWindow", "Refresh Displays && Sensor"), self.action_refresh)
        self.act_refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        m_file.addSeparator()
        act_quit = m_file.addAction(QIcon.fromTheme("application-exit"), translate("MainWindow", "&Quit"), self.close)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)

        m_view = mb.addMenu(translate("MainWindow", "&View"))
        self.mode_group = QActionGroup(self)
        self.act_simple = m_view.addAction(translate("MainWindow", "Simple Mode"))
        self.act_expert = m_view.addAction(translate("MainWindow", "Expert Mode"))
        for i, act in enumerate((self.act_simple, self.act_expert)):
            act.setCheckable(True)
            act.setShortcut(QKeySequence(f"Ctrl+Shift+{i + 1}"))
            act.triggered.connect(lambda _=False, m=i: self.set_mode(m))
            self.mode_group.addAction(act)
        self.act_simple.setChecked(True)
        m_view.addSeparator()
        self.nav_actions: list[QAction] = []
        for i, (icon, text) in enumerate(self._nav_entries()):
            act = m_view.addAction(QIcon.fromTheme(icon), text)
            act.setShortcut(QKeySequence(f"Alt+{i + 1}"))
            act.triggered.connect(lambda _=False, n=i: self.nav.setCurrentRow(n))
            self.nav_actions.append(act)

        m_cal = mb.addMenu(translate("MainWindow", "&Calibration"))
        self.act_test_patch = m_cal.addAction(translate("MainWindow", "Test Patch Window"),
                                              self.action_test_patch_window)
        self.act_cancel = m_cal.addAction(QIcon.fromTheme("process-stop"),
                                          translate("MainWindow", "Cancel Measurement"), self.action_cancel_job)
        self.act_cancel.setEnabled(False)

        m_settings = mb.addMenu(translate("MainWindow", "&Settings"))
        if self.theme is not None:
            self.theme.build_menu(m_settings)

        m_help = mb.addMenu(translate("MainWindow", "&Help"))
        m_help.addAction(QIcon.fromTheme("help-about"), translate("MainWindow", "About KelvinCal"), self.action_about)
        m_help.addAction(translate("MainWindow", "About Qt"), QApplication.aboutQt)

    @staticmethod
    def _nav_entries() -> list[tuple[str, str]]:
        return [
            ("video-display", translate("MainWindow", "Displays")),
            ("bookmarks", translate("MainWindow", "Presets")),
            ("color-profile", translate("MainWindow", "Profiles")),
        ]

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        # Sidebar
        side = QFrame()
        side.setFrameShape(QFrame.Shape.NoFrame)
        side.setAutoFillBackground(True)
        side.setBackgroundRole(QPalette.ColorRole.Base)
        side.setFixedWidth(220)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(8, 12, 8, 12)
        app_title = QLabel("KelvinCal")
        app_title.setFont(title_font(self, 1.3))
        app_title.setContentsMargins(8, 0, 0, 8)
        side_lay.addWidget(app_title)
        self.nav = QListWidget()
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.nav.setIconSize(QSize(22, 22))
        self.nav.setSpacing(2)
        self.nav.viewport().setAutoFillBackground(False)
        for icon, text in self._nav_entries():
            self.nav.addItem(QListWidgetItem(QIcon.fromTheme(icon), text))
        self.nav.currentRowChanged.connect(self._on_nav)
        side_lay.addWidget(self.nav, 1)
        self.sensor_dot, self.sensor_text = StatusDot(), SecondaryLabel(translate("MainWindow", "Looking for sensor…"))
        self.comp_dot, self.comp_text = StatusDot(), SecondaryLabel()
        for dot, text in ((self.sensor_dot, self.sensor_text), (self.comp_dot, self.comp_text)):
            row = QHBoxLayout()
            row.setContentsMargins(8, 2, 0, 2)
            text.setWordWrap(True)
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(text, 1)
            side_lay.addLayout(row)
        root.addWidget(side)

        # Main area: header + stacked pages
        main = QWidget()
        main_lay = QVBoxLayout(main)
        main_lay.setContentsMargins(0, 12, 0, 0)
        head = QHBoxLayout()
        head.setContentsMargins(16, 0, 16, 0)
        self.page_title = QLabel()
        self.page_title.setFont(title_font(self, 1.5))
        head.addWidget(self.page_title, 1)
        head.addWidget(SecondaryLabel(translate("MainWindow", "Active preset")))
        self.combo_preset = QComboBox()
        self.combo_preset.setMinimumWidth(180)
        self.combo_preset.activated.connect(self._on_preset_combo)
        head.addWidget(self.combo_preset)
        head.addSpacing(12)
        self.mode_switch = SegmentedControl([translate("MainWindow", "Simple"), translate("MainWindow", "Expert")])
        self.mode_switch.currentChanged.connect(self.set_mode)
        head.addWidget(self.mode_switch)
        main_lay.addLayout(head)

        self.stack = QStackedWidget()
        main_lay.addWidget(self.stack, 1)
        root.addWidget(main, 1)

        self.page_simple = MonitorsSimplePage()
        self.page_expert = MonitorsExpertPage()
        self.page_running = RunningPage()
        self.page_presets = PresetsPage()
        self.page_profiles = ProfilesPage()
        for page in (self.page_simple, self.page_expert, self.page_running, self.page_presets, self.page_profiles):
            self.stack.addWidget(page)

        self.page_simple.display_selected.connect(self.select_display)
        self.page_simple.inspect_requested.connect(self.inspect_display_profile)
        self.page_simple.start_requested.connect(self.action_run_target)
        self.page_expert.display_selected.connect(self.select_display)
        self.page_expert.phase_requested.connect(self._on_expert_phase)
        self.page_running.cancel_requested.connect(self.action_cancel_job)
        self.page_running.pause_toggled.connect(self._on_pause)
        self.page_running.back_requested.connect(lambda: self._show_nav(self._return_nav))
        self.page_presets.capture_requested.connect(self.action_capture_preset)
        self.page_presets.activate_requested.connect(self.activate_preset)
        self.page_presets.duplicate_requested.connect(self.action_duplicate_preset)
        self.page_presets.rename_requested.connect(self.action_rename_preset)
        self.page_presets.delete_requested.connect(self.action_delete_preset)
        self.page_presets.recalibrate_requested.connect(self.action_recalibrate)
        self.page_presets.inspect_requested.connect(self.open_inspector)
        self.page_profiles.inspect_requested.connect(self.open_inspector)
        self.page_profiles.open_file_requested.connect(self.action_open_profile)

        for i in range(9):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda n=i: self._activate_preset_index(n))

        self.mode = MODE_SIMPLE
        self.nav.setCurrentRow(NAV_MONITORS)

    # ------------------------------------------------------------------ navigation & mode

    def _on_nav(self, row: int) -> None:
        if row < 0:
            return
        self._return_nav = row
        titles = [translate("MainWindow", "Calibrate Display"), translate("MainWindow", "Presets"),
                  translate("MainWindow", "Profiles")]
        self.page_title.setText(titles[row])
        self.mode_switch.setVisible(row == NAV_MONITORS)
        if row == NAV_MONITORS:
            self.stack.setCurrentWidget(self.page_expert if self.mode == MODE_EXPERT else self.page_simple)
        elif row == NAV_PRESETS:
            self.stack.setCurrentWidget(self.page_presets)
        else:
            self.page_profiles.refresh(self.displays)
            self.stack.setCurrentWidget(self.page_profiles)

    def _show_nav(self, row: int) -> None:
        self.nav.setCurrentRow(row)
        self._on_nav(row)

    def set_mode(self, mode: int) -> None:
        self.mode = mode
        self.mode_switch.blockSignals(True)
        self.mode_switch.setCurrentIndex(mode)
        self.mode_switch.blockSignals(False)
        (self.act_expert if mode == MODE_EXPERT else self.act_simple).setChecked(True)
        if self._job is None and self.nav.currentRow() == NAV_MONITORS:
            self._on_nav(NAV_MONITORS)

    # ------------------------------------------------------------------ settings

    def _restore_settings(self) -> None:
        st = QSettings()
        geometry = st.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.page_expert.restore_settings(st)
        state = st.value("presets/splitter")
        if state is not None:
            self.page_presets.splitter.restoreState(state)
        self.selected_connector = str(st.value("params/connector", ""))
        self.page_simple.set_target_key(str(st.value("simple/target", "photo")))
        self.set_mode(int(st.value("window/mode", MODE_SIMPLE)))
        self._show_nav(int(st.value("window/nav", NAV_MONITORS)))

    def _save_settings(self) -> None:
        st = QSettings()
        st.setValue("window/geometry", self.saveGeometry())
        st.setValue("window/mode", self.mode)
        st.setValue("window/nav", max(0, self.nav.currentRow()))
        st.setValue("presets/splitter", self.page_presets.splitter.saveState())
        st.setValue("params/connector", self.selected_connector)
        st.setValue("simple/target", self.page_simple.current_target().key)
        self.page_expert.save_settings(st)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._job is not None:
            answer = QMessageBox.question(
                self,
                translate("MainWindow", "Calibration running"),
                translate("MainWindow", "A measurement is still running. Cancel it and quit?"),
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.action_cancel_job()
            self._job.wait(10000)
        for task in list(self._tasks):
            task.wait(5000)
        self._save_settings()
        super().closeEvent(event)

    # ------------------------------------------------------------------ helpers

    def log(self, message: str) -> None:
        self.page_expert.log.append(message)
        self.page_running.on_status(message)

    def selected_display(self) -> DisplayInfo | None:
        return next((d for d in self.displays if d.connector == self.selected_connector), None)

    def select_display(self, connector: str) -> None:
        self.selected_connector = connector
        self.page_simple.set_selected(connector)
        self.page_expert.set_selected(connector)

    def _run_task(self, fn, on_success, error_title: str | None) -> None:  # noqa: ANN001
        """Runs `fn` in a background thread; `on_success(result)` is called in the GUI thread."""
        task = TaskThread(fn, self)
        self._tasks.add(task)
        task.succeeded.connect(on_success)
        if error_title:
            task.failed.connect(lambda msg: QMessageBox.critical(self, error_title, msg))
        task.finished.connect(lambda: (self._tasks.discard(task), task.deleteLater()))
        task.start()

    def action_refresh(self) -> None:
        self.refresh_displays()
        self.detect_sensor()

    def detect_sensor(self) -> None:
        self._run_task(detect_instruments, self._on_instruments, None)

    def _on_instruments(self, status: InstrumentStatus) -> None:
        hint = ""
        if not status.argyll_version:
            hint = translate("MainWindow", "ArgyllCMS was not found. Install it (package \"argyllcms\") to measure.")
        elif not status.instruments:
            hint = translate("MainWindow", "No measuring instrument found. Connect the sensor and press F5.")
        self.page_simple.set_sensor_hint(hint)
        self.page_expert.set_sensor_hint(hint)
        if not status.argyll_version:
            self.sensor_dot.setState("error")
            self.sensor_text.setText(translate("MainWindow", "ArgyllCMS not found"))
        elif status.instruments:
            self.sensor_dot.setState("ok")
            self.sensor_text.setText(translate("MainWindow", "{sensor} ready · Argyll {version}").format(
                sensor=status.instruments[0], version=status.argyll_version))
        else:
            self.sensor_dot.setState("warning")
            self.sensor_text.setText(translate("MainWindow", "No sensor connected · Argyll {version}").format(
                version=status.argyll_version))

    def _update_compositor_status(self) -> None:
        self.comp_dot.setState("ok" if self.displays else "warning")
        name = {"kwin": "KWin", "mutter": "Mutter", "colord": "colord"}.get(self.compositor.name, self.compositor.name)
        self.comp_text.setText(translate("MainWindow", "{compositor} · {count} outputs").format(
            compositor=name, count=len(self.displays)))

    # ------------------------------------------------------------------ displays & presets

    def refresh_displays(self, then=None) -> None:  # noqa: ANN001 - optional callable run after the update
        self.log(translate("MainWindow", "Reading displays via DRM sysfs, ddcutil, and compositor..."))

        def done(displays: list[DisplayInfo]) -> None:
            self.displays = displays
            if not any(d.connector == self.selected_connector for d in displays):
                with_ddc = [d for d in displays if d.i2c_bus is not None]
                self.selected_connector = (with_ddc or displays)[0].connector if displays else ""
            self._update_displays_ui()
            self.log(translate("MainWindow", "Displays detected: {count}").format(count=len(displays)))
            if then is not None:
                then()

        self._run_task(
            lambda: discover_displays(compositor=self.compositor, include_ddc_values=True),
            done,
            translate("MainWindow", "Display Detection Error"),
        )

    def _update_displays_ui(self) -> None:
        active = next((p for p in self.presets if p.name == self.active_preset), None)
        drift = set(preset_drift(active, self.displays)) if active else set()
        self.page_simple.set_displays(self.displays, self.selected_connector, drift)
        self.page_expert.set_displays(self.displays, self.selected_connector)
        self.page_presets.set_data(self.active_preset, self.presets, self.displays)
        if self.stack.currentWidget() is self.page_profiles:
            self.page_profiles.refresh(self.displays)
        self._update_compositor_status()

    def refresh_presets(self) -> None:
        self.active_preset, self.presets = self.preset_manager.load_all()
        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        self.combo_preset.addItem(translate("MainWindow", "– none –"), "")
        for p in self.presets:
            self.combo_preset.addItem(p.name, p.name)
        self.combo_preset.setCurrentIndex(max(0, self.combo_preset.findData(self.active_preset)))
        self.combo_preset.blockSignals(False)
        self._update_displays_ui()

    def _on_preset_combo(self, index: int) -> None:
        name = self.combo_preset.itemData(index)
        if name and name != self.active_preset:
            self.activate_preset(name)
        else:
            self.combo_preset.setCurrentIndex(max(0, self.combo_preset.findData(self.active_preset)))

    def _activate_preset_index(self, index: int) -> None:
        if 0 <= index < len(self.presets):
            self.activate_preset(self.presets[index].name)

    def activate_preset(self, name: str) -> None:
        if self._job is not None:
            return
        displays = copy.deepcopy(self.displays)

        def done(_preset) -> None:  # noqa: ANN001
            self.log(translate("MainWindow", "Preset '{name}' activated.").format(name=name))
            self.refresh_presets()
            self.refresh_displays()

        self._run_task(lambda: self.preset_manager.apply_preset(name, displays=displays), done,
                       translate("MainWindow", "Preset Error"))

    def action_capture_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            translate("MainWindow", "Save Preset"),
            translate("MainWindow", "Name for the new/updated preset:"),
            text=self.active_preset,
        )
        if not ok or not name.strip():
            return

        def done(preset) -> None:  # noqa: ANN001
            self.log(translate("MainWindow", "Preset '{name}' saved.").format(name=preset.name))
            self.refresh_presets()

        self._run_task(
            lambda: self.preset_manager.capture_current_state(name=name.strip(), mark_active=True),
            done,
            translate("MainWindow", "Preset Error"),
        )

    def _edit_preset(self, fn) -> None:  # noqa: ANN001
        try:
            fn()
        except ValueError as exc:
            QMessageBox.warning(self, translate("MainWindow", "Preset Error"), str(exc))
        self.refresh_presets()

    def action_duplicate_preset(self, name: str) -> None:
        new, ok = QInputDialog.getText(self, translate("MainWindow", "Duplicate Preset"),
                                       translate("MainWindow", "Name of the copy:"),
                                       text=translate("MainWindow", "{name} (copy)").format(name=name))
        if ok:
            self._edit_preset(lambda: self.preset_manager.duplicate_preset(name, new))

    def action_rename_preset(self, name: str) -> None:
        new, ok = QInputDialog.getText(self, translate("MainWindow", "Rename Preset"),
                                       translate("MainWindow", "New name:"), text=name)
        if ok and new.strip() != name:
            self._edit_preset(lambda: self.preset_manager.rename_preset(name, new))

    def action_delete_preset(self, name: str) -> None:
        answer = QMessageBox.question(self, translate("MainWindow", "Delete Preset"),
                                      translate("MainWindow", "Delete preset '{name}'?").format(name=name))
        if answer == QMessageBox.StandardButton.Yes:
            self._edit_preset(lambda: self.preset_manager.delete_preset(name))

    def action_recalibrate(self, connector: str) -> None:
        self._recalibrate_preset = self.page_presets.selected_name()
        self.select_display(connector)
        self._show_nav(NAV_MONITORS)

    # ------------------------------------------------------------------ calibration jobs

    def _set_job_running(self, running: bool) -> None:
        self.nav.setEnabled(not running)
        self.combo_preset.setEnabled(not running)
        self.mode_switch.setEnabled(not running)
        for act in (self.act_open, self.act_refresh, self.act_test_patch, *self.nav_actions):
            act.setEnabled(not running)
        self.act_cancel.setEnabled(running)
        self.page_simple.set_busy(running)
        self.page_expert.set_busy(running)
        self.page_presets.set_busy(running)

    def _start_job(self, job, on_success, error_title: str, subtitle: str, phases: tuple[str, ...],  # noqa: ANN001
                   contrast_range: tuple[int, int] = (40, 90)) -> None:
        """Starts a calibration job for the selected display in a worker thread and shows the run page."""
        disp = self.selected_display()
        if disp is None or self._job is not None:
            return
        cancel = CancelToken()
        try:
            patch = QtPatchDisplay(disp.connector, cancel)
        except RuntimeError as exc:
            QMessageBox.critical(self, error_title, str(exc))
            return

        run = self.page_running
        observer = QtCalibrationObserver(self)
        observer.status_changed.connect(self.page_expert.log.append)
        observer.status_changed.connect(run.on_status)
        observer.phase_begun.connect(run.on_phase_started)
        observer.phase_done.connect(run.on_phase_finished)
        observer.progress_changed.connect(run.on_progress)
        observer.patch_shown.connect(run.on_patch)
        observer.contrast_step_measured.connect(run.on_contrast_step)
        observer.contrast_step_measured.connect(
            lambda s: self.log(
                f"  K={s.contrast}% -> Y={s.m_high.Y:.2f} cd/m², "
                f"ΔL={s.delta_l_cdm2:.2f} cd/m², Δu'v'={s.delta_uv:.4f} ({s.reason})"
            )
        )
        observer.whitepoint_measured.connect(run.on_whitepoint)
        observer.whitepoint_measured.connect(
            lambda m, ddc: self.log(
                f"  DDC {tuple(ddc)} -> Y={m.Y:6.2f} cd/m² | xy=({m.xy[0]:.4f}, {m.xy[1]:.4f}) | "
                f"CCT={m.cct_kelvin:.0f} K | Δu'v'(D65)={m.delta_uv_to_d65():.4f}"
            )
        )

        controller = CalibrationController(
            display=disp,
            compositor=self.compositor,
            patch_display=patch,
            observer=observer,
            cancel=cancel,
            ddc_client=self.ddc_client,
        )
        thread = CalibrationThread(controller, job, self)

        def succeeded(result) -> None:  # noqa: ANN001
            run.finish("ok")
            on_success(result)

        def failed(msg: str) -> None:
            run.finish("failed", msg)
            QMessageBox.critical(self, error_title, msg)

        def cancelled() -> None:
            run.finish("cancelled")
            self.log(translate("MainWindow", "Cancelled by user."))

        thread.succeeded.connect(succeeded)
        thread.failed.connect(failed)
        thread.cancelled.connect(cancelled)
        thread.finished.connect(self._on_job_finished)

        self._job, self._job_cancel, self._job_patch, self._job_observer = thread, cancel, patch, observer
        run.begin(subtitle, disp.connector, phases, contrast_range)
        self.page_title.setText(translate("MainWindow", "Calibration"))
        self.mode_switch.hide()
        self.stack.setCurrentWidget(run)
        self._set_job_running(True)
        thread.start()

    def _on_job_finished(self) -> None:
        if self._job_patch is not None:
            self._job_patch.dispose()
        if self._job is not None:
            self._job.deleteLater()
        if self._job_observer is not None:
            self._job_observer.deleteLater()
        self._job = self._job_cancel = self._job_patch = self._job_observer = None
        self._set_job_running(False)
        self.refresh_displays()

    def action_cancel_job(self) -> None:
        if self._job_cancel is not None:
            self.log(translate("MainWindow", "Cancelling..."))
            self._job_cancel.resume()
            self._job_cancel.cancel()

    def _on_pause(self, paused: bool) -> None:
        if self._job_cancel is None:
            return
        if paused:
            self._job_cancel.pause()
            self.log(translate("MainWindow", "Paused after the current measurement."))
        else:
            self._job_cancel.resume()
            self.log(translate("MainWindow", "Resumed."))

    def _subtitle(self, disp: DisplayInfo, what: str) -> str:
        return f"{disp.model} ({disp.connector}) · {what}"

    def action_run_target(self, connector: str, target: CalibrationTarget) -> None:
        """Simple mode: full calibration 1a → 1b → 2 → 3 for a purpose template."""
        self.select_display(connector)
        disp = self.selected_display()
        if disp is None:
            return
        contrast_cfg = ContrastOptimizationConfig()
        params = self.page_expert.parameters()
        profile_cfg = params.profile_config(disp)
        profile_cfg.patch_count = target.patch_count
        profile_cfg.gamma = target.gamma
        subtitle = self._subtitle(disp, f"{target.display_title} · {target.luminance:.0f} cd/m² · "
                                        f"{target.whitepoint_label}")
        self._start_job(
            lambda ctl: ctl.run_full(contrast_cfg, target.luminance, profile_cfg, target.whitepoint_xy),
            lambda res: self._review_profile(disp, res.profiling, target),
            translate("MainWindow", "Calibration Error"),
            subtitle,
            ("1a", "1b", "2", "3"),
            (contrast_cfg.min_contrast, contrast_cfg.max_contrast),
        )

    def _on_expert_phase(self, phase: str) -> None:
        disp = self.selected_display()
        if disp is None:
            return
        if phase == PHASE_TEST:
            self.action_test_patch_window()
            return
        p = self.page_expert.parameters()
        rng = (p.contrast.min_contrast, p.contrast.max_contrast)
        if phase == PHASE_1A:
            self._start_job(lambda ctl: ctl.run_contrast(p.contrast), lambda _r: None,
                            translate("MainWindow", "Contrast Optimizer Error"),
                            self._subtitle(disp, translate("MainWindow", "Phase 1a")), ("1a",), rng)
        elif phase == PHASE_1B:
            self._start_job(lambda ctl: ctl.run_whitepoint(p.luminance, p.whitepoint_xy), lambda _r: None,
                            translate("MainWindow", "Whitepoint Optimizer Error"),
                            self._subtitle(disp, translate("MainWindow", "Phase 1b")), ("1b",), rng)
        elif phase == PHASE_23:
            cfg = p.profile_config(disp)
            target = self.page_expert.current_target()
            self._start_job(lambda ctl: ctl.run_profiling(cfg), lambda res: self._review_profile(disp, res, target),
                            translate("MainWindow", "Profiling Error"),
                            self._subtitle(disp, translate("MainWindow", "Phase 2+3")), ("2", "3"), rng)
        elif phase == PHASE_ALL:
            cfg = p.profile_config(disp)
            target = self.page_expert.current_target()

            def done(res: FullCalibrationResult) -> None:
                self._review_profile(disp, res.profiling, target)

            self._start_job(lambda ctl: ctl.run_full(p.contrast, p.luminance, cfg, p.whitepoint_xy), done,
                            translate("MainWindow", "Calibration Error"),
                            self._subtitle(disp, translate("MainWindow", "All phases")), ("1a", "1b", "2", "3"), rng)

    def action_test_patch_window(self) -> None:
        disp = self.selected_display()
        if disp is None or self._test_window is not None or self._job is not None:
            return
        try:
            win = WaylandPatchWindow(connector=disp.connector)
        except RuntimeError as exc:
            QMessageBox.critical(self, translate("MainWindow", "Patch Window"), str(exc))
            return
        self.log(translate("MainWindow", "Opening Wayland fullscreen patch window on {display_label}...").format(
            display_label=disp.display_label))

        def close() -> None:
            if self._test_window is win:
                self._test_window = None
                win.hide()
                win.deleteLater()

        win.confirmed.connect(close)
        win.aborted.connect(close)
        self._test_window = win
        win.show_placement(
            translate("MainWindow", "Test patch window") + "\n" + disp.display_label,
            hints=[(translate("MainWindow", "Space / Esc"), translate("MainWindow", "Close"))],
        )

    # ------------------------------------------------------------------ profiles

    def _review_profile(self, disp: DisplayInfo, res: ProfilingResult,
                        target: CalibrationTarget | None = None) -> None:
        """Opens the inspector for a freshly staged (and already active) profile."""
        preselect, self._recalibrate_preset = self._recalibrate_preset, ""
        dlg = InspectorDialog(
            inspection=res.inspection,
            connector=disp.connector,
            compositor=self.compositor,
            staged_profile=res.staged,
            previous_icc_path=res.previous_icc_path,
            previous_source=res.previous_source,
            display=disp,
            target=target,
            presets=[p.name for p in self.presets],
            preset_preselect=preselect,
            parent=self,
        )
        if dlg.exec() == InspectorDialog.DialogCode.Accepted and dlg.saved_profile_path:
            self.log(translate("MainWindow", "✓ ICC profile saved: {saved_profile_path}")
                     .format(saved_profile_path=dlg.saved_profile_path))
        else:
            self.log(translate("MainWindow", "ICC profile discarded; previous profile restored."))
        preset = dlg.preset_to_update
        saved = dlg.saved_profile_path
        if preset and saved:
            self.refresh_displays(then=lambda: self._update_preset_display(preset, disp.connector, str(saved)))
        else:
            self.refresh_displays()

    def _update_preset_display(self, preset: str, connector: str, icc_path: str) -> None:
        """Writes the live DDC values and the new profile of one display into `preset`."""
        disp = next((d for d in self.displays if d.connector == connector), None)
        if disp is None:
            return
        self._edit_preset(lambda: self.preset_manager.update_display(preset, disp, icc_path))
        self.log(translate("MainWindow", "Preset '{preset}' updated for {connector}.").format(
            preset=preset, connector=connector))
        self._update_displays_ui()

    def inspect_display_profile(self, connector: str) -> None:
        disp = next((d for d in self.displays if d.connector == connector), None)
        if disp and disp.icc_profile_path and Path(disp.icc_profile_path).exists():
            self.open_inspector(disp.icc_profile_path, disp)
        else:
            self.action_open_profile()

    def action_open_profile(self) -> None:
        picked, _ = QFileDialog.getOpenFileName(
            self,
            translate("MainWindow", "Select ICC Profile to Inspect"),
            str(user_icc_dir()),
            translate("MainWindow", "ICC Profiles (*.icc *.icm)"),
        )
        if picked:
            self.open_inspector(picked)

    def open_inspector(self, icc_file: str, disp: DisplayInfo | None = None) -> None:
        disp = disp or self.selected_display()
        try:
            inspection = inspect_profile(icc_file)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, translate("MainWindow", "Profile Inspector Error"), str(exc))
            return
        dlg = InspectorDialog(
            inspection=inspection,
            connector=disp.connector if disp else None,
            compositor=self.compositor,
            staged_profile=None,
            previous_icc_path=disp.icc_profile_path if disp else None,
            previous_source=disp.color_profile_source if disp else "sRGB",
            display=disp,
            parent=self,
        )
        dlg.exec()
        self.refresh_displays()

    def action_about(self) -> None:
        QMessageBox.about(
            self,
            translate("MainWindow", "About KelvinCal"),
            translate(
                "MainWindow",
                "<h3>KelvinCal</h3><p>Wayland-native display calibration: DDC/CI hardware optimizer, "
                "ArgyllCMS profiling and multi-monitor presets.</p><p>License: GPL-3.0-or-later · Uses ArgyllCMS "
                "(AGPL) as external tools.</p>",
            ),
        )
