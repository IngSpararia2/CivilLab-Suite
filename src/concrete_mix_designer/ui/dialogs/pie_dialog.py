from __future__ import annotations

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.data.calendar_repository import CalendarRepository
from concrete_mix_designer.domain.pie_models import PieFrequency, PieInspectionPlan

PLAN_ID_ROLE = int(Qt.ItemDataRole.UserRole)


class PiePlanDialog(QDialog):
    plans_changed = Signal()

    def __init__(self, repository: CalendarRepository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self._editing_plan_id: int | None = None
        self._step_inputs: list[QLineEdit] = []

        self.setWindowTitle("Plan de Inspección y Ensayo")
        self.setModal(True)
        self.resize(940, 760)

        title = QLabel("Plan de Inspección y Ensayo")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Programa ensayos periódicos de calidad. El calendario calcula sólo las "
            "incidencias del rango visible y conserva el avance de cada una."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        form_card = QFrame()
        form_card.setObjectName("Card")
        form_layout = QVBoxLayout(form_card)
        self.form_title = QLabel("Nuevo ensayo")
        self.form_title.setObjectName("SectionTitle")
        fields = QFormLayout()
        fields.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej.: Verificación de asentamiento")
        self.frequency_input = QComboBox()
        self.frequency_input.addItem("Diario", PieFrequency.DAILY.value)
        self.frequency_input.addItem("Semanal", PieFrequency.WEEKLY.value)
        self.frequency_input.addItem("Mensual", PieFrequency.MONTHLY.value)
        self.frequency_input.addItem("Cada X días", PieFrequency.CUSTOM_DAYS.value)
        self.frequency_input.addItem("Cada X meses", PieFrequency.CUSTOM_MONTHS.value)
        self.frequency_input.currentIndexChanged.connect(self._frequency_changed)

        self.interval_input = QSpinBox()
        self.interval_input.setRange(1, 1200)
        self.interval_input.setValue(2)
        self.interval_label = QLabel("Repetir cada")
        self.interval_unit = QLabel("días")
        interval_row = QHBoxLayout()
        interval_row.setContentsMargins(0, 0, 0, 0)
        interval_row.addWidget(self.interval_input)
        interval_row.addWidget(self.interval_unit)
        interval_row.addStretch()
        self.interval_widget = QWidget()
        self.interval_widget.setLayout(interval_row)

        self.start_date_input = QDateEdit(QDate.currentDate())
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDisplayFormat("dd/MM/yyyy")
        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 365)
        self.duration_input.setSuffix(" día")
        self.duration_input.setValue(1)
        self.duration_input.valueChanged.connect(self._rebuild_step_inputs)

        fields.addRow("Nombre del ensayo *", self.name_input)
        fields.addRow("Periodicidad *", self.frequency_input)
        fields.addRow(self.interval_label, self.interval_widget)
        fields.addRow("Día de inicio *", self.start_date_input)
        fields.addRow("Duración *", self.duration_input)

        steps_label = QLabel("Pasos por día")
        steps_label.setObjectName("SectionTitle")
        steps_help = QLabel(
            "La duración crea una entrada por cada día del ensayo. Describe la actividad "
            "que debe aparecer en el calendario."
        )
        steps_help.setObjectName("Subtitle")
        steps_help.setWordWrap(True)
        self.steps_container = QWidget()
        self.steps_container.setObjectName("PieStepsContainer")
        self.steps_container.setStyleSheet(
            "QWidget#PieStepsContainer { background: #f8fafc; color: #1f2937; } "
            "QWidget#PieStepsContainer QLabel { background: transparent; color: #1f2937; }"
        )
        self.steps_layout = QFormLayout(self.steps_container)
        self.steps_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        steps_scroll = QScrollArea()
        steps_scroll.setObjectName("PieStepsScroll")
        steps_scroll.setStyleSheet(
            "QScrollArea#PieStepsScroll { background: #f8fafc; "
            "border: 1px solid #dce3ec; border-radius: 5px; }"
        )
        steps_scroll.viewport().setStyleSheet("background: #f8fafc;")
        steps_scroll.setWidgetResizable(True)
        steps_scroll.setFrameShape(QFrame.Shape.NoFrame)
        steps_scroll.setMinimumHeight(120)
        steps_scroll.setMaximumHeight(220)
        steps_scroll.setWidget(self.steps_container)

        save_button = QPushButton("Guardar ensayo")
        save_button.clicked.connect(self._save_plan)
        clear_button = QPushButton("Limpiar formulario")
        clear_button.setObjectName("Secondary")
        clear_button.clicked.connect(self._reset_form)
        form_actions = QHBoxLayout()
        form_actions.addStretch()
        form_actions.addWidget(clear_button)
        form_actions.addWidget(save_button)

        form_layout.addWidget(self.form_title)
        form_layout.addLayout(fields)
        form_layout.addWidget(steps_label)
        form_layout.addWidget(steps_help)
        form_layout.addWidget(steps_scroll)
        form_layout.addLayout(form_actions)

        list_card = QFrame()
        list_card.setObjectName("Card")
        list_layout = QVBoxLayout(list_card)
        list_title = QLabel("Ensayos incluidos en el PIE")
        list_title.setObjectName("SectionTitle")
        self.plan_table = QTableWidget(0, 4)
        self.plan_table.setHorizontalHeaderLabels(
            ["Ensayo", "Periodicidad", "Inicio", "Duración"]
        )
        self.plan_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.plan_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.plan_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.plan_table.setAlternatingRowColors(True)
        self.plan_table.verticalHeader().setVisible(False)
        self.plan_table.doubleClicked.connect(self._edit_selected)
        header = self.plan_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        edit_button = QPushButton("Modificar")
        edit_button.setObjectName("Secondary")
        edit_button.clicked.connect(self._edit_selected)
        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("Danger")
        delete_button.clicked.connect(self._delete_selected)
        close_button = QPushButton("Cerrar")
        close_button.setObjectName("Secondary")
        close_button.clicked.connect(self.accept)
        list_actions = QHBoxLayout()
        list_actions.addWidget(edit_button)
        list_actions.addWidget(delete_button)
        list_actions.addStretch()
        list_actions.addWidget(close_button)

        list_layout.addWidget(list_title)
        list_layout.addWidget(self.plan_table, 1)
        list_layout.addLayout(list_actions)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(form_card)
        layout.addWidget(list_card, 1)

        self._frequency_changed()
        self._rebuild_step_inputs(1)
        self._refresh_plans()

    def _frequency(self) -> PieFrequency:
        return PieFrequency(str(self.frequency_input.currentData()))

    def _frequency_changed(self, *_args) -> None:
        frequency = self._frequency()
        custom = frequency in {PieFrequency.CUSTOM_DAYS, PieFrequency.CUSTOM_MONTHS}
        self.interval_label.setVisible(custom)
        self.interval_widget.setVisible(custom)
        self.interval_unit.setText(
            "días" if frequency == PieFrequency.CUSTOM_DAYS else "meses"
        )

    def _rebuild_step_inputs(self, duration: int) -> None:
        previous = [field.text() for field in self._step_inputs]
        while self.steps_layout.rowCount():
            self.steps_layout.removeRow(0)
        self._step_inputs.clear()
        for index in range(duration):
            field = QLineEdit()
            field.setPlaceholderText(f"Actividad o procedimiento del día {index + 1}")
            if index < len(previous):
                field.setText(previous[index])
            self.steps_layout.addRow(f"Día {index + 1} *", field)
            self._step_inputs.append(field)
        self.duration_input.setSuffix(" día" if duration == 1 else " días")

    @staticmethod
    def _to_date(value: QDate):
        from datetime import date

        return date(value.year(), value.month(), value.day())

    @staticmethod
    def _to_qdate(value) -> QDate:
        return QDate(value.year, value.month, value.day)

    def _save_plan(self) -> None:
        frequency = self._frequency()
        interval = (
            self.interval_input.value()
            if frequency in {PieFrequency.CUSTOM_DAYS, PieFrequency.CUSTOM_MONTHS}
            else 1
        )
        plan = PieInspectionPlan(
            id=self._editing_plan_id,
            name=self.name_input.text(),
            frequency=frequency,
            interval=interval,
            start_date=self._to_date(self.start_date_input.date()),
            duration_days=self.duration_input.value(),
            steps=[field.text() for field in self._step_inputs],
        )
        try:
            self.repository.save_pie_plan(plan)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo guardar el ensayo PIE", str(error))
            return
        action = "actualizado" if self._editing_plan_id is not None else "añadido"
        self._reset_form()
        self._refresh_plans()
        self.plans_changed.emit()
        QMessageBox.information(
            self, "Plan de Inspección y Ensayo", f"El ensayo fue {action} correctamente."
        )

    def _selected_plan_id(self) -> int | None:
        row = self.plan_table.currentRow()
        item = self.plan_table.item(row, 0) if row >= 0 else None
        value = item.data(PLAN_ID_ROLE) if item else None
        return int(value) if value is not None else None

    def _edit_selected(self, *_args) -> None:
        plan_id = self._selected_plan_id()
        if plan_id is None:
            QMessageBox.information(
                self, "Selecciona un ensayo", "Selecciona el ensayo PIE que deseas modificar."
            )
            return
        plan = self.repository.get_pie_plan(plan_id)
        if plan is None:
            self._refresh_plans()
            QMessageBox.warning(self, "Ensayo no disponible", "El ensayo PIE ya no existe.")
            return
        self._editing_plan_id = plan.id
        self.form_title.setText(f"Modificar ensayo: {plan.name}")
        self.name_input.setText(plan.name)
        index = self.frequency_input.findData(plan.frequency.value)
        self.frequency_input.setCurrentIndex(index)
        self.interval_input.setValue(plan.interval)
        self.start_date_input.setDate(self._to_qdate(plan.start_date))
        self.duration_input.setValue(plan.duration_days)
        self._rebuild_step_inputs(plan.duration_days)
        for field, step in zip(self._step_inputs, plan.steps, strict=True):
            field.setText(step)
        self.name_input.setFocus()

    def _delete_selected(self) -> None:
        plan_id = self._selected_plan_id()
        if plan_id is None:
            QMessageBox.information(
                self, "Selecciona un ensayo", "Selecciona el ensayo PIE que deseas eliminar."
            )
            return
        plan = self.repository.get_pie_plan(plan_id)
        if plan is None:
            self._refresh_plans()
            return
        answer = QMessageBox.question(
            self,
            "Eliminar ensayo PIE",
            f"¿Deseas eliminar '{plan.name}' y su historial de ejecución?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.repository.delete_pie_plan(plan_id)
        if self._editing_plan_id == plan_id:
            self._reset_form()
        self._refresh_plans()
        self.plans_changed.emit()

    def _reset_form(self) -> None:
        self._editing_plan_id = None
        self.form_title.setText("Nuevo ensayo")
        self.name_input.clear()
        self.frequency_input.setCurrentIndex(0)
        self.interval_input.setValue(2)
        self.start_date_input.setDate(QDate.currentDate())
        self.duration_input.setValue(1)
        self._rebuild_step_inputs(1)
        self.name_input.setFocus()

    def _refresh_plans(self) -> None:
        plans = self.repository.list_pie_plans()
        self.plan_table.setRowCount(len(plans))
        for row, plan in enumerate(plans):
            values = (
                plan.name,
                self.repository.pie_frequency_label(plan.frequency, plan.interval),
                plan.start_date.strftime("%d/%m/%Y"),
                f"{plan.duration_days} día" + ("s" if plan.duration_days != 1 else ""),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(PLAN_ID_ROLE, plan.id)
                self.plan_table.setItem(row, column, item)
        self.plan_table.resizeRowsToContents()
