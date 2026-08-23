"""Ajustes de ergonomía compartidos para controles complejos de Qt."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QTableView,
    QTableWidget,
    QWidget,
)

from civillab_suite.ui.shared_controls import tune_shared_controls


def tune_table_headers(root: QWidget) -> None:
    """Alinea encabezados sin imponer anchos excesivos a columnas cortas."""

    for table in root.findChildren(QTableView):
        header = table.horizontalHeader()
        header.setMinimumHeight(38)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setTextElideMode(Qt.TextElideMode.ElideRight)
        header.setMinimumSectionSize(36)

        if isinstance(table, QTableWidget):
            for column in range(table.columnCount()):
                item = table.horizontalHeaderItem(column)
                if item is not None:
                    item.setToolTip(item.text())


def configure_table_columns(
    table: QTableView,
    *,
    key: str,
    compact_columns: tuple[int, ...] = (),
    narrative_columns: tuple[int, ...] = (),
    initial_widths: dict[int, int] | None = None,
    content_sizing: bool = True,
) -> None:
    """Registra una tabla redimensionable con estado persistente por usuario."""

    header = table.horizontalHeader()
    for column in range(table.model().columnCount()):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table._column_layout = {
        "key": key,
        "compact_columns": set(compact_columns),
        "narrative_columns": set(narrative_columns),
        "initial_widths": initial_widths or {},
        "content_sizing": content_sizing,
        "ready": False,
        "restored": False,
    }

    saved_state = QSettings().value(f"table_headers/{key}")
    if saved_state is not None and header.restoreState(saved_state):
        table._column_layout["ready"] = True
        table._column_layout["restored"] = True

    def save_state(*_args) -> None:
        layout = getattr(table, "_column_layout", None)
        if layout and layout["ready"]:
            QSettings().setValue(f"table_headers/{layout['key']}", header.saveState())

    header.sectionResized.connect(save_state)
    header.sectionMoved.connect(save_state)


def finalize_table_columns(table: QTableView) -> None:
    """Aplica una sola vez anchos iniciales, sin alterar ajustes del usuario."""

    layout = getattr(table, "_column_layout", None)
    if not layout or layout["ready"]:
        return

    header = table.horizontalHeader()
    for column in range(table.model().columnCount()):
        has_explicit_width = column in layout["initial_widths"]
        if has_explicit_width:
            width = layout["initial_widths"][column]
        elif layout["content_sizing"]:
            width = max(header.sectionSizeHint(column), table.sizeHintForColumn(column))
        else:
            width = header.sectionSizeHint(column)

        if not has_explicit_width:
            if column in layout["compact_columns"]:
                width = min(max(width, 58), 150)
            elif column in layout["narrative_columns"]:
                width = min(max(width, 150), 360)
            else:
                width = min(max(width, 90), 260)
        header.resizeSection(column, width)
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)

    layout["ready"] = True
    QSettings().setValue(f"table_headers/{layout['key']}", header.saveState())


def tune_widget_tree(root: QWidget) -> None:
    """Aplica la ergonomía compartida también a diálogos creados dinámicamente."""

    tune_shared_controls(root)
    tune_table_headers(root)
