from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Any, Callable, Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QDate, QModelIndex, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableView,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..database import session_scope
from ..historical_queries import (
    HistoricalFilters,
    HistoricalProductionSummary,
    HistoricalTestSummary,
    count_historical_productions,
    list_reading_statuses,
    query_historical_production_page,
    query_historical_specimens,
    query_historical_tests_for_production,
)
from .widget_tuning import configure_table_columns, finalize_table_columns

DisplayGetter = Callable[[Any], Any]


def qdate_to_date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def date_text(value: Optional[date]) -> str:
    return value.strftime("%d/%m/%Y") if value is not None else ""


def number_text(value: Optional[float], decimals: int = 3) -> str:
    if value is None:
        return ""
    return f"{value:.{decimals}f}"


def _sort_key(value: Any) -> Any:
    if isinstance(value, str):
        return value.casefold()
    return value


@dataclass(frozen=True)
class TableColumn:
    title: str
    getter: DisplayGetter
    formatter: Callable[[Any], str] = str
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft


class RecordTableModel(QAbstractTableModel):
    """Modelo ligero: almacena dataclasses, no widgets por celda."""

    def __init__(self, columns: Sequence[TableColumn]) -> None:
        super().__init__()
        self.columns = list(columns)
        self.rows: list[Any] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        column = self.columns[index.column()]
        value = column.getter(row)

        if role == Qt.ItemDataRole.DisplayRole:
            if value is None:
                return ""
            return column.formatter(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(column.alignment | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.UserRole:
            return value
        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.columns):
            if role in (
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.ToolTipRole,
            ):
                return self.columns[section].title
        return super().headerData(section, orientation, role)

    def set_rows(self, rows: Sequence[Any]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def record(self, row: int) -> Any | None:
        if 0 <= row < len(self.rows):
            return self.rows[row]
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if not 0 <= column < len(self.columns):
            return
        getter = self.columns[column].getter
        valued = [item for item in self.rows if getter(item) is not None]
        empty = [item for item in self.rows if getter(item) is None]
        valued.sort(
            key=lambda item: _sort_key(getter(item)),
            reverse=order == Qt.SortOrder.DescendingOrder,
        )
        self.layoutAboutToBeChanged.emit()
        self.rows = valued + empty
        self.layoutChanged.emit()


def _make_table(model: RecordTableModel, *, layout_key: str) -> QTableView:
    table = QTableView()
    table.setModel(model)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSortingEnabled(True)
    table.setWordWrap(False)
    table.setCornerButtonEnabled(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(25)
    table.horizontalHeader().setStretchLastSection(False)
    configure_table_columns(
        table,
        key=layout_key,
        narrative_columns=(0, 1),
        content_sizing=False,
    )
    finalize_table_columns(table)
    return table


def _fit_table_height(table: QTableView, row_count: int, maximum_rows: int) -> None:
    visible_rows = max(1, min(row_count, maximum_rows))
    row_height = table.verticalHeader().defaultSectionSize()
    header_height = table.horizontalHeader().height() or 28
    table.setFixedHeight(header_height + visible_rows * row_height + 8)


def _test_columns(test_type: str, profile: str) -> list[TableColumn]:
    center = Qt.AlignmentFlag.AlignCenter
    right = Qt.AlignmentFlag.AlignRight
    code = TableColumn("Código ensayo", lambda row: row.test_code)
    test_date_column = TableColumn("Fecha ensayo", lambda row: row.test_date, date_text, center)
    age = TableColumn("Edad", lambda row: row.target_age_days, str, center)
    density = TableColumn("Densidad", lambda row: row.density_avg, number_text, right)
    absorption = TableColumn("Absorción", lambda row: row.absorption_avg, number_text, right)
    load = TableColumn("Carga máxima", lambda row: row.maximum_load_avg, number_text, right)
    reading = TableColumn("Lectura", lambda row: row.reading_status)

    if test_type == "COMPRESSION":
        result = TableColumn("Resistencia", lambda row: row.strength_avg, number_text, right)
        masses = [
            TableColumn("Masa natural", lambda row: row.natural_mass_avg, number_text, right),
            TableColumn("Masa seca", lambda row: row.dry_mass_avg, number_text, right),
            TableColumn("Masa inmersa", lambda row: row.immersed_mass_avg, number_text, right),
            TableColumn("Masa saturada", lambda row: row.saturated_mass_avg, number_text, right),
        ]
        test_metrics = [load, absorption, result]
    else:
        result = TableColumn("Módulo de rotura", lambda row: row.flexural_avg, number_text, right)
        masses = [
            TableColumn("Masa seca", lambda row: row.dry_mass_avg, number_text, right),
            TableColumn("Masa inmersa", lambda row: row.immersed_mass_avg, number_text, right),
            TableColumn("Masa saturada", lambda row: row.saturated_mass_avg, number_text, right),
        ]
        test_metrics = [
            load,
            absorption,
            TableColumn("Espesor", lambda row: row.thickness_avg, number_text, right),
            result,
        ]

    if profile == "MASSES":
        return [code, test_date_column, age] + masses + [density]
    if profile == "TEST":
        return [code, test_date_column, age] + test_metrics
    if profile == "TRACE":
        return [
            code,
            TableColumn("Producto", lambda row: row.product_code),
            test_date_column,
            age,
            TableColumn("Archivo", lambda row: row.source_file),
            reading,
            TableColumn("Incidencias", lambda row: row.incidents),
        ]
    if profile == "ALL":
        return [code, test_date_column, age] + masses + [density] + test_metrics + [
            TableColumn("Archivo", lambda row: row.source_file),
            reading,
            TableColumn("Incidencias", lambda row: row.incidents),
        ]
    return [code, test_date_column, age, density, absorption, result, reading]


def _specimen_columns(test_type: str, profile: str) -> list[TableColumn]:
    center = Qt.AlignmentFlag.AlignCenter
    right = Qt.AlignmentFlag.AlignRight
    label = "Bloque" if test_type == "COMPRESSION" else "Muestra"
    ordinal = TableColumn(label, lambda row: row.ordinal, lambda value: f"{label} {value}", center)
    code = TableColumn("Código muestra", lambda row: row.specimen_code)
    production_date = TableColumn("Fecha fabricación", lambda row: row.production_date, date_text, center)
    age = TableColumn("Edad", lambda row: row.age_days, str, center)
    density = TableColumn("Densidad", lambda row: row.density, number_text, right)
    absorption = TableColumn("Absorción", lambda row: row.absorption, number_text, right)
    load = TableColumn("Carga máxima", lambda row: row.maximum_load, number_text, right)

    if test_type == "COMPRESSION":
        result = TableColumn("Resistencia", lambda row: row.strength, number_text, right)
        masses = [
            TableColumn("Masa natural", lambda row: row.natural_mass, number_text, right),
            TableColumn("Masa seca", lambda row: row.dry_mass, number_text, right),
            TableColumn("Masa inmersa", lambda row: row.immersed_mass, number_text, right),
            TableColumn("Masa saturada", lambda row: row.saturated_mass, number_text, right),
        ]
        test_metrics = [load, absorption, result]
    else:
        result = TableColumn("Módulo de rotura", lambda row: row.flexural_modulus, number_text, right)
        masses = [
            TableColumn("Masa seca", lambda row: row.dry_mass, number_text, right),
            TableColumn("Masa inmersa", lambda row: row.immersed_mass, number_text, right),
            TableColumn("Masa saturada", lambda row: row.saturated_mass, number_text, right),
        ]
        test_metrics = [
            load,
            absorption,
            TableColumn("Espesor", lambda row: row.thickness, number_text, right),
            result,
        ]

    if profile == "MASSES":
        return [ordinal, code, production_date, age] + masses + [density]
    if profile == "TEST":
        return [ordinal, code, age] + test_metrics
    if profile == "TRACE":
        return [
            ordinal,
            code,
            TableColumn("Material", lambda row: row.material),
            production_date,
            age,
        ]
    if profile == "ALL":
        return [ordinal, code, production_date, age] + masses + [density] + test_metrics
    return [ordinal, code, density, absorption, result]


class ProductionCard(QFrame):
    """Una producción desplegable con carga diferida de ensayos y muestras."""

    def __init__(
        self,
        *,
        production: HistoricalProductionSummary,
        test_type: str,
        filters: HistoricalFilters,
        profile: str,
    ) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.production = production
        self.test_type = test_type
        self.filters = filters
        self.profile = profile
        self._body_created = False
        self._tests: list[HistoricalTestSummary] = []

        self.setFrameShape(QFrame.Shape.StyledPanel)
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(4)

        header = QGridLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.toggle = QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolTip("Mostrar u ocultar los ensayos de esta producción")
        self.toggle.toggled.connect(self._toggle_body)

        values = [
            production.production_code,
            production.product_code,
            date_text(production.production_date),
            str(production.test_count),
            production.file_summary,
            production.reading_summary,
        ]
        header.addWidget(self.toggle, 0, 0)
        for index, value in enumerate(values, start=1):
            label = QLabel(value)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if index == 1:
                font = QFont()
                font.setBold(True)
                label.setFont(font)
            header.addWidget(label, 0, index)

        header.setColumnStretch(1, 3)
        header.setColumnStretch(2, 2)
        header.setColumnStretch(3, 1)
        header.setColumnStretch(4, 1)
        header.setColumnStretch(5, 2)
        header.setColumnStretch(6, 1)
        root.addLayout(header)

        self.body = QWidget()
        self.body.setVisible(False)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(30, 4, 4, 6)
        root.addWidget(self.body)

    def collapse(self) -> None:
        self.toggle.setChecked(False)

    def _toggle_body(self, checked: bool) -> None:
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        if checked and not self._body_created:
            self._create_body()
        self.body.setVisible(checked)

    def _create_body(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with session_scope() as session:
                self._tests = query_historical_tests_for_production(
                    session,
                    test_type=self.test_type,
                    product_code=self.production.product_code,
                    production_date=self.production.production_date,
                    filters=self.filters,
                )

            title = QLabel(
                f"Ensayos de {self.production.production_code}: "
                f"{len(self._tests)} registro(s). Selecciona uno para ver sus muestras."
            )
            title.setWordWrap(True)
            self.body_layout.addWidget(title)

            self.test_model = RecordTableModel(
                _test_columns(self.test_type, self.profile)
            )
            self.test_model.set_rows(self._tests)
            self.test_table = _make_table(
                self.test_model,
                layout_key=f"historical_{self.test_type}_{self.profile}_tests_v1",
            )
            self.test_table.selectionModel().currentRowChanged.connect(
                self._test_changed
            )
            self.body_layout.addWidget(self.test_table)
            _fit_table_height(self.test_table, len(self._tests), 7)

            self.specimen_title = QLabel(
                "Muestras individuales: selecciona un ensayo en la tabla superior."
            )
            self.specimen_title.setWordWrap(True)
            self.body_layout.addWidget(self.specimen_title)

            self.specimen_model = RecordTableModel(
                _specimen_columns(self.test_type, self.profile)
            )
            self.specimen_table = _make_table(
                self.specimen_model,
                layout_key=f"historical_{self.test_type}_{self.profile}_specimens_v1",
            )
            self.specimen_table.setVisible(False)
            self.body_layout.addWidget(self.specimen_table)
            self._body_created = True
        except Exception as error:
            QMessageBox.critical(
                self,
                "No se pudieron cargar los ensayos",
                str(error),
            )
            self.toggle.setChecked(False)
        finally:
            QApplication.restoreOverrideCursor()

    def _test_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        test = self.test_model.record(current.row()) if current.isValid() else None
        if test is None:
            self.specimen_model.set_rows([])
            self.specimen_table.setVisible(False)
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with session_scope() as session:
                specimens = query_historical_specimens(
                    session,
                    historical_test_id=test.id,
                )
            self.specimen_model.set_rows(specimens)
            self.specimen_title.setText(
                f"Muestras individuales de {test.test_code}: {len(specimens)} registro(s)."
            )
            self.specimen_table.setVisible(True)
            _fit_table_height(self.specimen_table, len(specimens), 6)
        except Exception as error:
            QMessageBox.critical(
                self,
                "No se pudieron cargar las muestras",
                str(error),
            )
        finally:
            QApplication.restoreOverrideCursor()


@dataclass
class AdvancedFiltersState:
    date_field: str = "production"
    use_date_from: bool = False
    date_from: QDate | None = None
    use_date_to: bool = False
    date_to: QDate | None = None
    age_min: int = 0
    age_max: int = 0
    reading_status: str = ""
    incidents_mode: str = "ALL"


class AdvancedFiltersDialog(QDialog):
    """Editor temporal de filtros avanzados, sin cambios hasta confirmar."""

    def __init__(
        self,
        *,
        state: AdvancedFiltersState,
        reading_statuses: list[str],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filtros avanzados")
        self.setModal(True)

        layout = QGridLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        self.date_field = QComboBox()
        self.date_field.addItem("Fecha de fabricación", "production")
        self.date_field.addItem("Fecha de ensayo", "test")
        self.date_field.setCurrentIndex(max(0, self.date_field.findData(state.date_field)))

        self.use_date_from = QCheckBox("Activar desde")
        self.use_date_from.setChecked(state.use_date_from)
        self.date_from = QDateEdit(state.date_from or QDate.currentDate().addYears(-1))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd/MM/yyyy")
        self.date_from.setEnabled(state.use_date_from)
        self.use_date_from.toggled.connect(self.date_from.setEnabled)

        self.use_date_to = QCheckBox("Activar hasta")
        self.use_date_to.setChecked(state.use_date_to)
        self.date_to = QDateEdit(state.date_to or QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd/MM/yyyy")
        self.date_to.setEnabled(state.use_date_to)
        self.use_date_to.toggled.connect(self.date_to.setEnabled)

        self.age_min = QSpinBox()
        self.age_min.setRange(0, 999)
        self.age_min.setSpecialValueText("Todas")
        self.age_min.setValue(state.age_min)
        self.age_max = QSpinBox()
        self.age_max.setRange(0, 999)
        self.age_max.setSpecialValueText("Todas")
        self.age_max.setValue(state.age_max)

        self.reading_combo = QComboBox()
        self.reading_combo.addItem("Todas", "")
        for status in reading_statuses:
            self.reading_combo.addItem(status, status)
        reading_index = self.reading_combo.findData(state.reading_status)
        self.reading_combo.setCurrentIndex(max(0, reading_index))

        self.incidents_combo = QComboBox()
        self.incidents_combo.addItem("Todas", "ALL")
        self.incidents_combo.addItem("Solo con incidencias", "WITH")
        self.incidents_combo.addItem("Solo sin incidencias", "WITHOUT")
        incidents_index = self.incidents_combo.findData(state.incidents_mode)
        self.incidents_combo.setCurrentIndex(max(0, incidents_index))

        layout.addWidget(QLabel("Filtrar fechas por:"), 0, 0)
        layout.addWidget(self.date_field, 0, 1)
        layout.addWidget(self.use_date_from, 1, 0)
        layout.addWidget(self.date_from, 1, 1)
        layout.addWidget(self.use_date_to, 2, 0)
        layout.addWidget(self.date_to, 2, 1)
        layout.addWidget(QLabel("Edad mínima:"), 3, 0)
        layout.addWidget(self.age_min, 3, 1)
        layout.addWidget(QLabel("Edad máxima:"), 4, 0)
        layout.addWidget(self.age_max, 4, 1)
        layout.addWidget(QLabel("Lectura:"), 5, 0)
        layout.addWidget(self.reading_combo, 5, 1)
        layout.addWidget(QLabel("Incidencias:"), 6, 0)
        layout.addWidget(self.incidents_combo, 6, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel
        )
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.setText("Aplicar")
        apply_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, 7, 0, 1, 2)

    def state(self) -> AdvancedFiltersState:
        return AdvancedFiltersState(
            date_field=self.date_field.currentData() or "production",
            use_date_from=self.use_date_from.isChecked(),
            date_from=self.date_from.date(),
            use_date_to=self.use_date_to.isChecked(),
            date_to=self.date_to.date(),
            age_min=self.age_min.value(),
            age_max=self.age_max.value(),
            reading_status=self.reading_combo.currentData() or "",
            incidents_mode=self.incidents_combo.currentData() or "ALL",
        )


class HistoricalTab(QWidget):
    DEFAULT_PAGE_SIZE = 25

    def __init__(self, test_type: str) -> None:
        super().__init__()
        self.test_type = test_type
        self._loaded = False
        self._page_index = 0
        self._total = 0
        self._cards: list[ProductionCard] = []
        self._advanced_state = AdvancedFiltersState()
        self._reading_statuses: list[str] = []

        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.addWidget(self._build_filters())

        root.addWidget(self._production_header())

        self.scroll = QScrollArea()
        self.scroll.setObjectName("HistoricalResultsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("HistoricalResultsContent")
        self.scroll_content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self.cards_layout = QVBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(1, 1, 1, 1)
        self.cards_layout.setSpacing(5)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        root.addWidget(self.scroll, 1)

        root.addLayout(self._pagination_controls())
        self._load_reading_statuses()

    def _production_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Card")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        grid = QGridLayout(frame)
        grid.setContentsMargins(6, 4, 6, 4)
        headers = [
            "",
            "Código de producción",
            "Producto",
            "Fecha fabricación",
            "Ensayos",
            "Archivo",
            "Lectura",
        ]
        font = QFont()
        font.setBold(True)
        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setFont(font)
            grid.addWidget(label, 0, column)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 2)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(4, 1)
        grid.setColumnStretch(5, 2)
        grid.setColumnStretch(6, 1)
        return frame

    def _build_filters(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.product_edit = QLineEdit()
        self.product_edit.setPlaceholderText("Ej.: M12L-DIV")
        self.material_edit = QLineEdit()
        self.material_edit.setPlaceholderText("Ej.: Muro Cell, adoquín...")
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Parte del nombre del archivo")

        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Resumen", "SUMMARY")
        self.profile_combo.addItem("Masas y densidad", "MASSES")
        self.profile_combo.addItem("Resultado del ensayo", "TEST")
        self.profile_combo.addItem("Trazabilidad", "TRACE")
        self.profile_combo.addItem("Todas las columnas", "ALL")
        self.profile_combo.currentIndexChanged.connect(
            lambda _index: self.refresh(reset_page=False) if self._loaded else None
        )

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Fecha: más reciente", ("date", True))
        self.sort_combo.addItem("Fecha: más antigua", ("date", False))
        self.sort_combo.addItem("Producto: A–Z", ("product", False))
        self.sort_combo.addItem("Producto: Z–A", ("product", True))
        self.sort_combo.addItem("Más ensayos", ("tests", True))
        self.sort_combo.addItem("Menos ensayos", ("tests", False))
        self.sort_combo.currentIndexChanged.connect(
            lambda _index: self.refresh(reset_page=True) if self._loaded else None
        )

        apply_button = QPushButton("Aplicar filtros")
        clear_button = QPushButton("Limpiar")
        apply_button.clicked.connect(lambda: self.refresh(reset_page=True))
        clear_button.clicked.connect(self.clear_filters)
        self.product_edit.returnPressed.connect(lambda: self.refresh(reset_page=True))
        self.material_edit.returnPressed.connect(lambda: self.refresh(reset_page=True))
        self.file_edit.returnPressed.connect(lambda: self.refresh(reset_page=True))

        advanced_button = QPushButton("Filtros avanzados")
        advanced_button.clicked.connect(self._edit_advanced_filters)
        for field in (self.product_edit, self.material_edit, self.file_edit):
            field.setMinimumWidth(80)
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout.addWidget(QLabel("Código:"))
        layout.addWidget(self.product_edit, 2)
        layout.addWidget(QLabel("Nombre/material:"))
        layout.addWidget(self.material_edit, 2)
        layout.addWidget(QLabel("Archivo:"))
        layout.addWidget(self.file_edit, 1)
        layout.addWidget(apply_button)
        layout.addWidget(clear_button)
        layout.addWidget(advanced_button)
        return bar

    def _edit_advanced_filters(self) -> None:
        dialog = AdvancedFiltersDialog(
            state=self._advanced_state,
            reading_statuses=self._reading_statuses,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._advanced_state = dialog.state()
            self.refresh(reset_page=True)

    def _pagination_controls(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.previous_button = QPushButton("◀")
        self.previous_button.setToolTip("Página anterior")
        self.next_button = QPushButton("▶")
        self.next_button.setToolTip("Página siguiente")
        self.page_label = QLabel("Página 0/0")
        self.page_size_combo = QComboBox()
        for size in (25, 50, 100):
            self.page_size_combo.addItem(str(size), size)
        self.page_size_combo.setCurrentIndex(0)

        self.result_label = QLabel("Sin consultar")
        self.result_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.profile_combo.setMinimumWidth(110)
        self.profile_combo.setMaximumWidth(155)
        self.sort_combo.setMinimumWidth(120)
        self.sort_combo.setMaximumWidth(165)
        collapse_button = QPushButton("Contraer")
        collapse_button.setToolTip("Contraer producciones abiertas")
        collapse_button.clicked.connect(self._collapse_all)
        refresh_button = QPushButton("Actualizar")
        refresh_button.clicked.connect(lambda: self.refresh(reset_page=False))

        self.previous_button.clicked.connect(self._previous_page)
        self.next_button.clicked.connect(self._next_page)
        self.page_size_combo.currentIndexChanged.connect(self._page_size_changed)

        layout.addWidget(QLabel("Por pág.:"))
        layout.addWidget(self.page_size_combo)
        layout.addWidget(self.result_label, 1)
        layout.addWidget(QLabel("Columnas:"))
        layout.addWidget(self.profile_combo)
        layout.addWidget(QLabel("Orden:"))
        layout.addWidget(self.sort_combo)
        layout.addWidget(collapse_button)
        layout.addWidget(refresh_button)
        layout.addStretch(1)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.page_label)
        layout.addWidget(self.next_button)
        return layout

    def _load_reading_statuses(self) -> None:
        with session_scope() as session:
            self._reading_statuses = list_reading_statuses(session, self.test_type)

    def _filters(self) -> HistoricalFilters:
        age_min = self._advanced_state.age_min or None
        age_max = self._advanced_state.age_max or None
        if age_min is not None and age_max is not None and age_min > age_max:
            age_min, age_max = age_max, age_min
        return HistoricalFilters(
            date_field=self._advanced_state.date_field,
            date_from=qdate_to_date(self._advanced_state.date_from)
            if self._advanced_state.use_date_from and self._advanced_state.date_from
            else None,
            date_to=qdate_to_date(self._advanced_state.date_to)
            if self._advanced_state.use_date_to and self._advanced_state.date_to
            else None,
            product_text=self.product_edit.text(),
            material_text=self.material_edit.text(),
            file_text=self.file_edit.text(),
            age_min=age_min,
            age_max=age_max,
            reading_status=self._advanced_state.reading_status,
            incidents_mode=self._advanced_state.incidents_mode,
        )

    def clear_filters(self) -> None:
        self.product_edit.clear()
        self.material_edit.clear()
        self.file_edit.clear()
        self._advanced_state = AdvancedFiltersState()
        self.sort_combo.setCurrentIndex(0)
        self.refresh(reset_page=True)

    def refresh(self, reset_page: bool = True) -> None:
        if reset_page:
            self._page_index = 0

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            filters = self._filters()
            page_size = int(self.page_size_combo.currentData() or self.DEFAULT_PAGE_SIZE)
            sort_field, descending = self.sort_combo.currentData() or ("date", True)

            with session_scope() as session:
                self._total = count_historical_productions(
                    session,
                    test_type=self.test_type,
                    filters=filters,
                )
                page_count = max(1, ceil(self._total / page_size)) if self._total else 0
                if page_count and self._page_index >= page_count:
                    self._page_index = page_count - 1
                productions = query_historical_production_page(
                    session,
                    test_type=self.test_type,
                    filters=filters,
                    limit=page_size,
                    offset=self._page_index * page_size,
                    sort_field=sort_field,
                    descending=bool(descending),
                )

            self._populate_cards(productions, filters)
            test_count = sum(item.test_count for item in productions)
            self.result_label.setText(f"{self._total} producciones · {test_count} ensayos")
            self._update_pagination()
            self._loaded = True
        except Exception as error:
            QMessageBox.critical(self, "No se pudo consultar", str(error))
        finally:
            QApplication.restoreOverrideCursor()

    def _populate_cards(
        self,
        productions: list[HistoricalProductionSummary],
        filters: HistoricalFilters,
    ) -> None:
        self._cards.clear()
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        profile = self.profile_combo.currentData() or "SUMMARY"
        for production in productions:
            card = ProductionCard(
                production=production,
                test_type=self.test_type,
                filters=filters,
                profile=profile,
            )
            self._cards.append(card)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        if not productions:
            empty_label = QLabel(
                "No se encontraron producciones con los filtros actuales."
            )
            empty_label.setObjectName("HistoricalEmptyState")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, empty_label)
        self.scroll.verticalScrollBar().setValue(0)

    def _collapse_all(self) -> None:
        for card in self._cards:
            card.collapse()

    def _update_pagination(self) -> None:
        page_size = int(self.page_size_combo.currentData() or self.DEFAULT_PAGE_SIZE)
        page_count = ceil(self._total / page_size) if self._total else 0
        current_page = self._page_index + 1 if page_count else 0
        self.page_label.setText(f"Página {current_page}/{page_count}")
        self.previous_button.setEnabled(self._page_index > 0)
        self.next_button.setEnabled(page_count > 0 and self._page_index + 1 < page_count)

    def _previous_page(self) -> None:
        if self._page_index <= 0:
            return
        self._page_index -= 1
        self.refresh(reset_page=False)

    def _next_page(self) -> None:
        page_size = int(self.page_size_combo.currentData() or self.DEFAULT_PAGE_SIZE)
        page_count = ceil(self._total / page_size) if self._total else 0
        if self._page_index + 1 >= page_count:
            return
        self._page_index += 1
        self.refresh(reset_page=False)

    def _page_size_changed(self, _index: int) -> None:
        if self._loaded:
            self.refresh(reset_page=True)


class HistoricalExplorerPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.compression_tab = HistoricalTab("COMPRESSION")
        self.flexure_tab = HistoricalTab("FLEXURE")
        self.tabs.addTab(self.compression_tab, "Compresión")
        self.tabs.addTab(self.flexure_tab, "Flexotracción")
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)

    def _tab_changed(self, _index: int) -> None:
        current = self.tabs.currentWidget()
        if isinstance(current, HistoricalTab) and self.isVisible() and not current._loaded:
            current.refresh()

    def refresh(self) -> None:
        if not self.isVisible():
            return
        current = self.tabs.currentWidget()
        if isinstance(current, HistoricalTab):
            current.refresh(reset_page=False)
