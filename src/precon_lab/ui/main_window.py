from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable, Optional
from .history_page import HistoryPage
from .inspection_plan_page import InspectionPlanPage
from .widget_tuning import configure_table_columns, finalize_table_columns, tune_widget_tree
from PySide6.QtCore import QDate, QEvent, Qt
from PySide6.QtGui import QAction, QCursor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_ICON_PATH, APP_ICON_PNG_PATH, APP_NAME, APP_VERSION, database_path
from ..database import session_scope
from ..importers import ImportValidationError, import_summary_file
from ..models import Product, SampleSet, WorkflowTask
from ..services import (
    ValidationError,
    complete_task,
    create_product,
    create_production,
    dashboard_metrics,
    list_batches,
    list_products,
    list_result_candidates,
    list_results,
    list_tasks_for_date,
    reopen_task,
    reprogram_sample_set,
    save_provisional_result,
    seed_demo_data,
)


RefreshCallback = Callable[[], None]


def qdate_to_date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def date_to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def optional_float(spin: QDoubleSpinBox) -> Optional[float]:
    return None if spin.value() == spin.minimum() else spin.value()


def configure_optional_spin(spin: QDoubleSpinBox, suffix: str = "") -> None:
    spin.setRange(-999999999.0, 999999999.0)
    spin.setDecimals(4)
    spin.setSpecialValueText("Sin dato")
    spin.setValue(spin.minimum())
    if suffix:
        spin.setSuffix(suffix)


def message_error(parent: QWidget, error: Exception) -> None:
    QMessageBox.critical(parent, "No se pudo completar", str(error))


