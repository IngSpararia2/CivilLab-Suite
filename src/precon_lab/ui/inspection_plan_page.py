from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QPoint, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.ui.shared_controls import ensure_table_row_height

from ..config import ASSETS_DIR
from ..database import session_scope
from ..services import (
    ValidationError,
    create_inspection_plan_entry,
    format_periodicity,
    get_test_requirements,
    list_applicable_tests,
    list_inspection_catalog,
    list_inspection_plan_entries,
    list_material_types,
)
from .widget_tuning import configure_table_columns, finalize_table_columns, tune_widget_tree


def _set_item(table: QTableWidget, row: int, column: int, value: object) -> None:
    item = QTableWidgetItem("" if value is None else str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    table.setItem(row, column, item)


def _requirement_text(requirement) -> str:
    numeric = ""
    if requirement.minimum is not None and requirement.maximum is not None:
        numeric = f"{requirement.minimum:g}–{requirement.maximum:g}"
    elif requirement.minimum is not None:
        numeric = f"{requirement.operator or '≥'} {requirement.minimum:g}"
    elif requirement.maximum is not None:
        numeric = f"{requirement.operator or '≤'} {requirement.maximum:g}"
    if numeric and requirement.unit:
        numeric = f"{numeric} {requirement.unit}"
    return numeric or requirement.requirement_text or "Sin valor numérico registrado"


class ProcedurePopup(QWidget):
    """Consulta breve, seleccionable y autocerrable del procedimiento almacenado."""

    def __init__(self, applicability, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("ProcedurePopup")
        self.setWindowTitle("Procedimiento")
        self.resize(560, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel(applicability.laboratory_test.name)
        title.setObjectName("ProcedureTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        metadata = QLabel(
            "\n".join((
                f"Material / producto: {applicability.material_type.name}",
                f"Especificación: {applicability.standard.code if applicability.standard else '—'}",
                f"Método: {applicability.laboratory_test.standard.code if applicability.laboratory_test.standard else '—'}",
            ))
        )
        metadata.setObjectName("ProcedureMetadata")
        metadata.setWordWrap(True)
        layout.addWidget(metadata)

        scroll = QScrollArea()
        scroll.setObjectName("ProcedureScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail = QLabel(applicability.procedure_detail or "Procedimiento pendiente de registrar.")
        detail.setObjectName("ProcedureDetail")
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        detail.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        detail.setTextFormat(Qt.TextFormat.PlainText)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.setContentsMargins(10, 8, 10, 8)
        scroll.setWidget(detail)
        layout.addWidget(scroll, 1)


class CatalogDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Catálogo de ensayos")
        self.resize(1280, 720)
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Material / producto:"))
        self.material_combo = QComboBox()
        self.material_combo.addItem("Todos los materiales")
        controls.addWidget(self.material_combo)
        controls.addWidget(QLabel("Buscar:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Ensayo, código o norma")
        controls.addWidget(self.search_edit, 1)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels((
            "Material / producto", "Ensayo", "Especificación", "Método", "Frecuencia",
            "Clase / gradación / condición", "Requisito", "Unidad", "Procedimiento",
        ))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setDefaultSectionSize(42)
        configure_table_columns(
            self.table,
            key="inspection_catalog_v2",
            compact_columns=(2, 3, 7, 8),
            narrative_columns=(0, 1, 4, 5, 6),
            initial_widths={8: 44},
        )
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        with session_scope() as session:
            self._rows = list_inspection_catalog(session)
        for name in sorted({app.material_type.name for app, _ in self._rows}):
            self.material_combo.addItem(name)
        self.material_combo.currentTextChanged.connect(self._refresh_table)
        self.search_edit.textChanged.connect(self._refresh_table)
        self._refresh_table()
        tune_widget_tree(self)

    def _refresh_table(self) -> None:
        selected_material = self.material_combo.currentText()
        needle = self.search_edit.text().casefold().strip()
        visible_rows = []
        for applicability, requirement in self._rows:
            standard = applicability.standard.code if applicability.standard else ""
            method = applicability.laboratory_test.standard.code if applicability.laboratory_test.standard else ""
            condition = " · ".join(value for value in (
                requirement.grading if requirement else "",
                requirement.condition if requirement else "",
                requirement.aggregation if requirement else "",
            ) if value)
            source = " · ".join(value for value in (
                requirement.standard.code if requirement and requirement.standard else "",
                requirement.source_detail if requirement else "",
            ) if value)
            values = (
                applicability.material_type.name,
                applicability.laboratory_test.name,
                standard,
                method,
                applicability.normative_frequency,
                condition,
                _requirement_text(requirement) if requirement else "Sin requisito numérico registrado",
                requirement.unit if requirement else "",
            )
            searchable = " ".join((*values, source, requirement.verification_status if requirement else "")).casefold()
            if (
                selected_material != "Todos los materiales"
                and values[0] != selected_material
            ) or (needle and needle not in searchable):
                continue
            visible_rows.append((applicability, values))
        self.table.setRowCount(len(visible_rows))
        for row, (applicability, values) in enumerate(visible_rows):
            for column, value in enumerate(values):
                _set_item(self.table, row, column, value)
            action = QToolButton()
            action.setObjectName("TableAction")
            action.setIcon(QIcon(str(ASSETS_DIR / "eye.svg")))
            action.setIconSize(QSize(16, 16))
            action.setToolTip("Ver procedimiento")
            action.setAccessibleName("Ver procedimiento")
            action.setFixedSize(30, 26)
            action.clicked.connect(
                lambda checked=False, item=applicability, button=action: self._show_procedure(item, button)
            )
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.addWidget(action, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 8, cell)
            ensure_table_row_height(self.table, row, minimum=34)
        finalize_table_columns(self.table)

    def _show_procedure(self, applicability, button: QToolButton) -> None:
        if getattr(self, "_procedure_popup", None) is not None:
            self._procedure_popup.close()
        popup = ProcedurePopup(applicability, self)
        self._procedure_popup = popup
        popup.destroyed.connect(lambda *_: setattr(self, "_procedure_popup", None))
        self._place_procedure_popup(popup, button)
        popup.show()

    @staticmethod
    def _place_procedure_popup(popup: ProcedurePopup, button: QToolButton) -> None:
        """Ubica el visor junto al botón sin dejarlo fuera del área visible."""

        global_button = button.mapToGlobal(QPoint(0, 0))
        screen = button.screen() or QGuiApplication.screenAt(
            button.mapToGlobal(button.rect().center())
        ) or QGuiApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        margin = 14
        popup_width = min(popup.width(), available.width() - (margin * 2))
        popup_height = min(popup.height(), available.height() - (margin * 2))
        popup.resize(max(1, popup_width), max(1, popup_height))

        right_x = global_button.x() + button.width() + 8
        left_x = global_button.x() - popup.width() - 8
        if right_x + popup.width() <= available.right() + 1:
            x = right_x
        elif left_x >= available.left():
            x = left_x
        else:
            x = available.left() + (available.width() - popup.width()) // 2

        y = global_button.y()
        if y + popup.height() > available.bottom() - margin:
            y = available.bottom() - margin - popup.height()
        y = max(available.top() + margin, y)
        x = max(available.left() + margin, min(x, available.right() - margin - popup.width()))
        popup.move(x, y)


class RequirementsDialog(QDialog):
    def __init__(self, material_id: int, test_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rangos y requisitos")
        self.resize(920, 420)
        layout = QVBoxLayout(self)
        info = QLabel("Los estados de verificación se conservan para diferenciar fuentes confirmadas y referencias secundarias.")
        info.setObjectName("InfoBanner")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Material", "Condición", "Requisito", "Unidad", "Fuente / norma", "Verificación"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        configure_table_columns(
            self.table,
            key="inspection_requirements_v1",
            compact_columns=(3, 5),
            narrative_columns=(0, 1, 2, 4),
        )
        layout.addWidget(self.table, 1)
        with session_scope() as session:
            requirements = get_test_requirements(session, material_id, test_id)
        self.table.setRowCount(len(requirements))
        for row, requirement in enumerate(requirements):
            condition = " · ".join(
                value for value in (requirement.condition, requirement.aggregation, f"{requirement.age_days} días" if requirement.age_days else "") if value
            )
            standard = requirement.standard.code if requirement.standard else ""
            source = " · ".join(value for value in (standard, requirement.source_detail) if value)
            values = (
                requirement.material_type.name,
                condition,
                _requirement_text(requirement),
                requirement.unit,
                source,
                requirement.verification_status,
            )
            for column, value in enumerate(values):
                _set_item(self.table, row, column, value)
        finalize_table_columns(self.table)
        if not requirements:
            layout.addWidget(QLabel("No hay rangos numéricos confirmados para esta combinación."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        tune_widget_tree(self)


class InspectionPlanPage(QWidget):
    def __init__(self, refresh_all) -> None:
        super().__init__()
        self.refresh_all = refresh_all
        self._applicabilities: dict[int, object] = {}
        layout = QVBoxLayout(self)

        plan_group = QGroupBox("Ensayos periódicos")
        plan_layout = QVBoxLayout(plan_group)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Norma", "Ensayo", "Periodicidad", "Materiales", "Responsable", "Rangos"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(240)
        configure_table_columns(
            self.table,
            key="inspection_plan_v1",
            compact_columns=(0, 2, 4, 5),
            narrative_columns=(1, 3),
            initial_widths={5: 108},
        )
        plan_layout.addWidget(self.table)
        form_group = QGroupBox("Registrar ensayo en el plan")
        form = QFormLayout(form_group)
        self.material_combo = QComboBox()
        self.test_combo = QComboBox()
        self.standard_label = QLabel("—")
        self.equipment_label = QLabel("—")
        self.procedure_label = QLabel("—")
        self.frequency_label = QLabel("—")
        for label in (self.standard_label, self.equipment_label, self.procedure_label, self.frequency_label):
            label.setWordWrap(True)
            label.setObjectName("Subtitle")
        self.responsible_combo = QComboBox()
        self.responsible_combo.addItems(("Laboratorista", "Jefe de Area", "Ayudante"))
        self.frequency_combo = QComboBox()
        self.frequency_combo.addItem("Diario", "DAILY")
        self.frequency_combo.addItem("Semanal", "WEEKLY")
        self.frequency_combo.addItem("Mensual", "MONTHLY")
        self.frequency_combo.addItem("Cada X meses", "EVERY_X_MONTHS")
        self.weekday_combo = QComboBox()
        for index, name in enumerate(("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")):
            self.weekday_combo.addItem(name, index)
        self.ordinal_combo = QComboBox()
        for ordinal, name in enumerate(("Primer", "Segundo", "Tercer", "Cuarto", "Quinto"), start=1):
            self.ordinal_combo.addItem(name, ordinal)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(2, 36)
        self.interval_spin.setValue(3)
        self.reference_date = QDateEdit(QDate.currentDate())
        self.reference_date.setCalendarPopup(True)
        self.observations_edit = QLineEdit()
        self.observations_edit.setPlaceholderText("Observaciones opcionales")
        self.schedule_widget = QWidget()
        schedule = QGridLayout(self.schedule_widget)
        schedule.setContentsMargins(0, 0, 0, 0)
        schedule.setHorizontalSpacing(8)
        schedule.setVerticalSpacing(6)
        schedule.addWidget(QLabel("Semana:"), 0, 0)
        schedule.addWidget(self.ordinal_combo, 0, 1)
        schedule.addWidget(QLabel("Día:"), 1, 0)
        schedule.addWidget(self.weekday_combo, 1, 1)
        schedule.addWidget(QLabel("Intervalo:"), 2, 0)
        schedule.addWidget(self.interval_spin, 2, 1)
        schedule.addWidget(QLabel("Referencia:"), 3, 0)
        schedule.addWidget(self.reference_date, 3, 1)
        schedule.setColumnStretch(1, 1)
        add_button = QPushButton("Añadir al plan")
        add_button.clicked.connect(self._add_entry)
        form.addRow("Material / producto:", self.material_combo)
        form.addRow("Ensayo:", self.test_combo)
        form.addRow("Norma:", self.standard_label)
        form.addRow("Equipo:", self.equipment_label)
        form.addRow("Procedimiento:", self.procedure_label)
        form.addRow("Frecuencia normativa:", self.frequency_label)
        form.addRow("Responsable:", self.responsible_combo)
        form.addRow("Periodicidad:", self.frequency_combo)
        form.addRow("", self.schedule_widget)
        form.addRow("Observaciones:", self.observations_edit)
        form.addRow("", add_button)
        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(plan_group, 3)
        columns.addWidget(form_group, 2)
        layout.addLayout(columns, 1)

        self.material_combo.currentIndexChanged.connect(self._load_applicable_tests)
        self.test_combo.currentIndexChanged.connect(self._show_test_info)
        self.frequency_combo.currentIndexChanged.connect(self._update_schedule_visibility)
        self._load_materials()
        self._update_schedule_visibility()

    def _load_materials(self) -> None:
        with session_scope() as session:
            materials = list_material_types(session)
        self.material_combo.blockSignals(True)
        self.material_combo.clear()
        for material in materials:
            self.material_combo.addItem(material.name, material.id)
        self.material_combo.blockSignals(False)
        self._load_applicable_tests()

    def _load_applicable_tests(self) -> None:
        material_id = self.material_combo.currentData()
        self.test_combo.clear()
        self._applicabilities = {}
        if material_id is None:
            self._show_test_info()
            return
        with session_scope() as session:
            applicabilities = list_applicable_tests(session, int(material_id))
        for applicability in applicabilities:
            test = applicability.laboratory_test
            self.test_combo.addItem(test.name, test.id)
            self._applicabilities[test.id] = applicability
        self._show_test_info()

    def _show_test_info(self) -> None:
        applicability = self._applicabilities.get(self.test_combo.currentData())
        if applicability is None:
            for label in (self.standard_label, self.equipment_label, self.procedure_label, self.frequency_label):
                label.setText("—")
            return
        test = applicability.laboratory_test
        self.standard_label.setText(applicability.standard.code if applicability.standard else "Pendiente de definir")
        self.equipment_label.setText(test.equipment or "Pendiente")
        self.procedure_label.setText(test.procedure_summary or "Pendiente")
        self.frequency_label.setText(applicability.normative_frequency or "No indicada")

    def _update_schedule_visibility(self) -> None:
        frequency = self.frequency_combo.currentData()
        self.ordinal_combo.setVisible(frequency in {"MONTHLY", "EVERY_X_MONTHS"})
        self.interval_spin.setVisible(frequency == "EVERY_X_MONTHS")
        self.reference_date.setVisible(frequency == "EVERY_X_MONTHS")
        for index in range(self.schedule_widget.layout().count()):
            item = self.schedule_widget.layout().itemAt(index)
            widget = item.widget() if item else None
            if isinstance(widget, QLabel):
                text = widget.text()
                if text == "Semana:":
                    widget.setVisible(frequency in {"MONTHLY", "EVERY_X_MONTHS"})
                elif text in {"Intervalo:", "Referencia:"}:
                    widget.setVisible(frequency == "EVERY_X_MONTHS")
                elif text == "Día:":
                    widget.setVisible(frequency in {"WEEKLY", "MONTHLY", "EVERY_X_MONTHS"})
        self.weekday_combo.setVisible(frequency in {"WEEKLY", "MONTHLY", "EVERY_X_MONTHS"})
        self.schedule_widget.setVisible(frequency != "DAILY")

    def _add_entry(self) -> None:
        try:
            frequency = self.frequency_combo.currentData()
            weekday = self.weekday_combo.currentData() if frequency != "DAILY" else None
            ordinal = self.ordinal_combo.currentData() if frequency in {"MONTHLY", "EVERY_X_MONTHS"} else None
            interval = self.interval_spin.value() if frequency == "EVERY_X_MONTHS" else None
            reference = None
            if frequency == "EVERY_X_MONTHS":
                qdate = self.reference_date.date()
                reference = date(qdate.year(), qdate.month(), qdate.day())
            with session_scope() as session:
                create_inspection_plan_entry(
                    session,
                    material_type_id=int(self.material_combo.currentData()),
                    laboratory_test_id=int(self.test_combo.currentData()),
                    responsible=self.responsible_combo.currentText(),
                    frequency_type=frequency,
                    weekday=weekday,
                    week_ordinal=ordinal,
                    month_interval=interval,
                    reference_date=reference,
                    observations=self.observations_edit.text(),
                )
            self.observations_edit.clear()
            self.refresh()
            self.refresh_all()
        except (ValidationError, TypeError) as error:
            QMessageBox.warning(self, "No se pudo añadir al plan", str(error))

    def _show_requirements(self, material_id: int, test_id: int) -> None:
        RequirementsDialog(material_id, test_id, self).exec()

    def refresh(self) -> None:
        with session_scope() as session:
            entries = list_inspection_plan_entries(session)
            rows = []
            for entry in entries:
                applicability = next(
                    (item for item in list_applicable_tests(session, entry.material_type_id)
                     if item.laboratory_test_id == entry.laboratory_test_id),
                    None,
                )
                standard = applicability.standard.code if applicability and applicability.standard else "—"
                rows.append((entry, standard))
        self.table.setRowCount(len(rows))
        for row, (entry, standard) in enumerate(rows):
            periodicity = format_periodicity(
                entry.frequency_type,
                weekday=entry.weekday,
                week_ordinal=entry.week_ordinal,
                month_interval=entry.month_interval,
            )
            values = (
                standard,
                entry.laboratory_test.name,
                periodicity,
                entry.material_type.name,
                entry.responsible,
            )
            for column, value in enumerate(values):
                _set_item(self.table, row, column, value)
            button = QPushButton("Ver rangos")
            button.setObjectName("TableAction")
            button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
            button.clicked.connect(
                lambda checked=False, material_id=entry.material_type_id, test_id=entry.laboratory_test_id:
                self._show_requirements(material_id, test_id)
            )
            self.table.setCellWidget(row, 5, button)
            ensure_table_row_height(self.table, row, minimum=34)
        finalize_table_columns(self.table)
