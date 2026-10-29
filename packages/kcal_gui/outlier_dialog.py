"""Measurement plausibility dialog (mockup 1i): shown between patch measurement and colprof."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kcal_argyll.ti3_check import MeasurementCheck
from kcal_core.i18n import translate
from kcal_gui.controller import REVIEW_ACCEPT, REVIEW_CANCEL, REVIEW_REMEASURE
from kcal_gui.fmt import num
from kcal_gui.theme import status_colors
from kcal_gui.widgets import MessageBanner, SecondaryLabel, mix, mono_font, title_font


class OutlierPlot(QWidget):
    """Stem plot of ΔE00 per patch in measurement order with the threshold line."""

    def __init__(self, check: MeasurementCheck, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.check = check
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(720, 150)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        pal = self.palette()
        base, text = pal.color(QPalette.ColorRole.Base), pal.color(QPalette.ColorRole.Text)
        warn = status_colors(pal).warning
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), base)
        p.setFont(mono_font(-1))
        fm = p.fontMetrics()
        scores = self.check.scores
        n = max(1, len(scores))
        top = max([self.check.threshold * 1.5, *scores])
        plot = QRectF(8, 8, self.width() - 16, self.height() - 16 - fm.height())

        def y(v: float) -> float:
            return plot.bottom() - min(v, top) / top * plot.height()

        def x(i: int) -> float:
            return plot.left() + (i + 0.5) / n * plot.width()

        p.setPen(QPen(mix(base, text, 0.3), 1))
        p.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
        outlier_idx = {o.patch.index for o in self.check.outliers}
        normal = QPen(mix(base, text, 0.4), 1)
        for i, s in enumerate(scores):
            if i not in outlier_idx:
                p.setPen(normal)
                p.drawLine(QPointF(x(i), plot.bottom()), QPointF(x(i), y(s)))
        threshold_pen = QPen(warn, 1, Qt.PenStyle.DashLine)
        p.setPen(threshold_pen)
        ty = y(self.check.threshold)
        p.drawLine(QPointF(plot.left(), ty), QPointF(plot.right(), ty))
        p.drawText(QPointF(plot.left() + 4, ty - 4), f"ΔE00 {num(self.check.threshold, 1)}")
        for o in self.check.outliers:
            i = o.patch.index
            p.setPen(QPen(warn, 2.5))
            p.drawLine(QPointF(x(i), plot.bottom()), QPointF(x(i), y(o.delta_e)))
            p.setPen(text)
            label = translate("OutlierDialog", "Patch {id}").format(id=o.patch.sample_id)
            lx = min(x(i) + 5, plot.right() - fm.horizontalAdvance(label))
            p.drawText(QPointF(lx, max(plot.top() + fm.ascent(), y(o.delta_e) + fm.ascent() / 2)), label)
        p.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
        p.drawText(QRectF(plot.left(), plot.bottom() + 2, plot.width(), fm.height()),
                   Qt.AlignmentFlag.AlignLeft, "1")
        p.drawText(QRectF(plot.left(), plot.bottom() + 2, plot.width(), fm.height()),
                   Qt.AlignmentFlag.AlignRight, str(len(scores)))
        p.drawText(QRectF(plot.left(), plot.bottom() + 2, plot.width(), fm.height()),
                   Qt.AlignmentFlag.AlignHCenter, translate("OutlierDialog", "measurement order"))


class _Swatch(QWidget):
    def __init__(self, rgb: tuple[float, float, float], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color = QColor(*(round(v * 255 / 100) for v in rgb))
        self.setFixedSize(28, 16)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        p = QPainter(self)
        p.fillRect(self.rect(), self.color)
        p.setPen(mix(self.palette().color(QPalette.ColorRole.Base), self.palette().color(QPalette.ColorRole.Text), 0.3))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


class OutlierDialog(QDialog):
    """Lists implausible patches and lets the user re-measure them, keep them or cancel."""

    def __init__(self, check: MeasurementCheck, attempt: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.decision = REVIEW_CANCEL
        self.setWindowTitle(translate("OutlierDialog", "Check Measurements – KelvinCal"))
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)

        count = len(check.outliers)
        title = QLabel(translate("OutlierDialog", "{count} measurement(s) deviate strongly").format(count=count))
        title.setFont(title_font(self, 1.3))
        lay.addWidget(title)
        intro = SecondaryLabel(translate(
            "OutlierDialog", "Found after the patch measurement, before the profile is computed. Possible causes: "
            "a notification briefly covered the patch window, or the sensor slipped."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        if attempt:
            banner = MessageBanner(translate(
                "OutlierDialog", "These patches still deviate after re-measuring. If they stay off, the display "
                "may really behave like this there – then compute the profile anyway."), "warning")
            lay.addWidget(banner)

        lay.addWidget(SecondaryLabel(translate("OutlierDialog", "ΔE00 to the expected course, all {n} patches")
                                     .format(n=len(check.scores))))
        lay.addWidget(OutlierPlot(check))

        table = QTableWidget(count, 3)
        table.setHorizontalHeaderLabels([
            translate("OutlierDialog", "Patch"), translate("OutlierDialog", "Target"), "ΔE00"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setFont(mono_font())
        for row, o in enumerate(check.outliers):
            table.setItem(row, 0, QTableWidgetItem(translate("OutlierDialog", "Patch {id}").format(id=o.patch.sample_id)))
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(6, 0, 6, 0)
            cl.addWidget(_Swatch(o.patch.rgb))
            rgb8 = " ".join(f"{round(v * 255 / 100):3d}" for v in o.patch.rgb)
            cl.addWidget(QLabel(f"RGB {rgb8}"))
            cl.addStretch(1)
            table.setCellWidget(row, 1, cell)
            de = QTableWidgetItem(num(o.delta_e, 2))
            de.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 2, de)
        table.resizeColumnToContents(0)
        lay.addWidget(table, 1)

        consecutive = [(a, b) for a, b in zip(check.outliers, check.outliers[1:]) if b.patch.index == a.patch.index + 1]
        if consecutive:
            a, b = consecutive[0]
            note = SecondaryLabel(translate(
                "OutlierDialog", "Patches {a} and {b} were measured directly one after the other – typical of a "
                "notification.").format(a=a.patch.sample_id, b=b.patch.sample_id))
            note.setWordWrap(True)
            lay.addWidget(note)

        buttons = QHBoxLayout()
        btn_cancel = QPushButton(translate("OutlierDialog", "Cancel Calibration"))
        btn_cancel.clicked.connect(lambda: self._done(REVIEW_CANCEL))
        btn_accept = QPushButton(translate("OutlierDialog", "Compute Profile Anyway"))
        btn_accept.clicked.connect(lambda: self._done(REVIEW_ACCEPT))
        btn_again = QPushButton(translate("OutlierDialog", "Re-measure Patches"))
        btn_again.setDefault(True)
        btn_again.setToolTip(translate("OutlierDialog", "Shows these patches again on the display and measures them "
                                                        "with the sensor in place."))
        btn_again.clicked.connect(lambda: self._done(REVIEW_REMEASURE))
        buttons.addWidget(btn_cancel)
        buttons.addStretch(1)
        buttons.addWidget(btn_accept)
        buttons.addWidget(btn_again)
        lay.addLayout(buttons)

    def _done(self, decision: str) -> None:
        self.decision = decision
        self.accept()

    def reject(self) -> None:  # Esc / window close = cancel
        self.decision = REVIEW_CANCEL
        super().reject()