def set_table_item(table: QTableWidget, row: int, column: int, value: object) -> None:
    item = QTableWidgetItem("" if value is None else str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    table.setItem(row, column, item)


class MetricCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("MetricCard")
        self.setMinimumHeight(126)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        self.value_label = QLabel("0")
        self.value_label.setObjectName("MetricValue")
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricTitle")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)


class DashboardPage(QWidget):
    def __init__(self, refresh_all: RefreshCallback) -> None:
        super().__init__()
        self.refresh_all = refresh_all
        layout = QVBoxLayout(self)
        title = QLabel("Resumen operativo")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        self.cards = {
            "pending_today": MetricCard("Actividades pendientes hoy"),
            "overdue": MetricCard("Actividades vencidas"),
            "batches_today": MetricCard("Producciones registradas hoy"),
            "provisional": MetricCard("Resultados provisionales"),
            "historical": MetricCard("Ensayos históricos importados"),
        }
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)

        info = QLabel(
            "El prototipo genera actividades a partir de la producción. Usa Producción para crear "
            "muestras; Itinerario para ejecutar el trabajo diario; Resultados para registrar promedios; "
            "e Importar Excel para cargar históricos."
        )
        info.setWordWrap(True)
        info.setObjectName("InfoBanner")
        layout.addWidget(info)

        buttons = QHBoxLayout()
        refresh_button = QPushButton("Actualizar resumen")
        refresh_button.clicked.connect(self.refresh)
        demo_button = QPushButton("Cargar datos de demostración")
        demo_button.setObjectName("Secondary")
        demo_button.clicked.connect(self.load_demo)
        buttons.addWidget(refresh_button)
        buttons.addWidget(demo_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()

    def refresh(self) -> None:
        with session_scope() as session:
            metrics = dashboard_metrics(session, date.today())
        for key, value in metrics.items():
            self.cards[key].value_label.setText(str(value))

    def load_demo(self) -> None:
        try:
            with session_scope() as session:
                seed_demo_data(session, date.today())
            QMessageBox.information(self, "Datos creados", "Se crearon producciones de demostración para hoy.")
            self.refresh_all()
        except Exception as error:
            message_error(self, error)


class ProductDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nuevo producto")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.code_edit = QLineEdit()
        self.category_combo = QComboBox()
        self.category_combo.addItem("Bloque / compresión", "BLOCK")
        self.category_combo.addItem("Elemento / flexotracción", "FLEXURE")
        layout.addRow("Nombre:", self.name_edit)
        layout.addRow("Código:", self.code_edit)
        layout.addRow("Categoría:", self.category_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        tune_widget_tree(self)


class ProductionPage(QWidget):
    def __init__(self, refresh_all: RefreshCallback) -> None:
        super().__init__()
        self.refresh_all = refresh_all
        layout = QVBoxLayout(self)

        form_group = QGroupBox("Datos de producción y muestreo")
        form = QFormLayout(form_group)
        product_row = QHBoxLayout()
        self.product_combo = QComboBox()
        add_product_button = QPushButton("Nuevo producto")
        add_product_button.setObjectName("Secondary")
        add_product_button.clicked.connect(self.add_product)
        product_row.addWidget(self.product_combo, 1)
        product_row.addWidget(add_product_button)
        form.addRow("Producto:", product_row)

        self.production_date = QDateEdit(QDate.currentDate())
        self.production_date.setCalendarPopup(True)
        self.production_date.setDisplayFormat("dd/MM/yyyy")
        self.lot_edit = QLineEdit()
        self.lot_edit.setPlaceholderText("Ej.: LOTE-2026-071")
        self.ages_edit = QLineEdit("3,7,14,28")
        self.ages_edit.setPlaceholderText("Edades separadas por coma")
        self.specimen_count = QSpinBox()
        self.specimen_count.setRange(0, 100)
        self.specimen_count.setSpecialValueText("Valor predeterminado")
        self.specimen_count.setValue(0)
        self.quantity = QSpinBox()
        self.quantity.setRange(0, 10_000_000)
        self.quantity.setSpecialValueText("Sin dato")
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)

        form.addRow("Fecha de fabricación:", self.production_date)
        form.addRow("Código de lote:", self.lot_edit)
        form.addRow("Edades de ensayo:", self.ages_edit)
        form.addRow("Unidades por edad:", self.specimen_count)
        form.addRow("Cantidad producida:", self.quantity)
        form.addRow("Observaciones:", self.notes_edit)
        register_button = QPushButton("Registrar y generar itinerario")
        register_button.clicked.connect(self.register_production)
        form.addRow(register_button)
        layout.addWidget(form_group)

        recent_button = QPushButton("Ver producciones recientes")
        recent_button.setObjectName("Secondary")
        recent_button.clicked.connect(self.show_recent_productions)
        layout.addWidget(recent_button, 0, Qt.AlignmentFlag.AlignLeft)

    def refresh(self) -> None:
        current_id = self.product_combo.currentData()
        self.product_combo.clear()
        with session_scope() as session:
            products = list_products(session)
        for product in products:
            self.product_combo.addItem(product.display_name, product.id)
        if current_id is not None:
            index = self.product_combo.findData(current_id)
            if index >= 0:
                self.product_combo.setCurrentIndex(index)


    def show_recent_productions(self) -> None:
        RecentProductionsDialog(self).exec()

    def add_product(self) -> None:
        dialog = ProductDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                product = create_product(
                    session,
                    dialog.name_edit.text(),
                    dialog.code_edit.text(),
                    dialog.category_combo.currentData(),
                )
                product_id = product.id
            self.refresh_all()
            index = self.product_combo.findData(product_id)
            if index >= 0:
                self.product_combo.setCurrentIndex(index)
        except Exception as error:
            message_error(self, error)

    def register_production(self) -> None:
        product_id = self.product_combo.currentData()
        if product_id is None:
            QMessageBox.warning(self, "Falta producto", "Crea o selecciona un producto.")
            return
        try:
            with session_scope() as session:
                summary = create_production(
                    session,
                    product_id=int(product_id),
                    production_date=qdate_to_date(self.production_date.date()),
                    lot_code=self.lot_edit.text(),
                    ages=self.ages_edit.text(),
                    quantity_produced=self.quantity.value() or None,
                    notes=self.notes_edit.toPlainText(),
                    specimens_per_age=self.specimen_count.value() or None,
                )
            QMessageBox.information(
                self,
                "Producción registrada",
                f"Se crearon {summary.sample_set_count} conjuntos, "
                f"{summary.specimen_count} especímenes y {summary.task_count} actividades.",
            )
            self.lot_edit.clear()
            self.notes_edit.clear()
            self.refresh_all()
        except Exception as error:
            message_error(self, error)


class RecentProductionsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Producciones recientes")
        self.resize(980, 520)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Fecha", "Producto", "Lote", "Cantidad", "Conjuntos", "Especímenes", "Notas"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        configure_table_columns(
            self.table,
            key="recent_productions_v1",
            compact_columns=(0, 3, 4, 5),
            narrative_columns=(1, 2, 6),
        )
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()
        tune_widget_tree(self)

    def refresh(self) -> None:
        with session_scope() as session:
            batches = list_batches(session, 200)
        self.table.setRowCount(len(batches))
        for row, batch in enumerate(batches):
            values = (
                batch.production_date.strftime("%d/%m/%Y"),
                batch.product.display_name,
                batch.lot_code,
                batch.quantity_produced,
                len(batch.sample_sets),
                sum(item.specimen_count for item in batch.sample_sets),
                batch.notes,
            )
            for column, value in enumerate(values):
                set_table_item(self.table, row, column, value)
        finalize_table_columns(self.table)


