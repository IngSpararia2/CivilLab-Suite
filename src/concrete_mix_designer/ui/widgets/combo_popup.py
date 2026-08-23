from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate


class ComboPopupItemDelegate(QStyledItemDelegate):
    """Provides comfortably sized rows for combo popup options."""

    MINIMUM_ROW_HEIGHT = 38

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), self.MINIMUM_ROW_HEIGHT))
        return size


class ComboPopupSizer(QObject):
    """Makes every combo popup wide enough to display its longest option."""

    _TEXT_PADDING = 64

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if isinstance(watched, QComboBox) and event.type() in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.KeyPress,
        }:
            self.resize_popup(watched)
        return super().eventFilter(watched, event)

    @classmethod
    def resize_popup(cls, combo: QComboBox) -> None:
        view = combo.view()
        if not isinstance(combo.itemDelegate(), ComboPopupItemDelegate):
            combo.setItemDelegate(ComboPopupItemDelegate(view))
        model = combo.model()
        root = combo.rootModelIndex()
        font_metrics = view.fontMetrics()
        widest_text = 0

        for row in range(model.rowCount(root)):
            index = model.index(row, combo.modelColumn(), root)
            text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            widest_text = max(widest_text, font_metrics.horizontalAdvance(text))

        desired_width = max(combo.width(), widest_text + cls._TEXT_PADDING)
        if screen := combo.screen():
            desired_width = min(desired_width, screen.availableGeometry().width() - 48)

        view.setMinimumWidth(desired_width)
        view.setTextElideMode(Qt.TextElideMode.ElideNone)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
