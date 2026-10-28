"""Interactive ICC Profile Inspector ('Knick-Check' curve viewer) and Live A/B Preview dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from kcal_argyll.profile_inspector import ProfileInspection, inspect_profile
from kcal_argyll.profile_pipeline import StagedProfile
from kcal_core.compositor.base import CompositorBackend
from kcal_core.i18n import tr


class ProfileCurveWidget(QWidget):
    """Custom QPainter widget rendering RGB tone response curves, .ti3 points, and kink markers."""

    MODE_TRC = 0
    MODE_DEVIATION = 1

    def __init__(
        self, inspection: ProfileInspection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.inspection = inspection
        self.view_mode = self.MODE_TRC
        self.setMinimumSize(640, 340)

    def set_inspection(self, inspection: ProfileInspection) -> None:
        self.inspection = inspection
        self.update()

    def set_view_mode(self, mode: int) -> None:
        self.view_mode = mode
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()
        painter.fillRect(rect, QColor("#14171c"))

        margin_left = 58.0
        margin_right = 24.0
        margin_top = 28.0
        margin_bottom = 42.0

        plot_rect = QRectF(
            margin_left,
            margin_top,
            max(10.0, rect.width() - margin_left - margin_right),
            max(10.0, rect.height() - margin_top - margin_bottom),
        )

        # Draw grid and axes
        grid_pen = QPen(QColor("#282e38"), 1.0, Qt.PenStyle.DotLine)
        axis_pen = QPen(QColor("#4c566a"), 1.2)
        text_pen = QPen(QColor("#b8c0cc"))
        small_font = QFont("Sans Serif", 8)
        painter.setFont(small_font)

        for i in range(11):
            frac = i / 10.0
            x = plot_rect.left() + frac * plot_rect.width()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(x, plot_rect.top()), QPointF(x, plot_rect.bottom()))
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(x - 20, plot_rect.bottom() + 4, 40, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{int(frac * 100)}%",
            )

        if self.view_mode == self.MODE_TRC:
            self._paint_trc_mode(painter, plot_rect, grid_pen, text_pen)
        else:
            self._paint_deviation_mode(painter, plot_rect, grid_pen, text_pen)

        # Plot border
        painter.setPen(axis_pen)
        painter.drawRect(plot_rect)

        # Highlight any detected kinks with vertical warning markers
        for kink in self.inspection.kinks:
            kx = plot_rect.left() + (kink.input_pct / 100.0) * plot_rect.width()
            k_color = (
                QColor("#ff5555") if kink.severity == "error" else QColor("#f5a623")
            )
            painter.setPen(QPen(k_color, 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(
                QPointF(kx, plot_rect.top()), QPointF(kx, plot_rect.bottom())
            )
            painter.setBrush(k_color)
            painter.drawEllipse(QPointF(kx, plot_rect.top() + 8), 4.5, 4.5)

        # X-axis label
        painter.setPen(text_pen)
        painter.drawText(
            QRectF(
                plot_rect.left(),
                rect.height() - 20,
                plot_rect.width(),
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            tr("Input Signal Level RGB (%)", "Eingangssignal RGB (%)"),
        )

    def _paint_trc_mode(
        self,
        painter: QPainter,
        plot_rect: QRectF,
        grid_pen: QPen,
        text_pen: QPen,
    ) -> None:
        for i in range(11):
            frac = i / 10.0
            y = plot_rect.bottom() - frac * plot_rect.height()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(plot_rect.left(), y), QPointF(plot_rect.right(), y))
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(4, y - 9, plot_rect.left() - 10, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{int(frac * 100)}%",
            )

        # Ideal gamma reference curve
        gamma = self.inspection.target_gamma
        ref_path = QPainterPath()
        steps = 100
        for i in range(steps + 1):
            xf = i / steps
            yf = xf**gamma
            px = plot_rect.left() + xf * plot_rect.width()
            py = plot_rect.bottom() - yf * plot_rect.height()
            if i == 0:
                ref_path.moveTo(px, py)
            else:
                ref_path.lineTo(px, py)
        painter.setPen(QPen(QColor("#8892b0"), 1.4, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(ref_path)

        # Draw R, G, B TRC curves
        channels = [
            (self.inspection.r_trc, QColor("#ff5c5c")),
            (self.inspection.g_trc, QColor("#50fa7b")),
            (self.inspection.b_trc, QColor("#5ccfe6")),
        ]
        for curve, color in channels:
            if len(curve) < 2:
                continue
            path = QPainterPath()
            n = len(curve)
            for idx, val in enumerate(curve):
                xf = idx / (n - 1)
                yf = max(0.0, min(1.0, val))
                px = plot_rect.left() + xf * plot_rect.width()
                py = plot_rect.bottom() - yf * plot_rect.height()
                if idx == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
            painter.setPen(QPen(color, 1.8))
            painter.drawPath(path)

        # Draw measured .ti3 grayscale points if available
        if self.inspection.gray_ramp:
            painter.setPen(QPen(QColor("#ffffff"), 1.3))
            painter.setBrush(QColor("#14171c"))
            for pt in self.inspection.gray_ramp:
                px = plot_rect.left() + (pt.input_pct / 100.0) * plot_rect.width()
                py = plot_rect.bottom() - pt.norm_y * plot_rect.height()
                painter.drawEllipse(QPointF(px, py), 3.2, 3.2)

        # Legend in top-left corner of plot
        self._draw_legend(
            painter,
            plot_rect,
            [
                (QColor("#ff5c5c"), "Red TRC"),
                (QColor("#50fa7b"), "Green TRC"),
                (QColor("#5ccfe6"), "Blue TRC"),
                (QColor("#8892b0"), f"Ideal γ={gamma:.1f}"),
                (QColor("#ffffff"), tr("Measured .ti3 Gray", "Messpunkte (.ti3 Grau)")),
            ],
        )

    def _paint_deviation_mode(
        self,
        painter: QPainter,
        plot_rect: QRectF,
        grid_pen: QPen,
        text_pen: QPen,
    ) -> None:
        """Magnifies deviations (in %) from the ideal gamma curve so small kinks stand out clearly."""
        max_dev_pct = 8.0
        for tick in range(-8, 9, 2):
            frac = (tick + max_dev_pct) / (2.0 * max_dev_pct)
            y = plot_rect.bottom() - frac * plot_rect.height()
            pen = (
                QPen(QColor("#6c768a"), 1.2, Qt.PenStyle.DashLine)
                if tick == 0
                else grid_pen
            )
            painter.setPen(pen)
            painter.drawLine(QPointF(plot_rect.left(), y), QPointF(plot_rect.right(), y))
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(2, y - 9, plot_rect.left() - 8, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{tick:+d}%",
            )

        gamma = self.inspection.target_gamma
        channels = [
            (self.inspection.r_trc, QColor("#ff5c5c")),
            (self.inspection.g_trc, QColor("#50fa7b")),
            (self.inspection.b_trc, QColor("#5ccfe6")),
        ]
        for curve, color in channels:
            if len(curve) < 2:
                continue
            path = QPainterPath()
            n = len(curve)
            for idx, val in enumerate(curve):
                xf = idx / (n - 1)
                ideal = xf**gamma
                dev_pct = max(-max_dev_pct, min(max_dev_pct, (val - ideal) * 100.0))
                yf = (dev_pct + max_dev_pct) / (2.0 * max_dev_pct)
                px = plot_rect.left() + xf * plot_rect.width()
                py = plot_rect.bottom() - yf * plot_rect.height()
                if idx == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
            painter.setPen(QPen(color, 1.8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        if self.inspection.gray_ramp:
            ramp_path = QPainterPath()
            for idx, pt in enumerate(self.inspection.gray_ramp):
                dev_pct = max(
                    -max_dev_pct, min(max_dev_pct, (pt.norm_y - pt.ideal_y) * 100.0)
                )
                yf = (dev_pct + max_dev_pct) / (2.0 * max_dev_pct)
                px = plot_rect.left() + (pt.input_pct / 100.0) * plot_rect.width()
                py = plot_rect.bottom() - yf * plot_rect.height()
                if idx == 0:
                    ramp_path.moveTo(px, py)
                else:
                    ramp_path.lineTo(px, py)
            painter.setPen(QPen(QColor("#f1fa8c"), 1.6))
            painter.drawPath(ramp_path)

            painter.setPen(QPen(QColor("#ffffff"), 1.3))
            painter.setBrush(QColor("#14171c"))
            for pt in self.inspection.gray_ramp:
                dev_pct = max(
                    -max_dev_pct, min(max_dev_pct, (pt.norm_y - pt.ideal_y) * 100.0)
                )
                yf = (dev_pct + max_dev_pct) / (2.0 * max_dev_pct)
                px = plot_rect.left() + (pt.input_pct / 100.0) * plot_rect.width()
                py = plot_rect.bottom() - yf * plot_rect.height()
                painter.drawEllipse(QPointF(px, py), 3.4, 3.4)

        self._draw_legend(
            painter,
            plot_rect,
            [
                (QColor("#ff5c5c"), "Δ Red TRC (%)"),
                (QColor("#50fa7b"), "Δ Green TRC (%)"),
                (QColor("#5ccfe6"), "Δ Blue TRC (%)"),
                (
                    QColor("#f1fa8c"),
                    tr("Δ Measured Gray vs. γ=2.2", "Δ Gemessenes Grau ggü. γ=2.2"),
                ),
            ],
        )

    @staticmethod
    def _draw_legend(
        painter: QPainter,
        plot_rect: QRectF,
        items: list[tuple[QColor, str]],
    ) -> None:
        x0 = plot_rect.left() + 12
        y0 = plot_rect.top() + 10
        box_w = 195
        box_h = 8 + len(items) * 18
        painter.fillRect(QRectF(x0, y0, box_w, box_h), QColor(20, 23, 28, 210))
        painter.setPen(QPen(QColor("#3b4252"), 1.0))
        painter.drawRect(QRectF(x0, y0, box_w, box_h))

        for idx, (color, label) in enumerate(items):
            ly = y0 + 12 + idx * 18
            painter.setPen(QPen(color, 2.2))
            painter.drawLine(QPointF(x0 + 8, ly), QPointF(x0 + 26, ly))
            painter.setPen(QColor("#d8dee9"))
            painter.drawText(
                QRectF(x0 + 32, ly - 8, box_w - 36, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )


class ProfileReviewDialog(QDialog):
    """Dialog to inspect tone curves, check for kinks, preview A/B live on screen, and confirm saving."""

    def __init__(
        self,
        inspection: ProfileInspection,
        connector: str | None = None,
        compositor: CompositorBackend | None = None,
        staged_profile: StagedProfile | None = None,
        previous_icc_path: str | None = None,
        previous_source: str = "sRGB",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.inspection = inspection
        self.connector = connector
        self.compositor = compositor
        self.staged_profile = staged_profile
        self.previous_icc_path = previous_icc_path
        self.previous_source = previous_source
        self.saved_profile_path: Path | None = None

        self.setWindowTitle(
            tr(
                "KelvinCal – ICC Profile Inspector & Live Preview",
                "KelvinCal – ICC-Profil-Inspektor & Live-Vorschau",
            )
        )
        self.resize(860, 660)
        self._build_ui()
        self._refresh_metrics_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header + View Mode selector
        header_row = QHBoxLayout()
        self.lbl_title = QLabel()
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.lbl_title.setFont(title_font)

        self.combo_mode = QComboBox()
        self.combo_mode.addItem(
            tr(
                "View: Tone Response Curves (RGB TRC & .ti3 vs. γ=2.2)",
                "Ansicht: Tonwertkurven (RGB-TRC & .ti3 ggü. γ=2.2)",
            )
        )
        self.combo_mode.addItem(
            tr(
                "View: Kink Magnifier (Deviation Δ% from Ideal γ=2.2)",
                "Ansicht: Knick-Lupe (Abweichung Δ% von Ideal γ=2.2)",
            )
        )

        header_row.addWidget(self.lbl_title, stretch=1)
        header_row.addWidget(self.combo_mode)

        if self.staged_profile is None:
            btn_open_file = QPushButton(
                tr("Load Another .icc File...", "Andere .icc-Datei öffnen...")
            )
            btn_open_file.clicked.connect(self._on_open_other_icc)
            header_row.addWidget(btn_open_file)

        layout.addLayout(header_row)

        # Metrics Summary Grid
        metrics_frame = QFrame()
        metrics_frame.setFrameShape(QFrame.Shape.StyledPanel)
        metrics_grid = QGridLayout(metrics_frame)
        self.lbl_white = QLabel()
        self.lbl_black = QLabel()
        self.lbl_contrast = QLabel()
        self.lbl_wp = QLabel()
        self.lbl_gamma = QLabel()
        self.lbl_kink_status = QLabel()

        metrics_grid.addWidget(self.lbl_white, 0, 0)
        metrics_grid.addWidget(self.lbl_black, 0, 1)
        metrics_grid.addWidget(self.lbl_contrast, 0, 2)
        metrics_grid.addWidget(self.lbl_wp, 1, 0)
        metrics_grid.addWidget(self.lbl_gamma, 1, 1)
        metrics_grid.addWidget(self.lbl_kink_status, 1, 2)
        layout.addWidget(metrics_frame)

        # Curve Plot Widget
        self.curve_widget = ProfileCurveWidget(self.inspection, self)
        self.combo_mode.currentIndexChanged.connect(self.curve_widget.set_view_mode)
        layout.addWidget(self.curve_widget, stretch=1)

        # Kink Details Banner
        self.lbl_kink_details = QLabel()
        self.lbl_kink_details.setWordWrap(True)
        layout.addWidget(self.lbl_kink_details)

        # Live A/B Preview Box (if compositor and connector are available)
        if self.compositor is not None and self.connector:
            grp_ab = QGroupBox(
                tr(
                    f"Live Monitor Preview on {self.connector} (Instant Switching)",
                    f"Live-Monitor-Vorschau auf {self.connector} (Sofort-Umschaltung)",
                )
            )
            ab_layout = QHBoxLayout(grp_ab)
            self.btn_group_ab = QButtonGroup(self)

            self.rad_new = QRadioButton(
                tr(
                    "New / Inspected ICC Profile",
                    "Neues / Geprüftes ICC-Profil",
                )
            )
            self.rad_new.setChecked(True)
            self.btn_group_ab.addButton(self.rad_new, 0)
            ab_layout.addWidget(self.rad_new)

            prev_name = (
                Path(self.previous_icc_path).name
                if self.previous_icc_path
                else "sRGB"
            )
            self.rad_prev = QRadioButton(
                tr(
                    f"Previous Profile ({prev_name})",
                    f"Vorheriges Profil ({prev_name})",
                )
            )
            self.btn_group_ab.addButton(self.rad_prev, 1)
            ab_layout.addWidget(self.rad_prev)

            self.rad_uncal = QRadioButton(
                tr("Uncalibrated (Compositor sRGB)", "Unkalibriert (KWin sRGB)")
            )
            self.btn_group_ab.addButton(self.rad_uncal, 2)
            ab_layout.addWidget(self.rad_uncal)

            self.btn_group_ab.idClicked.connect(self._on_preview_mode_changed)
            layout.addWidget(grp_ab)

        # Footer Buttons
        footer = QHBoxLayout()
        footer.addStretch(1)

        if self.staged_profile is not None:
            btn_discard = QPushButton(
                tr(
                    "Discard & Restore Previous Profile",
                    "Verwerfen & vorheriges Profil wiederherstellen",
                )
            )
            btn_discard.clicked.connect(self._on_discard_clicked)

            btn_save_as = QPushButton(
                tr("Save Profile As...", "Profil speichern unter...")
            )
            btn_save_as.clicked.connect(self._on_save_as_clicked)

            btn_save = QPushButton(
                tr(
                    f"Save & Activate ({self.staged_profile.suggested_output_path.name})",
                    f"Speichern & Aktivieren ({self.staged_profile.suggested_output_path.name})",
                )
            )
            btn_save.setDefault(True)
            btn_save.clicked.connect(self._on_save_default_clicked)

            footer.addWidget(btn_discard)
            footer.addWidget(btn_save_as)
            footer.addWidget(btn_save)
        else:
            btn_close = QPushButton(tr("Close", "Schließen"))
            btn_close.setDefault(True)
            btn_close.clicked.connect(self.accept)
            footer.addWidget(btn_close)

        layout.addLayout(footer)

    def _refresh_metrics_ui(self) -> None:
        insp = self.inspection
        self.lbl_title.setText(f"{insp.description} ({insp.profile_path.name})")

        w_str = (
            f"{insp.luminance_cdm2:.1f} cd/m²"
            if insp.luminance_cdm2 is not None
            else "n/a"
        )
        b_str = (
            f"{insp.black_luminance_cdm2:.3f} cd/m²"
            if insp.black_luminance_cdm2 is not None
            else "n/a"
        )
        c_str = (
            f"{insp.contrast_ratio:.0f} : 1"
            if insp.contrast_ratio is not None
            else "n/a"
        )
        if insp.white_cct_kelvin is not None and insp.white_delta_uv_d65 is not None:
            wp_str = f"{insp.white_cct_kelvin:.0f} K (Δu'v' D65 = {insp.white_delta_uv_d65:.4f})"
        else:
            wp_str = "n/a"
        g_str = (
            f"γ ≈ {insp.effective_gamma:.2f}"
            if insp.effective_gamma is not None
            else "n/a"
        )

        self.lbl_white.setText(
            tr(f"<b>White Level:</b> {w_str}", f"<b>Weißwert:</b> {w_str}")
        )
        self.lbl_black.setText(
            tr(f"<b>Black Level:</b> {b_str}", f"<b>Schwarzwert:</b> {b_str}")
        )
        self.lbl_contrast.setText(
            tr(
                f"<b>Static Contrast:</b> {c_str}",
                f"<b>Statischer Kontrast:</b> {c_str}",
            )
        )
        self.lbl_wp.setText(
            tr(f"<b>Whitepoint:</b> {wp_str}", f"<b>Weißpunkt:</b> {wp_str}")
        )
        self.lbl_gamma.setText(
            tr(
                f"<b>Effective Gamma:</b> {g_str} ({insp.total_measured_patches} patches)",
                f"<b>Effektives Gamma:</b> {g_str} ({insp.total_measured_patches} Messfelder)",
            )
        )

        if insp.is_clean:
            self.lbl_kink_status.setText(
                tr(
                    "<span style='color:#50fa7b;'><b>✓ Curve Check:</b> Smooth & monotonic (no kinks)</span>",
                    "<span style='color:#50fa7b;'><b>✓ Knick-Check:</b> Glatt & monoton (keine Knicke)</span>",
                )
            )
            self.lbl_kink_details.setText(
                tr(
                    "No discontinuities, reversals, or grayscale balance spikes were detected.",
                    "Keine Unstetigkeiten, Rückläufigkeiten oder Graubalance-Ausreißer erkannt.",
                )
            )
        else:
            color = "#ff5555" if insp.has_errors else "#f5a623"
            self.lbl_kink_status.setText(
                tr(
                    f"<span style='color:{color};'><b>⚠ Curve Check:</b> {len(insp.kinks)} anomaly/kink(s) found</span>",
                    f"<span style='color:{color};'><b>⚠ Knick-Check:</b> {len(insp.kinks)} Auffälligkeit(en) gefunden</span>",
                )
            )
            bullets = [
                f"• {tr(k.message_en, k.message_de)}" for k in insp.kinks[:4]
            ]
            self.lbl_kink_details.setText("\n".join(bullets))

    def _on_preview_mode_changed(self, btn_id: int) -> None:
        if self.compositor is None or not self.connector:
            return
        try:
            if btn_id == 0:
                self.compositor.apply_output_profile(
                    connector=self.connector,
                    icc_profile_path=str(self.inspection.profile_path),
                    color_profile_source="ICC",
                    brightness=None,
                )
            elif btn_id == 1:
                if self.previous_icc_path and self.previous_source == "ICC":
                    self.compositor.apply_output_profile(
                        connector=self.connector,
                        icc_profile_path=self.previous_icc_path,
                        color_profile_source="ICC",
                        brightness=None,
                    )
                else:
                    self.compositor.reset_for_calibration(self.connector)
            elif btn_id == 2:
                self.compositor.reset_for_calibration(self.connector)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                tr("Preview Switch Error", "Fehler beim Vorschau-Umschalten"),
                str(exc),
            )

    def _on_open_other_icc(self) -> None:
        default_dir = str(Path.home() / ".local" / "share" / "icc")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Open ICC Profile", "ICC-Profil öffnen"),
            default_dir,
            "ICC Profiles (*.icc *.icm)",
        )
        if not file_path:
            return
        try:
            self.inspection = inspect_profile(file_path)
            self.curve_widget.set_inspection(self.inspection)
            self._refresh_metrics_ui()
            if hasattr(self, "rad_new") and self.rad_new.isChecked():
                self._on_preview_mode_changed(0)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                tr("Profile Load Error", "Fehler beim Laden des Profils"),
                str(exc),
            )

    def _on_save_default_clicked(self) -> None:
        if self.staged_profile is None:
            return
        self._finalize_save(self.staged_profile.suggested_output_path)

    def _on_save_as_clicked(self) -> None:
        if self.staged_profile is None:
            return
        suggested = str(self.staged_profile.suggested_output_path)
        dest_str, _ = QFileDialog.getSaveFileName(
            self,
            tr("Save ICC Profile As", "ICC-Profil speichern unter"),
            suggested,
            "ICC Profiles (*.icc *.icm)",
        )
        if not dest_str:
            return
        dest = Path(dest_str)
        if not dest.suffix:
            dest = dest.with_suffix(".icc")
        self._finalize_save(dest)

    def _finalize_save(self, dest: Path) -> None:
        if self.staged_profile is None:
            return
        saved = self.staged_profile.save_to(dest)
        self.saved_profile_path = saved
        if self.compositor is not None and self.connector:
            self.compositor.apply_output_profile(
                connector=self.connector,
                icc_profile_path=str(saved),
                color_profile_source="ICC",
                brightness=None,
            )
        self.accept()

    def _on_discard_clicked(self) -> None:
        self.reject()

    def reject(self) -> None:
        if self.staged_profile is not None and self.saved_profile_path is None:
            if self.compositor is not None and self.connector:
                if self.previous_icc_path and self.previous_source == "ICC":
                    self.compositor.apply_output_profile(
                        connector=self.connector,
                        icc_profile_path=self.previous_icc_path,
                        color_profile_source="ICC",
                        brightness=None,
                    )
                else:
                    self.compositor.reset_for_calibration(self.connector)
            self.staged_profile.cleanup()
        super().reject()