class ReprogramDialog(QDialog):
    def __init__(self, current_date: date, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reprogramar conjunto")
        layout = QFormLayout(self)
        self.date_edit = QDateEdit(date_to_qdate(current_date))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        layout.addRow("Nueva fecha de ensayo:", self.date_edit)
        warning = QLabel("Solo se moverán las actividades pendientes. Las completadas conservarán su fecha.")
        warning.setWordWrap(True)
        layout.addRow(warning)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        tune_widget_tree(self)


class ItineraryPage(QWidget):
    def __init__(self, refresh_all: RefreshCallback) -> None:
        super().__init__()
        self.refresh_all = refresh_all
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.include_done = QCheckBox("Mostrar completadas")
        self.include_done.setChecked(True)
        refresh_button = QPushButton("Consultar")
        refresh_button.clicked.connect(self.refresh)
        self.date_edit.dateChanged.connect(lambda _: self.refresh())
        self.include_done.toggled.connect(lambda _: self.refresh())
        controls.addWidget(QLabel("Fecha:"))
        controls.addWidget(self.date_edit)
        controls.addWidget(self.include_done)
        controls.addWidget(refresh_button)
        controls.addStretch()
        layout.addLayout(controls)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Estado", "Producto", "Fabricación", "Edad", "Unidades", "Actividad", "Lote", "Instrucciones"]
        )
        configure_table_columns(
            self.table,
            key="daily_itinerary_v1",
            compact_columns=(0, 2, 3, 4),
            narrative_columns=(1, 5, 6, 7),
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.show_selected_detail)
        layout.addWidget(self.table, 1)

        self.detail_label = QLabel("Selecciona una actividad para ver sus instrucciones.")
        self.detail_label.setObjectName("InfoBanner")
        self.detail_label.setWordWrap(True)
        self.detail_label.setFrameShape(QFrame.Shape.StyledPanel)
        layout.addWidget(self.detail_label)

        buttons = QHBoxLayout()
        done_button = QPushButton("Marcar completada")
        done_button.clicked.connect(self.mark_done)
        reopen_button = QPushButton("Reabrir")
        reopen_button.setObjectName("Secondary")
        reopen_button.clicked.connect(self.mark_pending)
        reprogram_button = QPushButton("Reprogramar conjunto")
        reprogram_button.setObjectName("Secondary")
        reprogram_button.clicked.connect(self.reprogram)
        buttons.addWidget(done_button)
        buttons.addWidget(reopen_button)
        buttons.addWidget(reprogram_button)
        buttons.addStretch()
        layout.addLayout(buttons)

    def selected_metadata(self) -> tuple[int, int, Optional[date]] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        task_id = item.data(Qt.ItemDataRole.UserRole)
        set_id = item.data(Qt.ItemDataRole.UserRole + 1)
        planned = item.data(Qt.ItemDataRole.UserRole + 2)
        return int(task_id), int(set_id), planned

    def refresh(self) -> None:
        selected_date = qdate_to_date(self.date_edit.date())
        with session_scope() as session:
            tasks = list_tasks_for_date(session, selected_date, self.include_done.isChecked())
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            sample_set = task.sample_set
            batch = sample_set.batch
            status = "✓ Completada" if task.status == "DONE" else "Pendiente"
            age = f"{sample_set.target_age_days} días" if sample_set.target_age_days else "Absorción"
            values = [
                status,
                batch.product.display_name,
                batch.production_date.strftime("%d/%m/%Y"),
                age,
                sample_set.specimen_count,
                task.title,
                batch.lot_code,
                task.instructions,
            ]
            for column, value in enumerate(values):
                set_table_item(self.table, row, column, value)
            first = self.table.item(row, 0)
            first.setData(Qt.ItemDataRole.UserRole, task.id)
            first.setData(Qt.ItemDataRole.UserRole + 1, sample_set.id)
            first.setData(Qt.ItemDataRole.UserRole + 2, sample_set.planned_test_date)
        self.detail_label.setText(
            f"{len(tasks)} actividad(es) programada(s) para {selected_date.strftime('%d/%m/%Y')}."
        )
        finalize_table_columns(self.table)

    def show_selected_detail(self) -> None:
        row = self.table.currentRow()
        if row >= 0 and self.table.item(row, 7):
            self.detail_label.setText(self.table.item(row, 7).text())

    def mark_done(self) -> None:
        metadata = self.selected_metadata()
        if metadata is None:
            QMessageBox.warning(self, "Sin selección", "Selecciona una actividad.")
            return
        try:
            with session_scope() as session:
                complete_task(session, metadata[0])
            self.refresh_all()
        except Exception as error:
            message_error(self, error)

    def mark_pending(self) -> None:
        metadata = self.selected_metadata()
        if metadata is None:
            QMessageBox.warning(self, "Sin selección", "Selecciona una actividad.")
            return
        try:
            with session_scope() as session:
                reopen_task(session, metadata[0])
            self.refresh_all()
        except Exception as error:
            message_error(self, error)

    def reprogram(self) -> None:
        metadata = self.selected_metadata()
        if metadata is None:
            QMessageBox.warning(self, "Sin selección", "Selecciona una actividad.")
            return
        _, sample_set_id, planned_date = metadata
        if planned_date is None:
            QMessageBox.warning(self, "No aplicable", "La absorción exclusiva de bloques no tiene fecha de ensayo.")
            return
        dialog = ReprogramDialog(planned_date, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with session_scope() as session:
                reprogram_sample_set(session, sample_set_id, qdate_to_date(dialog.date_edit.date()))
            self.refresh_all()
        except Exception as error:
            message_error(self, error)


class CalendarPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.selectionChanged.connect(self.refresh)
        layout.addWidget(self.calendar, 1)

        right = QVBoxLayout()
        self.date_label = QLabel()
        self.date_label.setObjectName("pageTitle")
        right.addWidget(self.date_label)
        self.list_widget = QListWidget()
        right.addWidget(self.list_widget, 1)
        layout.addLayout(right, 2)

    def refresh(self) -> None:
        selected = qdate_to_date(self.calendar.selectedDate())
        self.date_label.setText(selected.strftime("Actividades del %d/%m/%Y"))
        with session_scope() as session:
            tasks = list_tasks_for_date(session, selected, include_done=True)
        self.list_widget.clear()
        if not tasks:
            self.list_widget.addItem("No hay actividades programadas.")
            return
        for task in tasks:
            sample_set = task.sample_set
            batch = sample_set.batch
            marker = "✓" if task.status == "DONE" else "○"
            age = f"{sample_set.target_age_days} días" if sample_set.target_age_days else "absorción"
            item = QListWidgetItem(
                f"{marker} {task.title}\n{batch.product.display_name} · {age} · "
                f"{sample_set.specimen_count} unidades · fabricación {batch.production_date:%d/%m/%Y}"
            )
            item.setToolTip(task.instructions)
            self.list_widget.addItem(item)


class ResultsPage(QWidget):
    def __init__(self, refresh_all: RefreshCallback) -> None:
        super().__init__()
        self.refresh_all = refresh_all
        self._sets: dict[int, SampleSet] = {}
        layout = QVBoxLayout(self)

        form_group = QGroupBox("Registrar o actualizar promedio")
        form = QFormLayout(form_group)
        self.set_combo = QComboBox()
        self.set_combo.currentIndexChanged.connect(self.load_existing)
        self.test_date = QDateEdit(QDate.currentDate())
        self.test_date.setCalendarPopup(True)
        self.test_date.setDisplayFormat("dd/MM/yyyy")
        self.absorption = QDoubleSpinBox()
        self.strength = QDoubleSpinBox()
        self.flexural = QDoubleSpinBox()
        self.abrasion = QDoubleSpinBox()
        for spin in (self.absorption, self.strength, self.flexural, self.abrasion):
            configure_optional_spin(spin)
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(80)
        form.addRow("Conjunto:", self.set_combo)
        form.addRow("Fecha de ensayo:", self.test_date)
        form.addRow("Absorción promedio:", self.absorption)
        form.addRow("Resistencia a compresión promedio:", self.strength)
        form.addRow("Módulo de rotura promedio:", self.flexural)
        form.addRow("Abrasión promedio:", self.abrasion)
        form.addRow("Observaciones:", self.notes)
        save_button = QPushButton("Guardar resultado provisional")
        save_button.clicked.connect(self.save)
        form.addRow(save_button)
        layout.addWidget(form_group)

        help_label = QLabel(
            "Después de importar el Excel de la máquina, la aplicación intentará vincular el resultado "
            "por tipo, producto, fecha de fabricación y edad. No sobrescribe diferencias silenciosamente."
        )
        help_label.setWordWrap(True)
        help_label.setObjectName("InfoBanner")
        layout.addWidget(help_label)
        layout.addStretch()

    def refresh(self) -> None:
        current_id = self.set_combo.currentData()
        with session_scope() as session:
            candidates = list_result_candidates(session)
        self._sets = {item.id: item for item in candidates}
        self.set_combo.blockSignals(True)
        self.set_combo.clear()
        for item in candidates:
            batch = item.batch
            status = item.result.status if item.result else "SIN RESULTADO"
            label = (
                f"{batch.product.display_name} | fabricación {batch.production_date:%d/%m/%Y} | "
                f"{item.purpose} "
                f"{str(item.target_age_days) + ' días' if item.target_age_days is not None else 'sin edad'} | {status}"
            )
            self.set_combo.addItem(label, item.id)
        if current_id is not None:
            index = self.set_combo.findData(current_id)
            if index >= 0:
                self.set_combo.setCurrentIndex(index)
        self.set_combo.blockSignals(False)
        self.load_existing()

    def _reset_spins(self) -> None:
        for spin in (self.absorption, self.strength, self.flexural, self.abrasion):
            spin.setValue(spin.minimum())

    def load_existing(self) -> None:
        self._reset_spins()
        self.notes.clear()
        sample_set = self._sets.get(self.set_combo.currentData())
        if sample_set is None:
            return
        if sample_set.planned_test_date:
            self.test_date.setDate(date_to_qdate(sample_set.planned_test_date))
        result = sample_set.result
        if result is None:
            return
        self.test_date.setDate(date_to_qdate(result.test_date))
        for spin, value in [
            (self.absorption, result.absorption_avg),
            (self.strength, result.strength_avg),
            (self.flexural, result.flexural_avg),
            (self.abrasion, result.abrasion_avg),
        ]:
            if value is not None:
                spin.setValue(value)
        self.notes.setPlainText(result.notes)

    def save(self) -> None:
        sample_set_id = self.set_combo.currentData()
        if sample_set_id is None:
            QMessageBox.warning(self, "Sin conjunto", "Primero registra una producción.")
            return
        try:
            with session_scope() as session:
                result = save_provisional_result(
                    session,
                    sample_set_id=int(sample_set_id),
                    test_date=qdate_to_date(self.test_date.date()),
                    absorption_avg=optional_float(self.absorption),
                    strength_avg=optional_float(self.strength),
                    flexural_avg=optional_float(self.flexural),
                    abrasion_avg=optional_float(self.abrasion),
                    notes=self.notes.toPlainText(),
                )
                status = result.status
            QMessageBox.information(self, "Resultado guardado", f"Estado actual: {status}.")
            self.refresh_all()
        except Exception as error:
            message_error(self, error)


class ImportPage(QWidget):
    def __init__(self, refresh_all: RefreshCallback) -> None:
        super().__init__()
        self.refresh_all = refresh_all
        layout = QVBoxLayout(self)

        group = QGroupBox("Importar resúmenes de máquinas")
        form = QFormLayout(group)
        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        browse_button = QPushButton("Seleccionar archivo")
        browse_button.setObjectName("Secondary")
        browse_button.clicked.connect(self.browse)
        file_row.addWidget(self.path_edit, 1)
        file_row.addWidget(browse_button)
        form.addRow("Archivo:", file_row)
        import_button = QPushButton("Validar e importar")
        import_button.clicked.connect(self.run_import)
        form.addRow(import_button)
        layout.addWidget(group)

        self.result_label = QLabel(
            "Formatos reconocidos: Resumen_Compresion.xlsx y Resumen_Flexotraccion.xlsx. "
            "La base conserva resultados individuales y promedios."
        )
        self.result_label.setWordWrap(True)
        self.result_label.setObjectName("InfoBanner")
        self.result_label.setFrameShape(QFrame.Shape.StyledPanel)
        layout.addWidget(self.result_label)
        layout.addStretch()

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar resumen",
            str(Path.home()),
            "Archivos Excel (*.xlsx *.xlsm)",
        )
        if path:
            self.path_edit.setText(path)

    def run_import(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Falta archivo", "Selecciona un archivo Excel.")
            return
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            with session_scope() as session:
                report = import_summary_file(session, path)
            if report.duplicate_file:
                text = (
                    f"El archivo ya había sido importado. Tipo: {report.test_type}. "
                    f"Filas registradas originalmente: {report.imported_rows}."
                )
            else:
                text = (
                    f"Importación terminada. Tipo: {report.test_type}. Total: {report.total_rows}; "
                    f"nuevas: {report.imported_rows}; duplicadas: {report.duplicate_rows}; "
                    f"conciliadas: {report.reconciled_rows}; conflictos: {report.conflict_rows}."
                )
            self.result_label.setText(text)
            QMessageBox.information(self, "Importación", text)
            self.refresh_all()
        except Exception as error:
            message_error(self, error)
        finally:
            QApplication.restoreOverrideCursor()


class ToolsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        text = QLabel(
            "Esta sección queda reservada para integrar, como módulos independientes, scripts de granulometría, "
            "Proctor, generación de informes, análisis estadístico u otras automatizaciones. Cada módulo podrá abrirse "
            "en una nueva pestaña sin crear otra aplicación ni otra base de datos."
        )
        text.setWordWrap(True)
        text.setObjectName("InfoBanner")
        layout.addWidget(text)
        placeholder = QListWidget()
        placeholder.addItems(
            [
                "Granulometría y comparación de curvas — pendiente",
                "Proctor y control de compactación — pendiente",
                "Generador de informes — pendiente",
                "Análisis estadístico de producción — pendiente",
            ]
        )
        layout.addWidget(placeholder)
        layout.addStretch()


class MainWindow(QMainWindow):
    """Ventana principal con el lenguaje visual y la navegación de Concretos Lab."""

    SIDEBAR_COLLAPSED_WIDTH = 64
    SIDEBAR_EXPANDED_WIDTH = 252

    def __init__(
        self,
        *,
        on_return_to_suite: Callable[[], None] | None = None,
        shared_catalog_page: QWidget | None = None,
        shared_pie_page: QWidget | None = None,
        shared_calendar_page: QWidget | None = None,
    ) -> None:
        super().__init__()
        self._on_return_to_suite = on_return_to_suite
        self.setWindowTitle(f"{APP_NAME} · v{APP_VERSION}")
        self.resize(1440, 900)
        self.setMinimumSize(1024, 700)
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        self.stack = QStackedWidget()
        self.shared_pie_page = shared_pie_page
        self.shared_catalog_page = shared_catalog_page
        self.shared_calendar_page = shared_calendar_page
        if shared_calendar_page is None:
            self.pages = [
                ("Inicio", DashboardPage(self.refresh_all)),
                ("Producción", ProductionPage(self.refresh_all)),
                ("Plan de Inspección y Ensayo", InspectionPlanPage(self.refresh_all)),
                ("Itinerario", ItineraryPage(self.refresh_all)),
                ("Calendario", CalendarPage()),
                ("Resultados", ResultsPage(self.refresh_all)),
                ("Historial", HistoryPage()),
                ("Importar Excel", ImportPage(self.refresh_all)),
                ("Herramientas", ToolsPage()),
            ]
            self.page_hints = [
                "Indicadores y estado operativo del laboratorio",
                "Registro de lotes, productos y muestras",
                "Planificación configurable de controles y ensayos",
                "Ejecución y seguimiento del trabajo diario",
                "Agenda visual de actividades y ensayos",
                "Captura y actualización de resultados provisionales",
                "Consulta consolidada de producción y ensayos",
                "Incorporación segura de resúmenes de máquinas",
                "Módulos complementarios del laboratorio",
            ]
        else:
            # The shared calendar has parity with Itinerary (instructions, checklist,
            # reopen and supported rescheduling), so the redundant navigation is omitted.
            self.pages = [
                ("Inicio", DashboardPage(self.refresh_all)),
                ("Producción", ProductionPage(self.refresh_all)),
                ("Plan de Inspección y Ensayo", shared_pie_page),
                ("Catálogo de Ensayos", shared_catalog_page),
                ("Calendario", shared_calendar_page),
                ("Resultados", ResultsPage(self.refresh_all)),
                ("Historial", HistoryPage()),
                ("Importar Excel", ImportPage(self.refresh_all)),
                ("Herramientas", ToolsPage()),
            ]
            self.page_hints = [
                "Indicadores y estado operativo del laboratorio",
                "Registro de lotes, productos y muestras",
                "Plan compartido de obligaciones de ensayo",
                "Catálogo canónico suministrado por CivilLab",
                "Agenda operativa unificada de las áreas habilitadas",
                "Captura y actualización de resultados provisionales",
                "Consulta consolidada de producción y ensayos",
                "Incorporación segura de resúmenes de máquinas",
                "Módulos complementarios del laboratorio",
            ]
        for _name, page in self.pages:
            page_layout = page.layout()
            if page_layout is not None:
                page_layout.setContentsMargins(24, 20, 24, 20)
                page_layout.setSpacing(12)
            self.stack.addWidget(page)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_page_header())
        content_layout.addWidget(self.stack, 1)
        root.addWidget(content, 1)
        self.setCentralWidget(central)

        tune_widget_tree(self)

        self.stack.currentChanged.connect(self._on_page_changed)
        self._set_sidebar_expanded(False)
        self._on_page_changed(0)
        QApplication.instance().installEventFilter(self)

        self._create_menu()
        self.statusBar().showMessage(f"Base de datos: {database_path()}")
        credit = QLabel("Ing. Samuel Parariá · Derechos reservados")
        credit.setObjectName("CopyrightCredit")
        self.statusBar().addPermanentWidget(credit)
        self.refresh_all()

    def _build_sidebar(self) -> QFrame:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("AppSidebar")
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        logo = QLabel()
        logo.setObjectName("AppLogo")
        logo.setFixedSize(46, 46)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setAccessibleName(f"Icono de {APP_NAME}")
        if APP_ICON_PNG_PATH.exists():
            pixmap = QPixmap(str(APP_ICON_PNG_PATH))
            logo.setPixmap(
                pixmap.scaled(
                    logo.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        self.sidebar_toggle = QToolButton()
        self.sidebar_toggle.setObjectName("SidebarToggle")
        self.sidebar_toggle.setText("☰")
        self.sidebar_toggle.setFixedHeight(42)
        self.sidebar_toggle.setAccessibleName("Mostrar u ocultar navegación")
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)

        self.sidebar_title = QLabel(APP_NAME)
        self.sidebar_title.setObjectName("SidebarBrandTitle")
        self.sidebar_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_title.setWordWrap(True)
        self.sidebar_version = QLabel(f"v{APP_VERSION}")
        self.sidebar_version.setObjectName("SidebarVersion")
        self.sidebar_version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.navigation_container = QWidget()
        navigation_layout = QVBoxLayout(self.navigation_container)
        navigation_layout.setContentsMargins(0, 8, 0, 0)
        navigation_layout.setSpacing(5)
        self.navigation_group = QButtonGroup(self)
        self.navigation_group.setExclusive(True)
        self.navigation_buttons: list[QPushButton] = []
        for index, (name, _page) in enumerate(self.pages):
            button = QPushButton(name)
            button.setObjectName("SidebarNavButton")
            button.setCheckable(True)
            button.setToolTip(self.page_hints[index])
            button.setAccessibleName(self.page_hints[index])
            button.clicked.connect(
                lambda checked=False, page_index=index: self.stack.setCurrentIndex(page_index)
            )
            self.navigation_group.addButton(button, index)
            self.navigation_buttons.append(button)
            navigation_layout.addWidget(button)
        navigation_layout.addStretch()

        layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.sidebar_toggle)
        layout.addWidget(self.sidebar_title)
        layout.addWidget(self.sidebar_version)
        layout.addWidget(self.navigation_container, 1)
        return self.sidebar

    def _build_page_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("PageHeader")
        header.setFixedHeight(68)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(24, 9, 24, 8)
        layout.setSpacing(1)
        self.current_section = QLabel()
        self.current_section.setObjectName("CurrentSection")
        self.current_section_hint = QLabel()
        self.current_section_hint.setObjectName("CurrentSectionHint")
        layout.addWidget(self.current_section)
        layout.addWidget(self.current_section_hint)
        return header

    def _toggle_sidebar(self) -> None:
        self._set_sidebar_expanded(not self.sidebar_expanded)

    def _set_sidebar_expanded(self, expanded: bool) -> None:
        self.sidebar_expanded = expanded
        width = self.SIDEBAR_EXPANDED_WIDTH if expanded else self.SIDEBAR_COLLAPSED_WIDTH
        self.sidebar.setMinimumWidth(width)
        self.sidebar.setMaximumWidth(width)
        self.sidebar_title.setVisible(expanded)
        self.sidebar_version.setVisible(expanded)
        self.navigation_container.setVisible(expanded)
        self.sidebar_toggle.setToolTip(
            "Ocultar navegación" if expanded else "Mostrar navegación"
        )

    def _on_page_changed(self, index: int) -> None:
        if not 0 <= index < len(self.pages):
            return
        self.navigation_buttons[index].setChecked(True)
        self.current_section.setText(self.pages[index][0])
        self.current_section_hint.setText(self.page_hints[index])
        self.refresh_current()

    def eventFilter(self, watched, event) -> bool:
        if (
            getattr(self, "sidebar_expanded", False)
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(watched, QWidget)
            and watched is not self.sidebar
            and not self.sidebar.isAncestorOf(watched)
        ):
            self._set_sidebar_expanded(False)
        return super().eventFilter(watched, event)

    def _create_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")
        if self._on_return_to_suite is not None:
            suite_action = QAction("Volver a CivilLab Suite", self)
            suite_action.setShortcut("Ctrl+Shift+H")
            suite_action.triggered.connect(self._return_to_suite)
            file_menu.addAction(suite_action)
            file_menu.addSeparator()
        refresh_action = QAction("Actualizar", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_all)
        file_menu.addAction(refresh_action)
        file_menu.addSeparator()
        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = self.menuBar().addMenu("Ayuda")
        about_action = QAction("Acerca de", self)
        about_action.triggered.connect(
            lambda: QMessageBox.information(
                self,
                f"Acerca de {APP_NAME}",
                f"{APP_NAME} {APP_VERSION}\n\n"
                "Gestión operativa, producción, muestreo, itinerarios y resultados "
                "del laboratorio de prefabricados de concreto.\n\n"
                "Ing. Samuel Parariá · Derechos reservados.",
            )
        )
        help_menu.addAction(about_action)

    def _return_to_suite(self) -> None:
        if self._on_return_to_suite is None:
            return
        self.hide()
        self._on_return_to_suite()

    def navigate_to_activity(self, target) -> None:
        if target.activity_type == "shared_pie" and self.shared_pie_page is not None:
            self.stack.setCurrentWidget(self.shared_pie_page)
            return
        if target.activity_type != "sample_set":
            return
        results_page = next(
            (page for name, page in self.pages if name == "Resultados"), None
        )
        if results_page is None:
            return
        results_page.refresh()
        index = results_page.set_combo.findData(int(target.source_id))
        if index >= 0:
            results_page.set_combo.setCurrentIndex(index)
        self.stack.setCurrentWidget(results_page)

    def closeEvent(self, event) -> None:
        if self._on_return_to_suite is not None and self.isVisible():
            event.ignore()
            self._return_to_suite()
            return
        super().closeEvent(event)

    def refresh_current(self) -> None:
        page = self.stack.currentWidget()
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    def refresh_all(self) -> None:
        for _, page in self.pages:
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()
