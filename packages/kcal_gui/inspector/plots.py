"""Inspector plots: tone curves / gamma γ(x) / kink magnifier, and the chromaticity diagram."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from kcal_argyll.profile_inspector import REFERENCE_GAMUTS, ProfileInspection, xy_to_uv
from kcal_core.i18n import translate
from kcal_core.models import D65_X, D65_Y
from kcal_gui.fmt import num
from kcal_gui.inspector.plot_base import PlotColors, PlotWidget, with_alpha

# CIE 1931 2° standard observer, spectral locus (wavelength nm, x, y)
SPECTRAL_LOCUS: tuple[tuple[int, float, float], ...] = (
    (380, 0.1741, 0.0050), (400, 0.1733, 0.0048), (410, 0.1726, 0.0048), (420, 0.1714, 0.0051),
    (430, 0.1689, 0.0069), (440, 0.1644, 0.0109), (450, 0.1566, 0.0177), (460, 0.1440, 0.0297),
    (465, 0.1355, 0.0399), (470, 0.1241, 0.0578), (475, 0.1096, 0.0868), (480, 0.0913, 0.1327),
    (485, 0.0687, 0.2007), (490, 0.0454, 0.2950), (495, 0.0235, 0.4127), (500, 0.0082, 0.5384),
    (505, 0.0039, 0.6548), (510, 0.0139, 0.7502), (515, 0.0389, 0.8120), (520, 0.0743, 0.8338),
    (525, 0.1142, 0.8262), (530, 0.1547, 0.8059), (535, 0.1929, 0.7816), (540, 0.2296, 0.7543),
    (545, 0.2658, 0.7243), (550, 0.3016, 0.6923), (555, 0.3373, 0.6589), (560, 0.3731, 0.6245),
    (565, 0.4087, 0.5896), (570, 0.4441, 0.5547), (575, 0.4788, 0.5202), (580, 0.5125, 0.4866),
    (585, 0.5448, 0.4544), (590, 0.5752, 0.4242), (595, 0.6029, 0.3965), (600, 0.6270, 0.3725),
    (610, 0.6658, 0.3340), (620, 0.6915, 0.3083), (630, 0.7079, 0.2920), (640, 0.7190, 0.2809),
    (650, 0.7260, 0.2740), (660, 0.7300, 0.2700), (680, 0.7334, 0.2666), (700, 0.7347, 0.2653),
)
LOCUS_LABELS = (460, 490, 520, 560, 600)

VIEW_TRC, VIEW_GAMMA, VIEW_KNICK = range(3)
CHANNELS = ("R", "G", "B")


def sample(curve: list[float], frac: float) -> float | None:
    """Linear interpolation in a curve sampled evenly over 0..1."""
    if not curve:
        return None
    if len(curve) == 1:
        return curve[0]
    pos = max(0.0, min(1.0, frac)) * (len(curve) - 1)
    idx = min(int(pos), len(curve) - 2)
    t = pos - idx
    return curve[idx] * (1.0 - t) + curve[idx + 1] * t


def to_lstar(y: float) -> float:
    """Relative luminance (0..1) → CIE L* / 100."""
    f = math.cbrt(y) if y > 216 / 24389 else (24389 / 27 * y + 16) / 116
    return (116 * f - 16) / 100


def local_gamma(x: float, y: float) -> float | None:
    if 0.0 < x < 1.0 and 0.0 < y < 1.0:
        return math.log(y) / math.log(x)
    return None


class CurvePlot(PlotWidget):
    """Tone response (Y % or L*), local gamma γ(x) and deviation from the target curve (kink magnifier)."""

    GAMMA_RANGE = (1.4, 3.0)
    KNICK_RANGE = 8.0  # ± percentage points

    def __init__(self, inspection: ProfileInspection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.inspection = inspection
        self.view = VIEW_TRC
        self.channels = set(CHANNELS)
        self.show_points = True
        self.show_reference = True
        self.lstar = False

    def set_inspection(self, inspection: ProfileInspection) -> None:
        self.inspection = inspection
        self.refresh()

    def set_view(self, view: int) -> None:
        self.view = view
        self.refresh()

    # ------------------------------------------------------------------ data

    def curves(self) -> dict[str, list[float]]:
        insp = self.inspection
        return {k: c for k, c in (("R", insp.r_trc), ("G", insp.g_trc), ("B", insp.b_trc)) if len(c) >= 2}

    def ideal(self, x: float) -> float:
        return x ** self.inspection.target_gamma

    def y_range(self) -> tuple[float, float]:
        if self.view == VIEW_GAMMA:
            return self.GAMMA_RANGE
        if self.view == VIEW_KNICK:
            return (-self.KNICK_RANGE, self.KNICK_RANGE)
        return (0.0, 1.0)

    def x_start(self) -> float:
        return {VIEW_TRC: 0.0, VIEW_GAMMA: 0.03, VIEW_KNICK: 0.0}[self.view]

    def value(self, x: float, y: float) -> float | None:
        """Maps an (input, normalised output) pair to the plotted quantity of the current view."""
        if self.view == VIEW_TRC:
            return to_lstar(y) if self.lstar else y
        if self.view == VIEW_GAMMA:
            if x < 0.03 or x > 0.97 or y <= 0.001 or y >= 0.999:
                return None
            return local_gamma(x, y)
        return (y - self.ideal(x)) * 100.0

    def fy(self, v: float) -> float:
        lo, hi = self.y_range()
        return (max(lo, min(hi, v)) - lo) / (hi - lo)

    # ------------------------------------------------------------------ painting

    def paint_plot(self, p: QPainter, rect: QRectF, c: PlotColors) -> None:
        lo, hi = self.y_range()
        for i in range(11):
            pt = self.map_point(rect, i / 10, 0)
            p.setPen(QPen(c.grid, 1))
            p.drawLine(QPointF(pt.x(), rect.top()), QPointF(pt.x(), rect.bottom()))
            self.draw_label(p, c, pt.x(), rect.bottom() + 12, str(i * 10))
        self.draw_label(p, c, rect.right(), rect.bottom() + 26, translate("Inspector", "Signal %"),
                        Qt.AlignmentFlag.AlignRight)

        if self.view == VIEW_TRC:
            ticks = [i / 5 for i in range(6)]
            zero = None
            tick_text = lambda t: num(t * 100)  # noqa: E731
            unit = "L*" if self.lstar else "Y %"
        elif self.view == VIEW_GAMMA:
            ticks = [lo + i * 0.2 for i in range(round((hi - lo) / 0.2) + 1)]
            zero = self.inspection.target_gamma
            tick_text = lambda t: num(t, 1)  # noqa: E731
            unit = "γ"
        else:
            ticks = list(range(int(lo), int(hi) + 1, 2))
            zero = 0.0
            tick_text = lambda t: f"{t:+d}" if t else "0"  # noqa: E731
            unit = "Δ %"
        for t in ticks:
            y = self.map_point(rect, 0, self.fy(t)).y()
            p.setPen(QPen(c.zero if zero is not None and abs(t - zero) < 1e-6 else c.grid, 1))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            self.draw_label(p, c, rect.left() - 8, y, tick_text(t), Qt.AlignmentFlag.AlignRight)
        self.draw_label(p, c, rect.left() + 6, rect.top() + 10, unit, Qt.AlignmentFlag.AlignLeft)

        curves = self.curves()
        if not curves:
            self.draw_label(p, c, rect.center().x(), rect.center().y(),
                            translate("Inspector", "The profile contains no TRC curves."))
            return

        # kink markers as shaded bands
        for kink in self.inspection.kinks:
            col = c.error if kink.severity == "error" else c.warning
            x0 = self.map_point(rect, max(0.0, kink.input_pct / 100 - 0.025), 0).x()
            x1 = self.map_point(rect, min(1.0, kink.input_pct / 100 + 0.025), 0).x()
            band = QRectF(x0, rect.top(), x1 - x0, rect.height())
            p.fillRect(band, with_alpha(col, 0.12))
            p.setPen(QPen(with_alpha(col, 0.5), 1, Qt.PenStyle.DashLine))
            p.drawLine(band.topLeft(), band.bottomLeft())
            p.drawLine(band.topRight(), band.bottomRight())

        # reference
        if self.show_reference:
            ref_pen = QPen(c.reference, 1.2, Qt.PenStyle.DashLine)
            p.setPen(ref_pen)
            if self.view == VIEW_TRC:
                pts = [self.map_point(rect, i / 160, self.fy(self.value(i / 160, self.ideal(i / 160)))) for i in range(161)]
                p.drawPath(self.polyline(pts))
            else:
                y = self.map_point(rect, 0, self.fy(zero or 0.0)).y()
                p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        # curves
        x0 = self.x_start()
        for key in CHANNELS:
            if key not in self.channels or key not in curves:
                continue
            curve = curves[key]
            pts: list[QPointF] = []
            segments: list[list[QPointF]] = []
            n = 200
            for i in range(n + 1):
                x = x0 + (1 - x0) * i / n
                v = self.value(x, sample(curve, x) or 0.0)
                if v is None:
                    if pts:
                        segments.append(pts)
                        pts = []
                    continue
                pts.append(self.map_point(rect, x, self.fy(v)))
            if pts:
                segments.append(pts)
            p.setPen(QPen(c.channel(key), 1.7))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for seg in segments:
                p.drawPath(self.polyline(seg))

        # measured points from the .ti3 (single-channel ramps, gray ramp)
        if self.show_points:
            p.setBrush(c.background)
            for key, ramp in self.inspection.channel_ramps.items():
                if key not in self.channels:
                    continue
                p.setPen(QPen(c.channel(key), 1.2))
                for pct, y in ramp:
                    v = self.value(pct / 100, y)
                    if v is not None:
                        p.drawEllipse(self.map_point(rect, pct / 100, self.fy(v)), 2.6, 2.6)
            if len(self.inspection.gray_ramp) > 2:
                p.setPen(QPen(c.foreground, 1.2))
                for gp in self.inspection.gray_ramp:
                    v = self.value(gp.input_pct / 100, gp.norm_y)
                    if v is not None:
                        p.drawEllipse(self.map_point(rect, gp.input_pct / 100, self.fy(v)), 2.8, 2.8)

    # ------------------------------------------------------------------ readout

    def readout_at(self, fx: float, fy: float) -> str:
        x = max(0.0, min(1.0, fx))
        parts = [translate("Inspector", "Signal {value} %").format(value=num(x * 100, 1))]
        curves = self.curves()
        for key in CHANNELS:
            if key in self.channels and key in curves:
                y = sample(curves[key], x) or 0.0
                parts.append(f"{key} {self._format(x, y)}")
        if self.view == VIEW_TRC:
            parts.append(translate("Inspector", "Ideal {value}").format(value=self._format(x, self.ideal(x))))
        return "  ·  ".join(parts)

    def _format(self, x: float, y: float) -> str:
        if self.view == VIEW_TRC:
            return f"L* {num(to_lstar(y) * 100, 2)}" if self.lstar else num(y * 100, 2, "%")
        v = self.value(x, y)
        if v is None:
            return "–"
        if self.view == VIEW_GAMMA:
            return f"γ {num(v, 3)}"
        return ("+" if v >= 0 else "−") + num(abs(v), 2, "%")


class GamutPlot(PlotWidget):
    """Chromaticity diagram (CIE 1976 u′v′ or CIE 1931 xy) with display primaries and reference spaces."""

    REF_STYLES = {
        "sRGB": [6, 4],
        "AdobeRGB": [2, 3],
        "DCI-P3": [10, 3, 2, 3],
        "Rec.2020": [1, 3],
    }

    def __init__(self, inspection: ProfileInspection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.inspection = inspection
        self.uv = True
        self.references = {"sRGB", "DCI-P3"}
        self.show_display = True

    def set_inspection(self, inspection: ProfileInspection) -> None:
        self.inspection = inspection
        self.refresh()

    # ------------------------------------------------------------------ mapping

    def extent(self) -> tuple[float, float]:
        return (0.65, 0.6) if self.uv else (0.8, 0.9)

    def _frame(self, rect: QRectF) -> tuple[float, float, float]:
        xr, yr = self.extent()
        s = min(rect.width() / xr, rect.height() / yr)
        ox = rect.left() + (rect.width() - xr * s) / 2
        oy = rect.bottom() - (rect.height() - yr * s) / 2
        return s, ox, oy

    def to_screen(self, rect: QRectF, x: float, y: float) -> QPointF:
        a, b = xy_to_uv(x, y) if self.uv else (x, y)
        s, ox, oy = self._frame(rect)
        return QPointF(ox + a * s, oy - b * s)

    # ------------------------------------------------------------------ painting

    def paint_plot(self, p: QPainter, rect: QRectF, c: PlotColors) -> None:
        xr, yr = self.extent()
        s, ox, oy = self._frame(rect)
        steps_x = round(xr / 0.1)
        steps_y = round(yr / 0.1)
        for i in range(steps_x + 1):
            x = ox + i * 0.1 * s
            p.setPen(QPen(c.grid, 1))
            p.drawLine(QPointF(x, oy), QPointF(x, oy - yr * s))
            self.draw_label(p, c, x, rect.bottom() + 12, num(i * 0.1, 1))
        for j in range(steps_y + 1):
            y = oy - j * 0.1 * s
            p.setPen(QPen(c.grid, 1))
            p.drawLine(QPointF(ox, y), QPointF(ox + xr * s, y))
            self.draw_label(p, c, ox - 8, y, num(j * 0.1, 1), Qt.AlignmentFlag.AlignRight)

        locus = [self.to_screen(rect, x, y) for _w, x, y in SPECTRAL_LOCUS]
        path = self.polyline(locus)
        path.closeSubpath()
        p.setPen(QPen(c.reference, 1))
        p.setBrush(with_alpha(c.foreground, 0.04))
        p.drawPath(path)
        for wl, x, y in SPECTRAL_LOCUS:
            if wl in LOCUS_LABELS:
                pt = self.to_screen(rect, x, y)
                align = Qt.AlignmentFlag.AlignRight if wl < 520 else Qt.AlignmentFlag.AlignLeft
                dx = -8 if wl < 520 else 8
                dy = -10 if wl == 520 else 0
                self.draw_label(p, c, pt.x() + (0 if wl == 520 else dx), pt.y() + dy, f"{wl} nm",
                                Qt.AlignmentFlag.AlignCenter if wl == 520 else align)

        p.setBrush(Qt.BrushStyle.NoBrush)
        for name, prims in REFERENCE_GAMUTS.items():
            if name not in self.references:
                continue
            pen = QPen(c.reference, 1.1)
            pen.setDashPattern(self.REF_STYLES[name])
            p.setPen(pen)
            tri = [self.to_screen(rect, *prims[k]) for k in ("R", "G", "B")]
            tri_path = self.polyline(tri)
            tri_path.closeSubpath()
            p.drawPath(tri_path)

        prims = self.inspection.primaries_xy
        if self.show_display and all(k in prims for k in ("R", "G", "B")):
            pts = [self.to_screen(rect, *prims[k]) for k in ("R", "G", "B")]
            cols = [c.red, c.green, c.blue]
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(3):
                a, b = pts[i], pts[(i + 1) % 3]
                grad = QLinearGradient(a, b)
                grad.setColorAt(0, cols[i])
                grad.setColorAt(1, cols[(i + 1) % 3])
                pen = QPen(grad, 2.6)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(a, b)
            for pt, col in zip(pts, cols):
                p.setPen(QPen(c.background, 1.5))
                p.setBrush(col)
                p.drawEllipse(pt, 4.5, 4.5)

        d65 = self.to_screen(rect, D65_X, D65_Y)
        p.setPen(QPen(c.foreground, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(d65, 3.5, 3.5)
        self.draw_label(p, c, d65.x() + 8, d65.y() + 6, "D65", Qt.AlignmentFlag.AlignLeft, c.foreground)
        if self.inspection.white_xy is not None:
            w = self.to_screen(rect, *self.inspection.white_xy)
            p.setPen(QPen(c.warning, 1.5))
            p.drawLine(QPointF(w.x() - 5, w.y()), QPointF(w.x() + 5, w.y()))
            p.drawLine(QPointF(w.x(), w.y() - 5), QPointF(w.x(), w.y() + 5))

        self.draw_label(p, c, rect.right() - 6, rect.top() + 10,
                        "CIE 1976 u′v′" if self.uv else "CIE 1931 xy", Qt.AlignmentFlag.AlignRight)
        self._paint_legend(p, rect, c)

    def _paint_legend(self, p: QPainter, rect: QRectF, c: PlotColors) -> None:
        """Line-style legend for the reference spaces, bottom right (the empty corner of both diagrams)."""
        names = [n for n in REFERENCE_GAMUTS if n in self.references]
        if not names:
            return
        line_h = p.fontMetrics().height() + 2
        width = max(p.fontMetrics().horizontalAdvance(n) for n in names) + 44
        box = QRectF(rect.right() - width - 10, rect.bottom() - line_h * len(names) - 18, width, line_h * len(names) + 8)
        p.setPen(QPen(c.frame, 1))
        p.setBrush(with_alpha(c.background, 0.85))
        p.drawRoundedRect(box, 3, 3)
        for i, name in enumerate(names):
            y = box.top() + 4 + line_h * (i + 0.5)
            pen = QPen(c.reference, 1.1)
            pen.setDashPattern(self.REF_STYLES[name])
            p.setPen(pen)
            p.drawLine(QPointF(box.left() + 8, y), QPointF(box.left() + 30, y))
            self.draw_label(p, c, box.left() + 36, y, name, Qt.AlignmentFlag.AlignLeft, c.foreground)

    def readout_at(self, fx: float, fy: float) -> str:
        rect = self.plot_rect()
        pt = self.map_point(rect, fx, fy)
        s, ox, oy = self._frame(rect)
        a, b = (pt.x() - ox) / s, (oy - pt.y()) / s
        if self.uv:
            return f"u′ {num(a, 4)}  ·  v′ {num(b, 4)}"
        return f"x {num(a, 4)}  ·  y {num(b, 4)}"
