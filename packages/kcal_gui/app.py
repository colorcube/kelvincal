"""Graphical interface `kcal-gui` (Qt 6 / PySide6) for KelvinCal under Wayland."""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kcal_argyll.profile_inspector import inspect_profile
from kcal_argyll.profile_pipeline import ProfileConfig
from kcal_core.compositor import get_compositor_backend
from kcal_core.discovery import discover_displays
from kcal_core.i18n import tr
from kcal_core.models import DisplayInfo
from kcal_core.paths import user_icc_dir
from kcal_ddc.contrast_optimizer import ContrastOptimizationConfig
from kcal_ddc.ddc_client import DDCClient
from kcal_gui.controller import (
    CalibrationController,
    CancelToken,
    FullCalibrationResult,
    ProfilingResult,
)
from kcal_gui.patch_window import WaylandPatchWindow
from kcal_gui.profile_review_dialog import ProfileReviewDialog
from kcal_gui.workers import CalibrationThread, QtCalibrationObserver, QtPatchDisplay, TaskThread
from kcal_presets.manager import PresetManager

APP_ID = "org.kde.kelvincal"


class KelvinCalMainWindow(QMainWindow):
    """Main window for display diagnostics, contrast/whitepoint optimization, profiling, and presets."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(
            tr(
                "KelvinCal – Wayland Color Management & Hardware Calibration",
                "KelvinCal – Wayland Farbmanagement & Hardware-Kalibrierung",
            )
        )
        self.resize(1020, 720)

        self.compositor = get_compositor_backend()
        self.ddc_client = DDCClient()
        self.preset_manager = PresetManager(
            compositor=self.compositor, ddc_client=self.ddc_client
        )
        self.displays: list[DisplayInfo] = []
        self._job: CalibrationThread | None = None
        self._job_cancel: CancelToken | None = None
        self._job_patch: QtPatchDisplay | None = None
        self._tasks: set[TaskThread] = set()
        self._test_window: WaylandPatchWindow | None = None

        self._build_ui()
        self._restore_settings()
        self.refresh_displays()
        self.refresh_presets()

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.tabs = QTabWidget()

        # Tab 1: Displays & Calibration
        tab_cal = QWidget()
        cal_layout = QVBoxLayout(tab_cal)

        top_bar = QHBoxLayout()
        self.combo_monitor = QComboBox()
        btn_inspect_icc = QPushButton(
            tr("Inspect ICC Profile (Curves)...", "ICC-Profil prüfen (Kurven)...")
        )
        btn_inspect_icc.clicked.connect(self.action_inspect_profile)
        btn_refresh = QPushButton(tr("Refresh Displays", "Monitore neu einlesen"))
        btn_refresh.clicked.connect(self.refresh_displays)
        top_bar.addWidget(QLabel(tr("Target Display:", "Ziel-Monitor:")))
        top_bar.addWidget(self.combo_monitor, stretch=1)
        top_bar.addWidget(btn_inspect_icc)
        top_bar.addWidget(btn_refresh)
        cal_layout.addLayout(top_bar)

        self.table_monitors = QTableWidget(0, 7)
        self.table_monitors.setHorizontalHeaderLabels(
            [
                "Connector",
                tr("Model & S/N", "Modell & S/N"),
                "I²C Bus",
                tr("DDC Brightness", "DDC Helligkeit"),
                tr("DDC Contrast", "DDC Kontrast"),
                tr("DDC RGB Gains", "DDC RGB-Gains"),
                tr("Active ICC Profile", "Aktives ICC-Profil (KWin)"),
            ]
        )
        self.table_monitors.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table_monitors.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_monitors.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_monitors.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_monitors.currentCellChanged.connect(
            lambda row, *_: self.combo_monitor.setCurrentIndex(row) if row >= 0 else None
        )
        self.combo_monitor.currentIndexChanged.connect(
            lambda idx: self.table_monitors.selectRow(idx) if idx >= 0 else None
        )
        cal_layout.addWidget(self.table_monitors)

        # Parameters for Phases 1–3
        grp_params = QGroupBox(
            tr("Calibration & Optimizer Parameters", "Kalibrierungs- & Optimizer-Parameter")
        )
        form = QFormLayout(grp_params)

        self.spin_luminance = QDoubleSpinBox()
        self.spin_luminance.setRange(60.0, 400.0)
        self.spin_luminance.setValue(140.0)
        self.spin_luminance.setSuffix(" cd/m²")

        self.spin_min_c = QSpinBox()
        self.spin_min_c.setRange(20, 80)
        self.spin_min_c.setValue(40)

        self.spin_max_c = QSpinBox()
        self.spin_max_c.setRange(50, 100)
        self.spin_max_c.setValue(90)

        self.spin_patches = QSpinBox()
        self.spin_patches.setRange(50, 1000)
        self.spin_patches.setValue(175)

        form.addRow(tr("Target Luminance (D65):", "Ziel-Luminanz (D65):"), self.spin_luminance)
        form.addRow(
            tr("Contrast Search Range (Min %):", "Kontrast-Suchbereich (Min %):"),
            self.spin_min_c,
        )
        form.addRow(
            tr("Contrast Search Range (Max %):", "Kontrast-Suchbereich (Max %):"),
            self.spin_max_c,
        )
        form.addRow(
            tr("Patch Count (targen):", "Anzahl Messfelder (targen):"),
            self.spin_patches,
        )
        cal_layout.addWidget(grp_params)

        # Action buttons for Phases 1–3
        btn_row = QHBoxLayout()
        btn_test_patch = QPushButton(tr("Test Patch Window", "Patch-Fenster testen"))
        btn_test_patch.clicked.connect(self.action_test_patch_window)

        btn_opt_contrast = QPushButton(
            tr(
                "Phase 1a: Contrast Optimizer (Binary Search)",
                "Phase 1a: Kontrast-Optimizer (Binärsuche)",
            )
        )
        btn_opt_contrast.clicked.connect(self.action_optimize_contrast)

        btn_opt_wp = QPushButton(
            tr(
                "Phase 1b: D65 Whitepoint & Brightness (DDC)",
                "Phase 1b: D65 Weißpunkt & Helligkeit (DDC)",
            )
        )
        btn_opt_wp.clicked.connect(self.action_optimize_whitepoint)

        btn_profiling = QPushButton(
            tr(
                "Phase 2+3: Start ArgyllCMS Profiling",
                "Phase 2+3: ArgyllCMS Profilierung starten",
            )
        )
        btn_profiling.clicked.connect(self.action_run_profiling)

        btn_all = QPushButton(tr("Run All Phases", "Alle Phasen ausführen"))
        btn_all.clicked.connect(self.action_run_full)

        self.btn_cancel = QPushButton(tr("Cancel", "Abbrechen"))
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.action_cancel_job)

        btn_row.addWidget(btn_test_patch)
        btn_row.addWidget(btn_opt_contrast)
        btn_row.addWidget(btn_opt_wp)
        btn_row.addWidget(btn_profiling)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(self.btn_cancel)
        cal_layout.addLayout(btn_row)
        # Widgets locked while a measurement job runs (prevents a second concurrent run).
        self._job_locked_widgets: list[QWidget] = [
            self.combo_monitor, btn_inspect_icc, btn_refresh, grp_params,
            btn_test_patch, btn_opt_contrast, btn_opt_wp, btn_profiling, btn_all,
        ]

        self.tabs.addTab(
            tab_cal,
            tr("1. Hardware Optimizer & Calibration", "1. Hardware-Optimizer & Kalibrierung"),
        )

        # Tab 2: Presets
        tab_presets = QWidget()
        preset_layout = QVBoxLayout(tab_presets)

        self.table_presets = QTableWidget(0, 3)
        self.table_presets.setHorizontalHeaderLabels(
            [
                "Status",
                tr("Preset Name", "Preset-Name"),
                tr("Configured Displays", "Konfigurierte Monitore"),
            ]
        )
        self.table_presets.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        preset_layout.addWidget(self.table_presets)

        preset_btns = QHBoxLayout()
        btn_capture = QPushButton(
            tr(
                "Save Current State as Preset...",
                "Aktuellen Ist-Zustand als Preset speichern...",
            )
        )
        btn_capture.clicked.connect(self.action_capture_preset)

        btn_apply = QPushButton(
            tr("Activate Selected Preset", "Ausgewähltes Preset aktivieren")
        )
        btn_apply.clicked.connect(self.action_apply_selected_preset)
        self._job_locked_widgets += [btn_capture, btn_apply]

        preset_btns.addWidget(btn_capture)
        preset_btns.addWidget(btn_apply)
        preset_layout.addLayout(preset_btns)

        self.tabs.addTab(
            tab_presets,
            tr("2. Display Presets (Multi-Monitor)", "2. Display-Presets (Multi-Monitor)"),
        )

        # Log console
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText(
            tr("Measurement and diagnostic log...", "Mess- und Diagnoseprotokoll...")
        )

        splitter.addWidget(self.tabs)
        splitter.addWidget(self.log_view)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        self.splitter = splitter
        self.setCentralWidget(splitter)

    # ------------------------------------------------------------------ settings

    def _restore_settings(self) -> None:
        st = QSettings()
        geometry = st.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        splitter_state = st.value("window/splitter")
        if splitter_state is not None:
            self.splitter.restoreState(splitter_state)
        self.spin_luminance.setValue(float(st.value("params/luminance", self.spin_luminance.value())))
        self.spin_min_c.setValue(int(st.value("params/contrast_min", self.spin_min_c.value())))
        self.spin_max_c.setValue(int(st.value("params/contrast_max", self.spin_max_c.value())))
        self.spin_patches.setValue(int(st.value("params/patches", self.spin_patches.value())))
        self._last_connector = str(st.value("params/connector", ""))

    def _save_settings(self) -> None:
        st = QSettings()
        st.setValue("window/geometry", self.saveGeometry())
        st.setValue("window/splitter", self.splitter.saveState())
        st.setValue("params/luminance", self.spin_luminance.value())
        st.setValue("params/contrast_min", self.spin_min_c.value())
        st.setValue("params/contrast_max", self.spin_max_c.value())
        st.setValue("params/patches", self.spin_patches.value())
        disp = self.selected_display()
        if disp is not None:
            st.setValue("params/connector", disp.connector)

    def closeEvent(self, event) -> None:  # noqa: ANN001
        if self._job is not None:
            answer = QMessageBox.question(
                self,
                tr("Calibration running", "Kalibrierung läuft"),
                tr(
                    "A measurement is still running. Cancel it and quit?",
                    "Eine Messung läuft noch. Abbrechen und beenden?",
                ),
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
        self.log_view.appendPlainText(message)

    def selected_display(self) -> DisplayInfo | None:
        idx = self.combo_monitor.currentIndex()
        if 0 <= idx < len(self.displays):
            return self.displays[idx]
        return None

    def _run_task(self, fn, on_success, error_title: str) -> None:  # noqa: ANN001
        """Runs `fn` in a background thread; `on_success(result)` is called in the GUI thread."""
        task = TaskThread(fn, self)
        self._tasks.add(task)
        task.succeeded.connect(on_success)
        task.failed.connect(lambda msg: QMessageBox.critical(self, error_title, msg))
        task.finished.connect(lambda: (self._tasks.discard(task), task.deleteLater()))
        task.start()

    def _populate_monitors_table(self) -> None:
        previous = self.selected_display()
        wanted = previous.connector if previous else getattr(self, "_last_connector", "")
        self.combo_monitor.blockSignals(True)
        self.combo_monitor.clear()
        self.table_monitors.setRowCount(len(self.displays))

        for row, d in enumerate(self.displays):
            self.combo_monitor.addItem(d.display_label, userData=d.connector)
            icc_name = Path(d.icc_profile_path).name if d.icc_profile_path else "sRGB"
            rgb_str = f"R={d.ddc.red_gain} G={d.ddc.green_gain} B={d.ddc.blue_gain}"
            cells = [
                d.connector,
                f"{d.model} ({d.serial})",
                f"/dev/i2c-{d.i2c_bus}" if d.i2c_bus is not None else "n/a",
                f"{d.ddc.brightness}%",
                f"{d.ddc.contrast}%",
                rgb_str,
                f"[{d.color_profile_source}] {icc_name}",
            ]
            for col, text in enumerate(cells):
                self.table_monitors.setItem(row, col, QTableWidgetItem(text))
        idx = self.combo_monitor.findData(wanted)
        self.combo_monitor.blockSignals(False)
        self.combo_monitor.setCurrentIndex(max(0, idx))

    def refresh_displays(self) -> None:
        self.log(
            tr(
                "Reading displays via DRM sysfs, ddcutil, and compositor...",
                "Lese Monitore über DRM-sysfs, ddcutil und KWin aus...",
            )
        )

        def done(displays: list[DisplayInfo]) -> None:
            self.displays = displays
            self._populate_monitors_table()
            self.log(
                tr(
                    f"{len(self.displays)} displays detected.",
                    f"{len(self.displays)} Monitore erfolgreich erkannt.",
                )
            )

        self._run_task(
            lambda: discover_displays(compositor=self.compositor, include_ddc_values=True),
            done,
            tr("Display Detection Error", "Fehler bei der Monitorerkennung"),
        )

    def refresh_presets(self) -> None:
        active_name, presets = self.preset_manager.load_all()
        self.table_presets.setRowCount(len(presets))
        for row, p in enumerate(presets):
            status = (
                tr("● Active", "● Aktiv")
                if p.name == active_name
                else tr("○ Ready", "○ Bereit")
            )
            mons = ", ".join(
                f"{e.connector or e.edid_hash[:6]} ({e.ddc_brightness}%/{e.ddc_contrast}%)"
                for e in p.displays
            )
            name_item = QTableWidgetItem(p.name)
            name_item.setData(Qt.ItemDataRole.UserRole, p.name)
            self.table_presets.setItem(row, 0, QTableWidgetItem(status))
            self.table_presets.setItem(row, 1, name_item)
            self.table_presets.setItem(row, 2, QTableWidgetItem(mons))

    # ------------------------------------------------------------------ calibration jobs

    def _set_job_running(self, running: bool) -> None:
        for w in self._job_locked_widgets:
            w.setEnabled(not running)
        self.btn_cancel.setEnabled(running)

    def _start_job(self, job, on_success, error_title: str) -> None:  # noqa: ANN001
        """Starts a calibration job for the selected display in a worker thread."""
        disp = self.selected_display()
        if disp is None or self._job is not None:
            return
        cancel = CancelToken()
        try:
            patch = QtPatchDisplay(disp.connector, cancel)
        except RuntimeError as exc:
            QMessageBox.critical(self, error_title, str(exc))
            return

        observer = QtCalibrationObserver(self)
        observer.status_changed.connect(self.log)
        observer.contrast_step_measured.connect(
            lambda s: self.log(
                f"  K={s.contrast}% -> Y={s.m_high.Y:.2f} cd/m², "
                f"ΔL={s.delta_l_cdm2:.2f} cd/m², Δu'v'={s.delta_uv:.4f} ({s.reason})"
            )
        )
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
        thread.succeeded.connect(on_success)
        thread.failed.connect(lambda msg: QMessageBox.critical(self, error_title, msg))
        thread.cancelled.connect(
            lambda: self.log(tr("Cancelled by user.", "Vom Benutzer abgebrochen."))
        )
        thread.finished.connect(self._on_job_finished)

        self._job, self._job_cancel, self._job_patch = thread, cancel, patch
        self._job_observer = observer
        self._set_job_running(True)
        thread.start()

    def _on_job_finished(self) -> None:
        if self._job_patch is not None:
            self._job_patch.dispose()
        if self._job is not None:
            self._job.deleteLater()
        self._job_observer.deleteLater()
        self._job = self._job_cancel = self._job_patch = None
        self._set_job_running(False)
        self.refresh_displays()

    def action_cancel_job(self) -> None:
        if self._job_cancel is not None:
            self.log(tr("Cancelling...", "Breche ab..."))
            self._job_cancel.cancel()

    def _contrast_config(self) -> ContrastOptimizationConfig:
        return ContrastOptimizationConfig(
            min_contrast=self.spin_min_c.value(),
            max_contrast=self.spin_max_c.value(),
        )

    def _profile_config(self, disp: DisplayInfo) -> ProfileConfig:
        return ProfileConfig(
            monitor_name=f"{disp.connector}_{disp.model}",
            patch_count=self.spin_patches.value(),
        )

    def action_test_patch_window(self) -> None:
        disp = self.selected_display()
        if disp is None or self._test_window is not None:
            return
        try:
            win = WaylandPatchWindow(connector=disp.connector)
        except RuntimeError as exc:
            QMessageBox.critical(self, tr("Patch Window", "Patch-Fenster"), str(exc))
            return
        self.log(
            tr(
                f"Opening Wayland fullscreen patch window on {disp.display_label}...",
                f"Öffne Wayland-Vollbild-Patchfenster auf {disp.display_label}...",
            )
        )

        def close() -> None:
            if self._test_window is win:
                self._test_window = None
                win.hide()
                win.deleteLater()

        win.confirmed.connect(close)
        win.aborted.connect(close)
        self._test_window = win
        win.show_placement(
            tr(
                f"Test Window on {disp.display_label} – [Space/Esc] to close",
                f"Testfenster auf {disp.display_label} – [Leertaste/Esc] zum Schließen",
            )
        )

    def action_optimize_contrast(self) -> None:
        cfg = self._contrast_config()
        self._start_job(
            lambda ctl: ctl.run_contrast(cfg),
            lambda _res: None,
            tr("Contrast Optimizer Error", "Fehler beim Kontrast-Optimizer"),
        )

    def action_optimize_whitepoint(self) -> None:
        lum = self.spin_luminance.value()
        self._start_job(
            lambda ctl: ctl.run_whitepoint(lum),
            lambda _res: None,
            tr("Whitepoint Optimizer Error", "Fehler bei Weißpunkt-Regelung"),
        )

    def action_run_profiling(self) -> None:
        disp = self.selected_display()
        if disp is None:
            return
        cfg = self._profile_config(disp)
        self._start_job(
            lambda ctl: ctl.run_profiling(cfg),
            lambda res: self._review_profile(disp, res),
            tr("Profiling Error", "Fehler bei der Profilierung"),
        )

    def action_run_full(self) -> None:
        disp = self.selected_display()
        if disp is None:
            return
        contrast_cfg = self._contrast_config()
        lum = self.spin_luminance.value()
        profile_cfg = self._profile_config(disp)

        def done(res: FullCalibrationResult) -> None:
            self._review_profile(disp, res.profiling)

        self._start_job(
            lambda ctl: ctl.run_full(contrast_cfg, lum, profile_cfg),
            done,
            tr("Calibration Error", "Fehler bei der Kalibrierung"),
        )

    def _review_profile(self, disp: DisplayInfo, res: ProfilingResult) -> None:
        """Opens the review dialog for a freshly staged (and already active) profile."""
        dlg = ProfileReviewDialog(
            inspection=res.inspection,
            connector=disp.connector,
            compositor=self.compositor,
            staged_profile=res.staged,
            previous_icc_path=res.previous_icc_path,
            previous_source=res.previous_source,
            parent=self,
        )
        if dlg.exec() == ProfileReviewDialog.DialogCode.Accepted and dlg.saved_profile_path:
            self.log(
                tr(
                    f"✓ ICC profile saved and activated in compositor: {dlg.saved_profile_path}",
                    f"✓ ICC-Profil gespeichert und im Compositor aktiviert: {dlg.saved_profile_path}",
                )
            )
        else:
            self.log(
                tr(
                    "ICC profile discarded; previous profile restored.",
                    "ICC-Profil verworfen; vorheriges Profil wiederhergestellt.",
                )
            )
        self.refresh_displays()

    def action_inspect_profile(self) -> None:
        disp = self.selected_display()
        icc_file: str | None = None
        if disp is not None and disp.icc_profile_path and Path(disp.icc_profile_path).exists():
            icc_file = disp.icc_profile_path
        else:
            default_dir = str(user_icc_dir())
            picked, _ = QFileDialog.getOpenFileName(
                self,
                tr("Select ICC Profile to Inspect", "Zu prüfendes ICC-Profil auswählen"),
                default_dir,
                "ICC Profiles (*.icc *.icm)",
            )
            if picked:
                icc_file = picked

        if not icc_file:
            return

        try:
            inspection = inspect_profile(icc_file)
            dlg = ProfileReviewDialog(
                inspection=inspection,
                connector=disp.connector if disp else None,
                compositor=self.compositor,
                staged_profile=None,
                previous_icc_path=disp.icc_profile_path if disp else None,
                previous_source=disp.color_profile_source if disp else "sRGB",
                parent=self,
            )
            dlg.exec()
            self.refresh_displays()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                tr("Profile Inspector Error", "Fehler beim Profil-Inspektor"),
                str(exc),
            )

    # ------------------------------------------------------------------ presets

    def action_capture_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            tr("Save Preset", "Preset speichern"),
            tr("Name for the new/updated preset:", "Name für das neue/aktualisierte Preset:"),
        )
        if not ok or not name.strip():
            return

        def done(preset) -> None:  # noqa: ANN001
            self.log(tr(f"Preset '{preset.name}' saved.", f"Preset '{preset.name}' gespeichert."))
            self.refresh_presets()

        self._run_task(
            lambda: self.preset_manager.capture_current_state(name=name.strip(), mark_active=True),
            done,
            tr("Preset Error", "Preset-Fehler"),
        )

    def action_apply_selected_preset(self) -> None:
        row = self.table_presets.currentRow()
        item = self.table_presets.item(row, 1) if row >= 0 else None
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        displays = list(self.displays)

        def done(_preset) -> None:  # noqa: ANN001
            self.log(tr(f"Preset '{name}' activated.", f"Preset '{name}' aktiviert."))
            self.refresh_presets()
            self.refresh_displays()

        self._run_task(
            lambda: self.preset_manager.apply_preset(name, displays=displays),
            done,
            tr("Preset Error", "Preset-Fehler"),
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("kelvincal")
    app.setApplicationDisplayName("KelvinCal")
    app.setOrganizationDomain("kde.org")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme("preferences-desktop-display-color"))
    win = KelvinCalMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
