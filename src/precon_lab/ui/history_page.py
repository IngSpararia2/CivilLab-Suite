from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..database import session_scope
from ..services import list_batches, list_results
from .historical_explorer import HistoricalExplorerPage
from .widget_tuning import configure_table_columns, finalize_table_columns


def _set_item(table: QTableWidget, row: int, column: int, value: object) -> None:
    item = QTableWidgetItem("" if value is None else str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    table.setItem(row, column, item)


def _configure_table(
    table: QTableWidget,
    *,
    key: str,
    compact_columns: tuple[int, ...],
    narrative_columns: tuple[int, ...],
) -> None:
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)
    configure_table_columns(
        table,
        key=key,
        compact_columns=compact_columns,
        narrative_columns=narrative_columns,
    )


class ProductionHistoryPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        refresh_button = QPushButton("Actualizar producción")
        refresh_button.clicked.connect(self.refresh)
        layout.addWidget(refresh_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Fecha", "Producto", "Lote", "Cantidad", "Conjuntos", "Notas"]
        )
        _configure_table(
            self.table,
            key="production_history_v1",
            compact_columns=(0, 3, 4),
            narrative_columns=(1, 2, 5),
        )
        layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        with session_scope() as session:
            batches = list_batches(session, 1000)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(batches))
        for row, batch in enumerate(batches):
            values = [
                batch.production_date.strftime("%d/%m/%Y"),
                batch.product.display_name,
                batch.lot_code,
                batch.quantity_produced,
                len(batch.sample_sets),
                batch.notes,
            ]
            for column, value in enumerate(values):
                _set_item(self.table, row, column, value)
        self.table.setSortingEnabled(True)
        finalize_table_columns(self.table)


class ResultsHistoryPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        refresh_button = QPushButton("Actualizar resultados")
        refresh_button.clicked.connect(self.refresh)
        layout.addWidget(refresh_button, alignment=Qt.AlignmentFlag.AlignLeft)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Ensayo",
                "Producto",
                "Fabricación",
                "Edad",
                "Fecha ensayo",
                "Absorción",
                "Resistencia",
                "Módulo",
                "Estado",
            ]
        )
        _configure_table(
            self.table,
            key="results_history_v1",
            compact_columns=(2, 3, 4, 5, 6, 7, 8),
            narrative_columns=(0, 1),
        )
        layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        with session_scope() as session:
            results = list_results(session, 1000)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(results))
        for row, result in enumerate(results):
            sample_set = result.sample_set
            batch = sample_set.batch
            values = [
                result.test_type,
                batch.product.display_name,
                batch.production_date.strftime("%d/%m/%Y"),
                sample_set.target_age_days,
                result.test_date.strftime("%d/%m/%Y"),
                result.absorption_avg,
                result.strength_avg,
                result.flexural_avg,
                result.status,
            ]
            for column, value in enumerate(values):
                _set_item(self.table, row, column, value)
        self.table.setSortingEnabled(True)
        finalize_table_columns(self.table)


class HistoryPage(QWidget):
    """Integrated history area.

    The old unfiltered historical table is replaced by HistoricalExplorerPage,
    while production and application results remain available in the same area.
    """

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.production_page = ProductionHistoryPage()
        self.results_page = ResultsHistoryPage()
        self.excel_history_page = HistoricalExplorerPage()
        self.tabs.addTab(self.production_page, "Producción")
        self.tabs.addTab(self.results_page, "Resultados de la app")
        self.tabs.addTab(self.excel_history_page, "Históricos Excel")
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)

    def _tab_changed(self, _index: int) -> None:
        if self.isVisible():
            self.refresh()

    def refresh(self) -> None:
        if not self.isVisible():
            return
        current = self.tabs.currentWidget()
        refresh = getattr(current, "refresh", None)
        if callable(refresh):
            refresh()
