"""Inspector page "Verification" (mockup 1j): measure sRGB test patches with the active profile."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kcal_core.i18n import translate
from kcal_core.verification import (
    TOL_GRAY_CHROMA,
    TOL_MAX,
    TOL_MEAN,
    TOL_WHITE_DUV,
    VerificationResult,
    grade,
    report_html,
    test_patches,
)
from kcal_gui.fmt import num
from kcal_gui.inspector.plot_base import plot_colors, with_alpha
from kcal_gui.theme import status_colors
from kcal_gui.widgets import Card, SecondaryLabel, mono_font, title_font

# start(profile_label, on_progress(current, total), on_done(result), on_failed(message)) -> cancel()
VerifyStarter = Callable[[str, Callable[[int, int], None], Callable[[VerificationResult], None],
                          Callable[[str], None]], Callable[[], None]]


class _StateLabel(QLabel):
    """Label whose text colour follows a status ("ok"/"warning"/"error"), resolved at paint time."""

    state = ""

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        color = getattr(status_colors(self.palette()), self.state, None) if self.state else None
        if color is None:
            super().paintEvent(event)
            return
        p = QPainter(self)
        p.setPen(color)
        p.setFont(self.font())
        p.drawText(self.contentsRect(), int(self.alignment()), self.text())


class _Kpi(QWidget):
    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(SecondaryLabel(caption))
        self.value = _StateLabel("–")
        font = mono_font()
        font.setPointSizeF(self.font().pointSizeF() * 1.45)
        self.value.setFont(font)
        self.note = SecondaryLabel()
        lay.addWidget(self.value)
        lay.addWidget(self.note)

    def set(self, value: str, note: str = "", state: str = "") -> None:
        self.value.setText(value)
        self.value.state = state
        self.value.update()
        self.note.setText(note)


class GrayBalancePlot(QWidget):
    """a*b* deviations of the gray patches (relative to their expectation) with 1.0 / 2.0 circles."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result: VerificationResult | None = None
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(280, 280)

    def set_result(self, result: VerificationResult | None) -> None:
        self.result = result
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        c = plot_colors(self.palette())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), c.background)
        size = min(self.width(), self.height()) - 24
        centre = QPointF(self.width() / 2, self.height() / 2)
        gray = self.result.gray if self.result else []
        extent = max(3.0, *(max(abs(g.measured_lab[1] - g.expected_lab[1]), abs(g.measured_lab[2] - g.expected_lab[2]))
                            for g in gray)) if gray else 3.0
        k = size / 2 / extent
        p.setFont(mono_font(-1))
        p.setPen(QPen(c.grid, 1))
        p.drawLine(QPointF(centre.x() - size / 2, centre.y()), QPointF(centre.x() + size / 2, centre.y()))
        p.drawLine(QPointF(centre.x(), centre.y() - size / 2), QPointF(centre.x(), centre.y() + size / 2))
        for radius, color in ((TOL_GRAY_CHROMA[0], c.ok), (TOL_GRAY_CHROMA[1], c.warning)):
            pen = QPen(with_alpha(color, 0.7), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(centre, radius * k, radius * k)
            p.drawText(QPointF(centre.x() + radius * k * 0.72 + 3, centre.y() - radius * k * 0.72 - 3), num(radius, 1))
        p.setPen(c.label)
        p.drawText(QRectF(centre.x() + size / 2 - 40, centre.y() - 16, 40, 14), Qt.AlignmentFlag.AlignRight, "+a*")
        p.drawText(QRectF(centre.x() + 4, centre.y() - size / 2, 40, 14), Qt.AlignmentFlag.AlignLeft, "+b*")
        if not gray:
            return
        pts = [QPointF(centre.x() + (g.measured_lab[1] - g.expected_lab[1]) * k,
                       centre.y() - (g.measured_lab[2] - g.expected_lab[2]) * k) for g in gray]
        p.setPen(QPen(c.reference, 1.2))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
        for g, pt in zip(gray, pts):
            p.setPen(QPen(c.foreground, 1))
            p.setBrush(QColor(*g.patch.rgb))
            p.drawEllipse(pt, 4.5, 4.5)


class VerificationPage(QWidget):
    """Start button, progress, KPIs, patch table (sortable) and gray balance plot; HTML report."""

    def __init__(self, starter: VerifyStarter | None, profile_label: Callable[[], str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.starter = starter
        self.profile_label = profile_label
        self.result: VerificationResult | None = None
        self._cancel: Callable[[], None] | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        head = Card()
        row = QHBoxLayout()
        col = QVBoxLayout()
        title = QLabel(translate("Inspector", "Verification (ΔE2000)"))
        title.setFont(title_font(self, 1.1))
        col.addWidget(title)
        self.info = SecondaryLabel()
        self.info.setWordWrap(True)
        col.addWidget(self.info)
        row.addLayout(col, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.hide()
        row.addWidget(self.progress)
        self.btn_start = QPushButton(translate("Inspector", "Measure Verification"))
        self.btn_start.setDefault(False)
        self.btn_start.clicked.connect(self.start)
        self.btn_cancel = QPushButton(translate("Inspector", "Cancel"))
        self.btn_cancel.clicked.connect(self.cancel)
        self.btn_cancel.hide()
        self.btn_report = QPushButton(translate("Inspector", "Save Report…"))
        self.btn_report.clicked.connect(self.save_report)
        self.btn_report.setEnabled(False)
        for b in (self.btn_start, self.btn_cancel, self.btn_report):
            row.addWidget(b)
        head.body.addLayout(row)
        lay.addWidget(head)

        kpis = Card()
        krow = QHBoxLayout()
        krow.setSpacing(28)
        self.kpi_mean = _Kpi(translate("Inspector", "Mean ΔE00"))
        self.kpi_max = _Kpi(translate("Inspector", "Max ΔE00"))
        self.kpi_gray = _Kpi(translate("Inspector", "Gray balance"))
        self.kpi_white = _Kpi(translate("Inspector", "Whitepoint"))
        self.kpi_lum = _Kpi(translate("Inspector", "White / black"))
        for k in (self.kpi_mean, self.kpi_max, self.kpi_gray, self.kpi_white, self.kpi_lum):
            krow.addWidget(k)
        krow.addStretch(1)
        kpis.body.addLayout(krow)
        lay.addWidget(kpis)

        body = QHBoxLayout()
        body.setSpacing(12)
        table_card = Card()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "#", translate("Inspector", "Patch"), translate("Inspector", "Target / measured"), "sRGB", "ΔE00"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        table_card.body.addWidget(self.table)
        body.addWidget(table_card, 3)
        gray_card = Card()
        gray_title = QLabel(translate("Inspector", "Gray balance a*b*"))
        gray_title.setFont(title_font(self, 1.0))
        gray_card.body.addWidget(gray_title)
        self.gray_plot = GrayBalancePlot()
        gray_card.body.addWidget(self.gray_plot, 1)
        gray_card.body.addWidget(SecondaryLabel(translate(
            "Inspector", "Deviation of the gray patches from neutral; circles at 1.0 and 2.0.")))
        body.addWidget(gray_card, 2)
        lay.addLayout(body, 1)
        self._update_info()

    # ------------------------------------------------------------------ run

    def _update_info(self) -> None:
        if self.starter is None:
            self.info.setText(translate(
                "Inspector", "Measuring needs the display this profile belongs to: open the inspector from the "
                "calibration or via the display (↗)."))
            self.btn_start.setEnabled(False)
            return
        self.info.setText(translate(
            "Inspector", "Measures {count} sRGB test patches (ColorChecker, gray ramp, primaries) with the "
            "currently active profile – {profile}. Use the live preview to verify another state.").format(
            count=len(test_patches()), profile=self.profile_label()))

    def start(self) -> None:
        if self.starter is None or self._cancel is not None:
            return
        self._update_info()
        self.btn_start.hide()
        self.btn_cancel.show()
        self.progress.setValue(0)
        self.progress.show()
        self._cancel = lambda: None  # running; the starter may already report done/failed synchronously
        stop = self.starter(self.profile_label(), self._on_progress, self._on_done, self._on_failed)
        if self._cancel is not None:
            self._cancel = stop

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel()

    def is_running(self) -> bool:
        return self._cancel is not None

    def _finish(self) -> None:
        self._cancel = None
        self.btn_cancel.hide()
        self.btn_start.show()
        self.btn_start.setText(translate("Inspector", "Measure Again"))
        self.progress.hide()

    def _on_progress(self, current: int, total: int) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(current)

    def _on_failed(self, message: str) -> None:
        self._finish()
        if message:
            QMessageBox.warning(self, translate("Inspector", "Verification"), message)

    def _on_done(self, result: VerificationResult) -> None:
        self._finish()
        self.set_result(result)

    # ------------------------------------------------------------------ display

    def set_result(self, result: VerificationResult) -> None:
        self.result = result
        self.btn_report.setEnabled(True)
        worst = result.maximum
        self.kpi_mean.set(num(result.mean, 2), translate("Inspector", "recommended ≤ {r}, nominal ≤ {n}").format(
            r=num(TOL_MEAN[0], 1), n=num(TOL_MEAN[1], 1)), grade(result.mean, TOL_MEAN))
        if worst:
            self.kpi_max.set(num(worst.delta_e, 2), worst.patch.display_name, grade(worst.delta_e, TOL_MAX))
        self.kpi_gray.set(num(result.gray_chroma_max, 2), translate("Inspector", "max Δa*b* of the grays"),
                          grade(result.gray_chroma_max, TOL_GRAY_CHROMA))
        self.kpi_white.set(f"Δu′v′ {num(result.white_duv, 4)}", translate("Inspector", "to target"),
                           grade(result.white_duv, TOL_WHITE_DUV))
        contrast = f" · {num(result.contrast)} : 1" if result.contrast else ""
        self.kpi_lum.set(num(result.white_luminance, 1, "cd/m²"),
                         num(result.black_xyz[1], 3, "cd/m²") + contrast)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(result.patches))
        for row, p in enumerate(result.patches):
            nr = QTableWidgetItem()
            nr.setData(Qt.ItemDataRole.DisplayRole, row + 1)
            self.table.setItem(row, 0, nr)
            self.table.setItem(row, 1, QTableWidgetItem(p.patch.display_name))
            self.table.setCellWidget(row, 2, _Pair(p.patch.rgb, p.measured_xyz, result.white_xyz))
            rgb = QTableWidgetItem(" ".join(f"{v:3d}" for v in p.patch.rgb))
            rgb.setFont(mono_font())
            self.table.setItem(row, 3, rgb)
            de = _NumberItem(num(p.delta_e, 2), p.delta_e)
            de.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            state = grade(p.delta_e, (2.0, 3.0))
            if state != "ok":
                de.setForeground(getattr(status_colors(self.palette()), state))
            self.table.setItem(row, 4, de)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.gray_plot.set_result(result)

    def save_report(self) -> None:
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, translate("Inspector", "Save Verification Report"),
            f"kelvincal-verification-{datetime.now():%Y-%m-%d_%H-%M}.html",
            translate("Inspector", "HTML files (*.html)"))
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(report_html(self.result))


class _NumberItem(QTableWidgetItem):
    """Locale-formatted text, sorted by the numeric value."""

    def __init__(self, text: str, value: float) -> None:
        super().__init__(text)
        self.value = value

    def __lt__(self, other: QTableWidgetItem) -> bool:
        return self.value < getattr(other, "value", 0.0)


class _Pair(QWidget):
    """Target (sRGB) and measured colour side by side (measured shown relative to the measured white)."""

    def __init__(self, rgb: tuple[int, int, int], xyz: tuple[float, float, float],
                 white: tuple[float, float, float], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.target = QColor(*rgb)
        self.measured = _xyz_to_srgb_color(xyz, white)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(70, 18)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        p = QPainter(self)
        h = self.height() - 6
        w = 28
        x = 6
        p.fillRect(QRectF(x, 3, w, h), self.target)
        p.fillRect(QRectF(x + w + 2, 3, w, h), self.measured)


def _xyz_to_srgb_color(xyz: tuple[float, float, float], white: tuple[float, float, float]) -> QColor:
    """Approximate on-screen rendering of a measurement (white-relative, sRGB encoded, clipped)."""
    y_white = white[1] or 1.0
    x, y, z = (v / y_white for v in xyz)
    lin = (3.2406 * x - 1.5372 * y - 0.4986 * z, -0.9689 * x + 1.8758 * y + 0.0415 * z,
           0.0557 * x - 0.2040 * y + 1.0570 * z)

    def enc(v: float) -> int:
        v = max(0.0, min(1.0, v))
        return round(255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055))

    return QColor(*(enc(v) for v in lin))
