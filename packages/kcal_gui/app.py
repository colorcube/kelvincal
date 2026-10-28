"""Graphical interface `kcal-gui` (Qt 6 / PySide6) for KelvinCal under Wayland."""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
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

from kcal_argyll.profile_pipeline import CalibrationPipeline, ProfileConfig
from kcal_argyll.spotread_session import SpotreadSession
from kcal_core.compositor import get_compositor_backend
from kcal_core.discovery import discover_displays
from kcal_core.i18n import tr
from kcal_core.models import DisplayInfo
from kcal_ddc.contrast_optimizer import ContrastOptimizationConfig, ContrastOptimizer
from kcal_ddc.ddc_client import DDCClient
from kcal_ddc.whitepoint_optimizer import WhitepointOptimizer
from kcal_gui.patch_window import WaylandPatchWindow
from kcal_presets.manager import PresetManager


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

        self._build_ui()
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
        btn_refresh = QPushButton(tr("Refresh Displays", "Monitore neu einlesen"))
        btn_refresh.clicked.connect(self.refresh_displays)
        top_bar.addWidget(QLabel(tr("Target Display:", "Ziel-Monitor:")))
        top_bar.addWidget(self.combo_monitor, stretch=1)
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

        btn_full_cal = QPushButton(
            tr(
                "Phase 2+3: Start ArgyllCMS Profiling",
                "Phase 2+3: ArgyllCMS Profilierung starten",
            )
        )
        btn_full_cal.clicked.connect(self.action_run_profiling)

        btn_row.addWidget(btn_test_patch)
        btn_row.addWidget(btn_opt_contrast)
        btn_row.addWidget(btn_opt_wp)
        btn_row.addWidget(btn_full_cal)
        cal_layout.addLayout(btn_row)

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
        self.setCentralWidget(splitter)

    def log(self, message: str) -> None:
        self.log_view.appendPlainText(message)
        QApplication.processEvents()

    def selected_display(self) -> DisplayInfo | None:
        idx = self.combo_monitor.currentIndex()
        if 0 <= idx < len(self.displays):
            return self.displays[idx]
        return None

    def _populate_monitors_table(self) -> None:
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

    def refresh_displays(self) -> None:
        self.log(
            tr(
                "Reading displays via DRM sysfs, ddcutil, and compositor...",
                "Lese Monitore über DRM-sysfs, ddcutil und KWin aus...",
            )
        )
        self.displays = discover_displays(compositor=self.compositor, include_ddc_values=True)
        self._populate_monitors_table()
        self.log(
            tr(
                f"{len(self.displays)} displays detected.",
                f"{len(self.displays)} Monitore erfolgreich erkannt.",
            )
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
            self.table_presets.setItem(row, 0, QTableWidgetItem(status))
            self.table_presets.setItem(row, 1, QTableWidgetItem(p.name))
            self.table_presets.setItem(row, 2, QTableWidgetItem(mons))

    def action_test_patch_window(self) -> None:
        disp = self.selected_display()
        if disp is None:
            return
        win = WaylandPatchWindow(connector=disp.connector)
        self.log(
            tr(
                f"Opening Wayland fullscreen patch window on {disp.display_label}...",
                f"Öffne Wayland-Vollbild-Patchfenster auf {disp.display_label}...",
            )
        )
        win.wait_for_sensor_placement(
            prompt_text=tr(
                f"Test Window on {disp.display_label} – [Space/Esc] to close",
                f"Testfenster auf {disp.display_label} – [Leertaste/Esc] zum Schließen",
            )
        )
        win.close()

    def action_optimize_contrast(self) -> None:
        disp = self.selected_display()
        if disp is None or disp.i2c_bus is None:
            return
        win = WaylandPatchWindow(connector=disp.connector)
        if not win.wait_for_sensor_placement():
            win.close()
            return

        cfg = ContrastOptimizationConfig(
            min_contrast=self.spin_min_c.value(),
            max_contrast=self.spin_max_c.value(),
        )
        opt = ContrastOptimizer(cfg)
        self.log(
            tr(
                f"Starting binary contrast search on {disp.display_label}...",
                f"Starte Kontrast-Binärsuche auf {disp.display_label}...",
            )
        )
        try:
            with self.compositor.calibration_guard(disp.connector):
                with SpotreadSession() as sensor:
                    res = opt.run(
                        set_contrast_fn=lambda k: self.ddc_client.set_contrast(disp.i2c_bus, k),  # type: ignore[arg-type]
                        measure_patch_fn=lambda rgb: sensor.measure_rgb(
                            rgb,
                            show_patch_fn=lambda c: win.set_patch_rgb(
                                c, status_text=f"Contrast Optimizer ({disp.connector})"
                            ),
                        ),
                        on_step=lambda s: self.log(
                            f"  K={s.contrast}% -> Y={s.m_high.Y:.2f} cd/m², "
                            f"ΔL={s.delta_l_cdm2:.2f} cd/m², Δu'v'={s.delta_uv:.4f} ({s.reason})"
                        ),
                    )
            self.log(
                tr(
                    f"✓ Optimal contrast for {disp.connector}: {res.optimal_contrast}% ({res.peak_luminance_cdm2:.1f} cd/m²)",
                    f"✓ Optimaler Kontrast für {disp.connector}: {res.optimal_contrast}% ({res.peak_luminance_cdm2:.1f} cd/m²)",
                )
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                tr("Contrast Optimizer Error", "Fehler beim Kontrast-Optimizer"),
                str(exc),
            )
        finally:
            win.close()
            self.refresh_displays()

    def action_optimize_whitepoint(self) -> None:
        disp = self.selected_display()
        if disp is None or disp.i2c_bus is None:
            return
        win = WaylandPatchWindow(connector=disp.connector)
        if not win.wait_for_sensor_placement():
            win.close()
            return

        wp = WhitepointOptimizer(target_luminance_cdm2=self.spin_luminance.value())
        self.log(
            tr(
                f"Starting D65 whitepoint & brightness regulation ({self.spin_luminance.value():.0f} cd/m²)...",
                f"Starte D65-Weißpunkt- & Helligkeitsregelung ({self.spin_luminance.value():.0f} cd/m²)...",
            )
        )
        try:
            with self.compositor.calibration_guard(disp.connector):
                with SpotreadSession() as sensor:
                    def _meas_wp():
                        m = sensor.measure_rgb(
                            (255, 255, 255),
                            show_patch_fn=lambda c: win.set_patch_rgb(
                                c, status_text=f"D65 Whitepoint ({disp.connector})"
                            ),
                        )
                        x, y = m.xy
                        self.log(
                            f"  Reading: Y={m.Y:6.2f} cd/m² | xy=({x:.4f}, {y:.4f}) | "
                            f"CCT={m.cct_kelvin:.0f} K | Δu'v'(D65)={m.delta_uv_to_d65():.4f}"
                        )
                        return m

                    res = wp.run(
                        initial_brightness=disp.ddc.brightness or 50,
                        initial_gains=(
                            disp.ddc.red_gain or 100,
                            disp.ddc.green_gain or 100,
                            disp.ddc.blue_gain or 100,
                        ),
                        apply_ddc_fn=lambda b, r, g, bl: self.ddc_client.set_vcp_values(
                            disp.i2c_bus,  # type: ignore[arg-type]
                            {"10": b, "16": r, "18": g, "1A": bl},
                        ),
                        measure_white_fn=_meas_wp,
                    )
            self.log(
                tr(
                    f"✓ Whitepoint regulated: Bri={res.brightness}%, RGB=({res.red_gain}, {res.green_gain}, {res.blue_gain}), "
                    f"Y={res.final_measurement.Y:.1f} cd/m², CCT={res.final_measurement.cct_kelvin:.0f} K",
                    f"✓ Weißpunkt eingeregelt: Bri={res.brightness}%, RGB=({res.red_gain}, {res.green_gain}, {res.blue_gain}), "
                    f"Y={res.final_measurement.Y:.1f} cd/m², CCT={res.final_measurement.cct_kelvin:.0f} K",
                )
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                tr("Whitepoint Optimizer Error", "Fehler bei Weißpunkt-Regelung"),
                str(exc),
            )
        finally:
            win.close()
            self.refresh_displays()

    def action_run_profiling(self) -> None:
        disp = self.selected_display()
        if disp is None:
            return
        win = WaylandPatchWindow(connector=disp.connector)
        if not win.wait_for_sensor_placement():
            win.close()
            return

        cfg = ProfileConfig(
            monitor_name=f"{disp.connector}_{disp.model}",
            patch_count=self.spin_patches.value(),
        )
        pipeline = CalibrationPipeline(cfg)
        try:
            with self.compositor.calibration_guard(disp.connector) as guard:
                icc_path = pipeline.generate_icc_profile(
                    update_patch_fn=lambda rgb, idx=0, total=0: win.set_patch_rgb(
                        rgb,
                        status_text=(
                            f"ArgyllCMS dispread ({disp.connector}) – Patch {idx}/{total}"
                            if total
                            else f"ArgyllCMS dispread ({disp.connector})"
                        ),
                    ),
                    on_status_fn=self.log,
                )
                self.compositor.apply_output_profile(
                    connector=disp.connector,
                    icc_profile_path=str(icc_path),
                    color_profile_source="ICC",
                    brightness=None,
                )
                guard.keep_new_profile = True
            self.log(
                tr(
                    f"✓ ICC profile generated and activated in compositor: {icc_path}",
                    f"✓ ICC-Profil erstellt und in KWin aktiviert: {icc_path}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                tr("Profiling Error", "Fehler bei der Profilierung"),
                str(exc),
            )
        finally:
            win.close()
            self.refresh_displays()

    def action_capture_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            tr("Save Preset", "Preset speichern"),
            tr("Name for the new/updated preset:", "Name für das neue/aktualisierte Preset:"),
        )
        if not ok or not name.strip():
            return
        preset = self.preset_manager.capture_current_state(name=name.strip(), mark_active=True)
        self.log(tr(f"Preset '{preset.name}' saved.", f"Preset '{preset.name}' gespeichert."))
        self.refresh_presets()

    def action_apply_selected_preset(self) -> None:
        row = self.table_presets.currentRow()
        if row < 0:
            return
        name_item = self.table_presets.item(row, 1)
        if name_item is None:
            return
        name = name_item.text()
        try:
            self.preset_manager.apply_preset(name, displays=self.displays)
            self.log(tr(f"Preset '{name}' activated.", f"Preset '{name}' aktiviert."))
            self._populate_monitors_table()
            self.refresh_presets()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("Preset Error", "Preset-Fehler"), str(exc))


def main() -> int:
    app = QApplication(sys.argv)
    win = KelvinCalMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
