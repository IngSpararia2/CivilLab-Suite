from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from concrete_mix_designer.domain.models import MaterialCategory, MixDesign


CATEGORY_COLORS = {
    MaterialCategory.WATER: QColor("#4ea5d9"),
    MaterialCategory.CEMENTITIOUS: QColor("#9aa4ad"),
    MaterialCategory.FINE_AGGREGATE: QColor("#d6a85f"),
    MaterialCategory.COARSE_AGGREGATE: QColor("#6b7280"),
    MaterialCategory.ADMIXTURE: QColor("#8b5cf6"),
    MaterialCategory.AIR: QColor("#dbeafe"),
    MaterialCategory.OTHER: QColor("#2a9d8f"),
}


class VolumeStackWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._design: MixDesign | None = None
        self.setMinimumSize(208, 430)

    def set_design(self, design: MixDesign) -> None:
        self._design = design
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        margin_x = 55.0
        top = 35.0
        bottom = 75.0
        cylinder = QRectF(
            margin_x,
            top,
            max(self.width() - 2 * margin_x, 80),
            max(self.height() - top - bottom, 200),
        )

        painter.setPen(QPen(QColor("#60758a"), 2))
        painter.setBrush(QColor("#f8fafc"))
        painter.drawRoundedRect(cylinder, 16, 16)

        if self._design is None:
            painter.drawText(cylinder, Qt.AlignCenter, "Sin mezcla")
            return

        target = self._design.parameters.target_volume_l
        total = self._design.total_absolute_volume_l
        visible_total = min(total, target)
        cursor_y = cylinder.bottom()

        painter.save()
        painter.setClipPath(self._rounded_path(cylinder))
        for component in self._design.enabled_components():
            liters = component.absolute_volume_l
            if liters <= 0:
                continue
            height = cylinder.height() * min(liters, visible_total) / target
            height = min(height, max(cursor_y - cylinder.top(), 0))
            rect = QRectF(cylinder.left(), cursor_y - height, cylinder.width(), height)
            painter.fillRect(rect, CATEGORY_COLORS[component.category])
            cursor_y -= height
            if cursor_y <= cylinder.top():
                break
        painter.restore()

        painter.setPen(QPen(QColor("#12355b"), 1))
        for pct in (0, 25, 50, 75, 100):
            y = cylinder.bottom() - cylinder.height() * pct / 100.0
            painter.drawLine(cylinder.left() - 7, y, cylinder.left(), y)
            painter.drawText(
                QRectF(0, y - 10, cylinder.left() - 10, 20),
                Qt.AlignRight | Qt.AlignVCenter,
                f"{int(target * pct / 100)} L",
            )

        painter.setPen(QColor("#12355b"))
        painter.drawText(
            QRectF(0, 5, self.width(), 25),
            Qt.AlignCenter,
            f"Volumen absoluto: {total:.2f} L",
        )

        delta = target - total
        if abs(delta) <= 0.02:
            status = "CERRADO A 1000 L"
            status_color = QColor("#0b6e4f")
        elif delta > 0:
            status = f"FALTAN {delta:.2f} L"
            status_color = QColor("#b42318")
            missing_height = cylinder.height() * min(delta, target) / target
            painter.setBrush(QColor(255, 220, 220, 150))
            painter.setPen(Qt.NoPen)
            painter.drawRect(
                QRectF(cylinder.left(), cylinder.top(), cylinder.width(), missing_height)
            )
        else:
            status = f"EXCESO {-delta:.2f} L"
            status_color = QColor("#b42318")
            painter.setPen(QPen(status_color, 4))
            painter.drawLine(cylinder.left(), cylinder.top() - 8, cylinder.right(), cylinder.top() - 8)

        painter.setPen(status_color)
        painter.drawText(
            QRectF(0, self.height() - 48, self.width(), 28),
            Qt.AlignCenter,
            status,
        )

    @staticmethod
    def _rounded_path(rect: QRectF):
        from PySide6.QtGui import QPainterPath

        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        return path
