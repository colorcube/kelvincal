"""DisplayCAL-inspired ICC Profile Inspector ('Knick-Check' curve/gamut viewer) and Live A/B Preview."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
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

from kcal_argyll.profile_inspector import (
    ProfileInspection,
    SRGB_PRIMARIES_XY,
    inspect_profile,
)
from kcal_argyll.profile_pipeline import StagedProfile
from kcal_core.compositor.base import CompositorBackend
from kcal_core.i18n import translate
from kcal_core.models import D65_X, D65_Y
from kcal_core.paths import user_icc_dir


# Approximate CIE 1931 2-degree spectral locus horseshoe coordinates (380nm .. 700nm)
CIE1931_LOCUS_XY: list[tuple[float, float]] = [
    (0.1741, 0.0050),
    (0.1733, 0.0048),
    (0.1703, 0.0058),
    (0.1603, 0.0145),
    (0.1440, 0.0297),
    (0.1241, 0.0578),
    (0.0913, 0.1327),
    (0.0454, 0.2950),
    (0.0082, 0.5384),
    (0.0139, 0.7502),
    (0.0743, 0.8338),
    (0.1547, 0.8059),
    (0.2296, 0.7543),
    (0.3016, 0.6923),
    (0.3731, 0.6245),
    (0.4441, 0.5547),
    (0.5125, 0.4866),
    (0.5752, 0.4242),
    (0.6270, 0.3725),
    (0.6658, 0.3340),
    (0.7006, 0.2993),
    (0.7347, 0.2653),
]


class ProfileCurveWidget(QWidget):
    """DisplayCAL-style interactive curve and CIE gamut viewer with mouse crosshair readout."""

    MODE_TRC = 0
    MODE_GAMMA = 1
    MODE_DEVIATION = 2
    MODE_GAMUT = 3

    def __init__(
        self,
        inspection: ProfileInspection,
        on_hover_readout: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.inspection = inspection
        self.view_mode = self.MODE_TRC
        self.on_hover_readout = on_hover_readout
        self.show_r = True
        self.show_g = True
        self.show_b = True
        self.show_ti3_points = True
        self.show_reference = True
        self.hover_frac: float | None = None

        self.setMinimumSize(680, 370)
        self.setMouseTracking(True)

    def set_inspection(self, inspection: ProfileInspection) -> None:
        self.inspection = inspection
        self.update()

    def set_view_mode(self, mode: int) -> None:
        self.view_mode = mode
        self.update()

    def _plot_rect(self) -> QRectF:
        rect = self.rect()
        margin_left = 62.0
        margin_right = 24.0
        margin_top = 24.0
        margin_bottom = 42.0
        return QRectF(
            margin_left,
            margin_top,
            max(10.0, rect.width() - margin_left - margin_right),
            max(10.0, rect.height() - margin_top - margin_bottom),
        )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        plot_rect = self._plot_rect()
        pos = event.position()
        if plot_rect.contains(pos) and self.view_mode != self.MODE_GAMUT:
            self.hover_frac = max(
                0.0, min(1.0, (pos.x() - plot_rect.left()) / plot_rect.width())
            )
            self._emit_readout(self.hover_frac)
        else:
            self.hover_frac = None
            if self.on_hover_readout:
                self.on_hover_readout("")
        self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self.hover_frac = None
        if self.on_hover_readout:
            self.on_hover_readout("")
        self.update()

    @staticmethod
    def _sample_curve(curve: list[float], frac: float) -> float | None:
        if not curve:
            return None
        if len(curve) == 1:
            return curve[0]
        pos = frac * (len(curve) - 1)
        idx = int(math.floor(pos))
        if idx >= len(curve) - 1:
            return curve[-1]
        t = pos - idx
        return curve[idx] * (1.0 - t) + curve[idx + 1] * t

    def _emit_readout(self, frac: float) -> None:
        if not self.on_hover_readout:
            return
        pct = frac * 100.0
        rgb_8bit = int(round(frac * 255))
        ideal = (frac ** self.inspection.target_gamma) * 100.0
        rv = self._sample_curve(self.inspection.r_trc, frac)
        gv = self._sample_curve(self.inspection.g_trc, frac)
        bv = self._sample_curve(self.inspection.b_trc, frac)

        parts = [f"Input: {pct:5.1f}% (RGB {rgb_8bit:3d}/255)"]
        if rv is not None and gv is not None and bv is not None:
            parts.append(
                f"Output: R={rv * 100:5.1f}%  G={gv * 100:5.1f}%  B={bv * 100:5.1f}%  (Ideal γ={self.inspection.target_gamma:.1f}: {ideal:5.1f}%)"
            )
            if 0.03 <= frac <= 0.97 and rv > 0.001 and gv > 0.001 and bv > 0.001:
                gr = math.log(rv) / math.log(frac)
                gg = math.log(gv) / math.log(frac)
                gb = math.log(bv) / math.log(frac)
                parts.append(f"γ: R={gr:.2f}  G={gg:.2f}  B={gb:.2f}")
        self.on_hover_readout("   |   ".join(parts))

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()
        painter.fillRect(rect, QColor("#181b22"))

        plot_rect = self._plot_rect()
        painter.fillRect(plot_rect, QColor("#12151b"))

        grid_pen = QPen(QColor("#2a303c"), 1.0, Qt.PenStyle.DotLine)
        axis_pen = QPen(QColor("#4c566a"), 1.3)
        text_pen = QPen(QColor("#c0c8d8"))
        painter.setFont(QFont("Sans Serif", 8))

        if self.view_mode == self.MODE_GAMUT:
            self._paint_gamut_mode(painter, plot_rect, grid_pen, text_pen)
        else:
            # Common X-axis grid (0% .. 100%)
            for i in range(11):
                frac = i / 10.0
                x = plot_rect.left() + frac * plot_rect.width()
                painter.setPen(grid_pen)
                painter.drawLine(
                    QPointF(x, plot_rect.top()), QPointF(x, plot_rect.bottom())
                )
                painter.setPen(text_pen)
                painter.drawText(
                    QRectF(x - 22, plot_rect.bottom() + 4, 44, 18),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{int(frac * 100)}%",
                )

            if self.view_mode == self.MODE_TRC:
                self._paint_trc_mode(painter, plot_rect, grid_pen, text_pen)
            elif self.view_mode == self.MODE_GAMMA:
                self._paint_gamma_mode(painter, plot_rect, grid_pen, text_pen)
            else:
                self._paint_deviation_mode(painter, plot_rect, grid_pen, text_pen)

            # Highlight any detected kinks with vertical warning markers
            for kink in self.inspection.kinks:
                kx = plot_rect.left() + (kink.input_pct / 100.0) * plot_rect.width()
                k_color = (
                    QColor("#ff5555")
                    if kink.severity == "error"
                    else QColor("#f5a623")
                )
                painter.setPen(QPen(k_color, 1.5, Qt.PenStyle.DashLine))
                painter.drawLine(
                    QPointF(kx, plot_rect.top()), QPointF(kx, plot_rect.bottom())
                )
                painter.setBrush(k_color)
                painter.drawEllipse(QPointF(kx, plot_rect.top() + 8), 4.5, 4.5)

            # Interactive mouse hover crosshair
            if self.hover_frac is not None:
                hx = plot_rect.left() + self.hover_frac * plot_rect.width()
                painter.setPen(QPen(QColor(255, 255, 255, 110), 1.0, Qt.PenStyle.DashLine))
                painter.drawLine(
                    QPointF(hx, plot_rect.top()), QPointF(hx, plot_rect.bottom())
                )

            # X-axis title
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(
                    plot_rect.left(),
                    rect.height() - 20,
                    plot_rect.width(),
                    18,
                ),
                Qt.AlignmentFlag.AlignCenter,
                translate("ProfileReview", "Input Signal Level RGB (%)"),
            )

        # Always reset brush to NoBrush before drawing the outer plot frame!
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(axis_pen)
        painter.drawRect(plot_rect)

    def _active_channels(self) -> list[tuple[str, list[float], QColor, float]]:
        out: list[tuple[str, list[float], QColor, float]] = []
        if self.show_r:
            out.append(("R", self.inspection.r_trc, QColor(255, 85, 85, 230), 2.6))
        if self.show_g:
            out.append(("G", self.inspection.g_trc, QColor(80, 250, 123, 230), 2.1))
        if self.show_b:
            out.append(("B", self.inspection.b_trc, QColor(92, 207, 230, 230), 1.7))
        return out

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
            painter.drawLine(
                QPointF(plot_rect.left(), y), QPointF(plot_rect.right(), y)
            )
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(4, y - 9, plot_rect.left() - 10, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{int(frac * 100)}%",
            )

        # Diagonal linear reference (dotted subtle line)
        painter.setPen(QPen(QColor("#2e3646"), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(plot_rect.bottomLeft(), plot_rect.topRight())

        # Ideal gamma reference curve
        gamma = self.inspection.target_gamma
        if self.show_reference:
            ref_path = QPainterPath()
            steps = 120
            for i in range(steps + 1):
                xf = i / steps
                yf = xf**gamma
                px = plot_rect.left() + xf * plot_rect.width()
                py = plot_rect.bottom() - yf * plot_rect.height()
                if i == 0:
                    ref_path.moveTo(px, py)
                else:
                    ref_path.lineTo(px, py)
            painter.setPen(QPen(QColor("#9aa5ce"), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(ref_path)

        # Draw R, G, B TRC curves
        for _ch, curve, color, width in self._active_channels():
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
            painter.setPen(QPen(color, width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # Draw measured .ti3 points (both single-channel ramps and neutral gray ramp)
        if self.show_ti3_points:
            ch_colors = {
                "R": (self.show_r, QColor("#ff5555")),
                "G": (self.show_g, QColor("#50fa7b")),
                "B": (self.show_b, QColor("#5ccfe6")),
            }
            for ch, pts in self.inspection.channel_ramps.items():
                enabled, col = ch_colors.get(ch, (True, QColor("#ffffff")))
                if not enabled:
                    continue
                painter.setPen(QPen(col, 1.4))
                painter.setBrush(QColor("#12151b"))
                for pct, norm_val in pts:
                    px = plot_rect.left() + (pct / 100.0) * plot_rect.width()
                    py = plot_rect.bottom() - norm_val * plot_rect.height()
                    painter.drawEllipse(QPointF(px, py), 3.4, 3.4)

            if len(self.inspection.gray_ramp) > 2:
                painter.setPen(QPen(QColor("#f8f8f2"), 1.5))
                painter.setBrush(QColor("#12151b"))
                for pt in self.inspection.gray_ramp:
                    px = plot_rect.left() + (pt.input_pct / 100.0) * plot_rect.width()
                    py = plot_rect.bottom() - pt.norm_y * plot_rect.height()
                    painter.drawEllipse(QPointF(px, py), 3.6, 3.6)

        self._draw_legend(
            painter,
            plot_rect,
            [
                (QColor("#ff5555"), "Red TRC (rTRC)"),
                (QColor("#50fa7b"), "Green TRC (gTRC)"),
                (QColor("#5ccfe6"), "Blue TRC (bTRC)"),
                (QColor("#9aa5ce"), f"Ideal γ={gamma:.1f}"),
                (QColor("#f8f8f2"), translate("ProfileReview", "Measured .ti3 Points")),
            ],
        )

    def _paint_gamma_mode(
        self,
        painter: QPainter,
        plot_rect: QRectF,
        grid_pen: QPen,
        text_pen: QPen,
    ) -> None:
        """DisplayCAL-style Gamma plot: plots effective γ(x) = ln(Y)/ln(x) over [1.4 .. 3.0]."""
        g_min = 1.4
        g_max = 3.0
        for step_idx in range(9):
            g_val = g_min + step_idx * 0.2
            frac = (g_val - g_min) / (g_max - g_min)
            y = plot_rect.bottom() - frac * plot_rect.height()
            is_target = abs(g_val - self.inspection.target_gamma) < 0.02
            pen = (
                QPen(QColor("#9aa5ce"), 1.4, Qt.PenStyle.DashLine)
                if is_target
                else grid_pen
            )
            painter.setPen(pen)
            painter.drawLine(
                QPointF(plot_rect.left(), y), QPointF(plot_rect.right(), y)
            )
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(4, y - 9, plot_rect.left() - 10, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"γ {g_val:.1f}",
            )

        for _ch, curve, color, width in self._active_channels():
            if len(curve) < 16:
                continue
            path = QPainterPath()
            started = False
            n = len(curve)
            for idx, val in enumerate(curve):
                xf = idx / (n - 1)
                if xf < 0.04 or xf > 0.96 or val <= 0.001 or val >= 0.999:
                    continue
                loc_g = math.log(val) / math.log(xf)
                clamped_g = max(g_min, min(g_max, loc_g))
                yf = (clamped_g - g_min) / (g_max - g_min)
                px = plot_rect.left() + xf * plot_rect.width()
                py = plot_rect.bottom() - yf * plot_rect.height()
                if not started:
                    path.moveTo(px, py)
                    started = True
                else:
                    path.lineTo(px, py)
            painter.setPen(QPen(color, width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        if self.show_ti3_points:
            ch_colors = {
                "R": (self.show_r, QColor("#ff5555")),
                "G": (self.show_g, QColor("#50fa7b")),
                "B": (self.show_b, QColor("#5ccfe6")),
            }
            for ch, pts in self.inspection.channel_ramps.items():
                enabled, col = ch_colors.get(ch, (True, QColor("#ffffff")))
                if not enabled:
                    continue
                painter.setPen(QPen(col, 1.4))
                painter.setBrush(QColor("#12151b"))
                for pct, norm_val in pts:
                    xf = pct / 100.0
                    if 0.04 <= xf <= 0.96 and 0.002 < norm_val < 0.998:
                        loc_g = max(g_min, min(g_max, math.log(norm_val) / math.log(xf)))
                        yf = (loc_g - g_min) / (g_max - g_min)
                        px = plot_rect.left() + xf * plot_rect.width()
                        py = plot_rect.bottom() - yf * plot_rect.height()
                        painter.drawEllipse(QPointF(px, py), 3.5, 3.5)

            if len(self.inspection.gray_ramp) > 2:
                painter.setPen(QPen(QColor("#f8f8f2"), 1.5))
                painter.setBrush(QColor("#12151b"))
                for pt in self.inspection.gray_ramp:
                    if pt.local_gamma is not None:
                        loc_g = max(g_min, min(g_max, pt.local_gamma))
                        yf = (loc_g - g_min) / (g_max - g_min)
                        px = plot_rect.left() + (pt.input_pct / 100.0) * plot_rect.width()
                        py = plot_rect.bottom() - yf * plot_rect.height()
                        painter.drawEllipse(QPointF(px, py), 3.6, 3.6)

        self._draw_legend(
            painter,
            plot_rect,
            [
                (QColor("#ff5555"), "Red γ(x)"),
                (QColor("#50fa7b"), "Green γ(x)"),
                (QColor("#5ccfe6"), "Blue γ(x)"),
                (QColor("#9aa5ce"), f"Target γ={self.inspection.target_gamma:.1f}"),
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
        max_dev_pct = 6.0
        for tick in range(-6, 7, 2):
            frac = (tick + max_dev_pct) / (2.0 * max_dev_pct)
            y = plot_rect.bottom() - frac * plot_rect.height()
            pen = (
                QPen(QColor("#9aa5ce"), 1.3, Qt.PenStyle.DashLine)
                if tick == 0
                else grid_pen
            )
            painter.setPen(pen)
            painter.drawLine(
                QPointF(plot_rect.left(), y), QPointF(plot_rect.right(), y)
            )
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(2, y - 9, plot_rect.left() - 8, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{tick:+d}%",
            )

        gamma = self.inspection.target_gamma
        for _ch, curve, color, width in self._active_channels():
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
            painter.setPen(QPen(color, width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        if self.show_ti3_points:
            ch_colors = {
                "R": (self.show_r, QColor("#ff5555")),
                "G": (self.show_g, QColor("#50fa7b")),
                "B": (self.show_b, QColor("#5ccfe6")),
            }
            for ch, pts in self.inspection.channel_ramps.items():
                enabled, col = ch_colors.get(ch, (True, QColor("#ffffff")))
                if not enabled:
                    continue
                painter.setPen(QPen(col, 1.4))
                painter.setBrush(QColor("#12151b"))
                for pct, norm_val in pts:
                    xf = pct / 100.0
                    ideal = xf**gamma
                    dev_pct = max(
                        -max_dev_pct, min(max_dev_pct, (norm_val - ideal) * 100.0)
                    )
                    yf = (dev_pct + max_dev_pct) / (2.0 * max_dev_pct)
                    px = plot_rect.left() + xf * plot_rect.width()
                    py = plot_rect.bottom() - yf * plot_rect.height()
                    painter.drawEllipse(QPointF(px, py), 3.4, 3.4)

            if len(self.inspection.gray_ramp) > 2:
                painter.setPen(QPen(QColor("#f8f8f2"), 1.5))
                painter.setBrush(QColor("#12151b"))
                for pt in self.inspection.gray_ramp:
                    dev_pct = max(
                        -max_dev_pct,
                        min(max_dev_pct, (pt.norm_y - pt.ideal_y) * 100.0),
                    )
                    yf = (dev_pct + max_dev_pct) / (2.0 * max_dev_pct)
                    px = plot_rect.left() + (pt.input_pct / 100.0) * plot_rect.width()
                    py = plot_rect.bottom() - yf * plot_rect.height()
                    painter.drawEllipse(QPointF(px, py), 3.6, 3.6)

        self._draw_legend(
            painter,
            plot_rect,
            [
                (QColor("#ff5555"), "Δ Red TRC (%)"),
                (QColor("#50fa7b"), "Δ Green TRC (%)"),
                (QColor("#5ccfe6"), "Δ Blue TRC (%)"),
                (QColor("#9aa5ce"), f"Ideal γ={gamma:.1f} (0.0%)"),
            ],
        )

    def _paint_gamut_mode(
        self,
        painter: QPainter,
        plot_rect: QRectF,
        grid_pen: QPen,
        text_pen: QPen,
    ) -> None:
        """Draws a DisplayCAL-style CIE 1931 (x, y) chromaticity diagram comparing monitor gamut vs sRGB."""
        x_max = 0.80
        y_max = 0.90

        def _xy_to_pt(cx: float, cy: float) -> QPointF:
            px = plot_rect.left() + (cx / x_max) * plot_rect.width()
            py = plot_rect.bottom() - (cy / y_max) * plot_rect.height()
            return QPointF(px, py)

        for i in range(9):
            xv = i * 0.1
            p_top = _xy_to_pt(xv, y_max)
            p_bot = _xy_to_pt(xv, 0.0)
            painter.setPen(grid_pen)
            painter.drawLine(p_top, p_bot)
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(p_bot.x() - 18, plot_rect.bottom() + 4, 36, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{xv:.1f}",
            )

        for j in range(10):
            yv = j * 0.1
            p_l = _xy_to_pt(0.0, yv)
            p_r = _xy_to_pt(x_max, yv)
            painter.setPen(grid_pen)
            painter.drawLine(p_l, p_r)
            painter.setPen(text_pen)
            painter.drawText(
                QRectF(4, p_l.y() - 9, plot_rect.left() - 10, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{yv:.1f}",
            )

        # Draw spectral locus horseshoe
        locus_path = QPainterPath()
        for idx, (lx, ly) in enumerate(CIE1931_LOCUS_XY):
            pt = _xy_to_pt(lx, ly)
            if idx == 0:
                locus_path.moveTo(pt)
            else:
                locus_path.lineTo(pt)
        locus_path.closeSubpath()
        painter.setPen(QPen(QColor("#4c566a"), 1.5))
        painter.setBrush(QColor(40, 48, 64, 55))
        painter.drawPath(locus_path)

        # sRGB reference triangle
        srgb_path = QPainterPath()
        sr = _xy_to_pt(*SRGB_PRIMARIES_XY["R"])
        sg = _xy_to_pt(*SRGB_PRIMARIES_XY["G"])
        sb = _xy_to_pt(*SRGB_PRIMARIES_XY["B"])
        srgb_path.moveTo(sr)
        srgb_path.lineTo(sg)
        srgb_path.lineTo(sb)
        srgb_path.closeSubpath()
        painter.setPen(QPen(QColor("#9aa5ce"), 1.6, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(srgb_path)

        # Profile gamut triangle
        prims = self.inspection.primaries_xy
        if all(k in prims for k in ("R", "G", "B")):
            disp_path = QPainterPath()
            dr = _xy_to_pt(*prims["R"])
            dg = _xy_to_pt(*prims["G"])
            db = _xy_to_pt(*prims["B"])
            disp_path.moveTo(dr)
            disp_path.lineTo(dg)
            disp_path.lineTo(db)
            disp_path.closeSubpath()
            painter.setPen(QPen(QColor("#f8f8f2"), 2.2))
            painter.setBrush(QColor(80, 250, 123, 35))
            painter.drawPath(disp_path)

            for pt_xy, col in (
                (dr, QColor("#ff5555")),
                (dg, QColor("#50fa7b")),
                (db, QColor("#5ccfe6")),
            ):
                painter.setPen(QPen(QColor("#12151b"), 1.5))
                painter.setBrush(col)
                painter.drawEllipse(pt_xy, 5.0, 5.0)

        # D65 target and measured whitepoint
        d65_pt = _xy_to_pt(D65_X, D65_Y)
        painter.setPen(QPen(QColor("#9aa5ce"), 1.5))
        painter.drawLine(
            QPointF(d65_pt.x() - 6, d65_pt.y()), QPointF(d65_pt.x() + 6, d65_pt.y())
        )
        painter.drawLine(
            QPointF(d65_pt.x(), d65_pt.y() - 6), QPointF(d65_pt.x(), d65_pt.y() + 6)
        )

        if self.inspection.white_xy is not None:
            w_pt = _xy_to_pt(*self.inspection.white_xy)
            painter.setPen(QPen(QColor("#f1fa8c"), 1.8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(w_pt, 4.5, 4.5)

        cov = self.inspection.srgb_coverage_pct
        vol = self.inspection.srgb_volume_pct
        cov_str = f"sRGB Coverage: {cov:.1f}% (Area: {vol:.1f}%)" if cov is not None and vol is not None else "Profile Gamut"

        self._draw_legend(
            painter,
            plot_rect,
            [
                (QColor("#f8f8f2"), cov_str),
                (QColor("#9aa5ce"), "sRGB Reference Gamut"),
                (QColor("#f1fa8c"), "Measured Whitepoint vs D65 (+)"),
            ],
        )

    @staticmethod
    def _draw_legend(
        painter: QPainter,
        plot_rect: QRectF,
        items: list[tuple[QColor, str]],
    ) -> None:
        x0 = plot_rect.left() + 14
        y0 = plot_rect.top() + 12
        box_w = 230
        box_h = 10 + len(items) * 18
        painter.fillRect(QRectF(x0, y0, box_w, box_h), QColor(20, 23, 28, 220))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#3b4252"), 1.0))
        painter.drawRect(QRectF(x0, y0, box_w, box_h))

        for idx, (color, label) in enumerate(items):
            ly = y0 + 13 + idx * 18
            painter.setPen(QPen(color, 2.4))
            painter.drawLine(QPointF(x0 + 8, ly), QPointF(x0 + 26, ly))
            painter.setPen(QColor("#d8dee9"))
            painter.drawText(
                QRectF(x0 + 32, ly - 8, box_w - 36, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )


class ProfileReviewDialog(QDialog):
    """DisplayCAL-inspired dialog to inspect tone curves, gamma, gamut, and live A/B preview."""

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
            translate("ProfileReview", "KelvinCal – ICC Profile Inspector & Live Preview")
        )
        self.resize(920, 700)
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
            translate("ProfileReview", "1. Tone Response Curves (RGB TRC & .ti3 vs. γ=2.2)")
        )
        self.combo_mode.addItem(
            translate("ProfileReview", "2. Gamma Curve γ(x) across Signal Level (DisplayCAL Style)")
        )
        self.combo_mode.addItem(
            translate("ProfileReview", "3. Kink Magnifier (Deviation Δ% from Ideal γ=2.2)")
        )
        self.combo_mode.addItem(
            translate("ProfileReview", "4. Gamut (CIE 1931 xy vs. sRGB)")
        )

        header_row.addWidget(self.lbl_title, stretch=1)
        header_row.addWidget(self.combo_mode)

        if self.staged_profile is None:
            btn_open_file = QPushButton(
                translate("ProfileReview", "Load Another .icc File...")
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

        # Channel visibility filter bar (like DisplayCAL)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(translate("ProfileReview", "Channels:")))
        self.chk_r = QCheckBox(translate("ProfileReview", "Red"))
        self.chk_r.setChecked(True)
        self.chk_g = QCheckBox(translate("ProfileReview", "Green"))
        self.chk_g.setChecked(True)
        self.chk_b = QCheckBox(translate("ProfileReview", "Blue"))
        self.chk_b.setChecked(True)
        self.chk_pts = QCheckBox(translate("ProfileReview", "Measured .ti3 Points"))
        self.chk_pts.setChecked(True)
        self.chk_ref = QCheckBox(translate("ProfileReview", "Ideal γ=2.2 Reference"))
        self.chk_ref.setChecked(True)

        for chk in (self.chk_r, self.chk_g, self.chk_b, self.chk_pts, self.chk_ref):
            chk.toggled.connect(self._on_channel_toggles_changed)
            filter_row.addWidget(chk)
        filter_row.addStretch(1)

        self.lbl_hover_readout = QLabel(
            translate("ProfileReview", "Hover over graph to inspect exact RGB & gamma values")
        )
        self.lbl_hover_readout.setStyleSheet("font-family: monospace;")
        filter_row.addWidget(self.lbl_hover_readout)
        layout.addLayout(filter_row)

        # Curve Plot Widget
        self.curve_widget = ProfileCurveWidget(
            self.inspection,
            on_hover_readout=self._on_hover_readout,
            parent=self,
        )
        self.combo_mode.currentIndexChanged.connect(self.curve_widget.set_view_mode)
        layout.addWidget(self.curve_widget, stretch=1)

        # Kink Details Banner
        self.lbl_kink_details = QLabel()
        self.lbl_kink_details.setWordWrap(True)
        layout.addWidget(self.lbl_kink_details)

        # Live A/B Preview Box (if compositor and connector are available)
        if self.compositor is not None and self.connector:
            grp_ab = QGroupBox(
                translate(
                    "ProfileReview",
                    "Live Monitor Preview on {connector} (Instant Switching)",
                ).format(connector=self.connector)
            )
            ab_layout = QHBoxLayout(grp_ab)
            self.btn_group_ab = QButtonGroup(self)

            self.rad_new = QRadioButton(
                translate("ProfileReview", "New / Inspected ICC Profile")
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
                translate("ProfileReview", "Previous Profile ({prev_name})").format(prev_name=prev_name)
            )
            self.btn_group_ab.addButton(self.rad_prev, 1)
            ab_layout.addWidget(self.rad_prev)

            self.rad_uncal = QRadioButton(
                translate("ProfileReview", "Uncalibrated (Compositor sRGB)")
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
                translate("ProfileReview", "Discard & Restore Previous Profile")
            )
            btn_discard.clicked.connect(self._on_discard_clicked)

            btn_save_as = QPushButton(
                translate("ProfileReview", "Save Profile As...")
            )
            btn_save_as.clicked.connect(self._on_save_as_clicked)

            btn_save = QPushButton(
                translate(
                    "ProfileReview",
                    "Save & Activate ({name})",
                ).format(name=self.staged_profile.suggested_output_path.name)
            )
            btn_save.setDefault(True)
            btn_save.clicked.connect(self._on_save_default_clicked)

            footer.addWidget(btn_discard)
            footer.addWidget(btn_save_as)
            footer.addWidget(btn_save)
        else:
            btn_close = QPushButton(translate("ProfileReview", "Close"))
            btn_close.setDefault(True)
            btn_close.clicked.connect(self.accept)
            footer.addWidget(btn_close)

        layout.addLayout(footer)

    def _on_channel_toggles_changed(self) -> None:
        self.curve_widget.show_r = self.chk_r.isChecked()
        self.curve_widget.show_g = self.chk_g.isChecked()
        self.curve_widget.show_b = self.chk_b.isChecked()
        self.curve_widget.show_ti3_points = self.chk_pts.isChecked()
        self.curve_widget.show_reference = self.chk_ref.isChecked()
        self.curve_widget.update()

    def _on_hover_readout(self, text: str) -> None:
        if text:
            self.lbl_hover_readout.setText(text)
        else:
            self.lbl_hover_readout.setText(
                translate("ProfileReview", "Hover over graph to inspect exact RGB & gamma values")
            )

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
        if insp.srgb_coverage_pct is not None:
            g_str += f" | sRGB: {insp.srgb_coverage_pct:.1f}%"

        self.lbl_white.setText(
            translate("ProfileReview", "<b>White Level:</b> {w_str}").format(w_str=w_str)
        )
        self.lbl_black.setText(
            translate("ProfileReview", "<b>Black Level:</b> {b_str}").format(b_str=b_str)
        )
        self.lbl_contrast.setText(
            translate("ProfileReview", "<b>Static Contrast:</b> {c_str}").format(c_str=c_str)
        )
        self.lbl_wp.setText(
            translate("ProfileReview", "<b>Whitepoint:</b> {wp_str}").format(wp_str=wp_str)
        )
        self.lbl_gamma.setText(
            translate(
                "ProfileReview",
                "<b>Gamma & Gamut:</b> {g_str} ({total_measured_patches} patches)",
            ).format(g_str=g_str, total_measured_patches=insp.total_measured_patches)
        )

        if insp.is_clean:
            self.lbl_kink_status.setText(
                translate(
                    "ProfileReview",
                    "<b>Curve Check:</b> <span style='background-color:#15803d; color:#ffffff; padding:2px 6px;'> ✓ Smooth &amp; monotonic (no kinks) </span>",
                )
            )
            self.lbl_kink_details.setText(
                translate(
                    "ProfileReview",
                    "No discontinuities, reversals, or grayscale balance spikes were detected.",
                )
            )
        else:
            bg_color = "#b91c1c" if insp.has_errors else "#b45309"
            self.lbl_kink_status.setText(
                translate(
                    "ProfileReview",
                    "<b>Curve Check:</b> <span style='background-color:{bg_color}; color:#ffffff; padding:2px 6px;'> ⚠ {count} anomaly/kink(s) found </span>",
                ).format(bg_color=bg_color, count=len(insp.kinks))
            )
            bullets = [
                f"• {k.message}" for k in insp.kinks[:4]
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
                translate("ProfileReview", "Preview Switch Error"),
                str(exc),
            )

    def _on_open_other_icc(self) -> None:
        default_dir = str(user_icc_dir())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            translate("ProfileReview", "Open ICC Profile"),
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
                translate("ProfileReview", "Profile Load Error"),
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
            translate("ProfileReview", "Save ICC Profile As"),
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
