from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.core.catalog import CatalogService
from civillab_suite.core.pie import PieFrequency, PiePlan, PieService


FREQUENCY_LABELS = {
    PieFrequency.DAILY: "Diario",
    PieFrequency.WEEKLY: "Semanal",
    PieFrequency.MONTHLY: "Mensual",
    PieFrequency.CUSTOM_DAYS: "Cada X días",
    PieFrequency.CUSTOM_MONTHS: "Cada X meses",
}


class SharedPiePage(QWidget):
    """Controlled catalog-backed PIE editor shared by all suite modules."""

    def __init__(
        self,
        service: PieService,
        catalog: CatalogService,
        available_modules: dict[str, str],
        context_module_id: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.service = service
        self.catalog = catalog
        self.available_modules = available_modules
        self.context_module_id = context_module_id
        self._editing_id: int | None = None
        self._plans: list[PiePlan] = []

        title = QLabel("Plan de Inspección y Ensayo")
        title.setObjectName("Title")
        info = QLabel(
            "Las nuevas obligaciones usan ensayos canónicos del Core. Las entradas legadas "
            "sin correspondencia segura se conservan y se identifican como tales."
        )
        info.setWordWrap(True)
        info.setObjectName("Subtitle")

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ("Ensayo", "Material", "Periodicidad", "Inicio", "Responsable", "Áreas", "Estado")
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self._edit_selected)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.assay_combo = QComboBox()
        self.material_type_combo = QComboBox()
        self.responsible_edit = QLineEdit()
        self.frequency_combo = QComboBox()
        for frequency, label in FREQUENCY_LABELS.items():
            self.frequency_combo.addItem(label, frequency.value)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 120)
        self.start_date = QDateEdit(QDate.currentDate())
        self.start_date.setCalendarPopup(True)
        self.observations = QTextEdit()
        self.observations.setMaximumHeight(72)
        self.module_checks: dict[str, QCheckBox] = {}
        areas = QWidget()
        areas_layout = QHBoxLayout(areas)
        areas_layout.setContentsMargins(0, 0, 0, 0)
        for module_id, name in available_modules.items():
            check = QCheckBox(name)
            check.setChecked(module_id == context_module_id)
            self.module_checks[module_id] = check
            areas_layout.addWidget(check)
        areas_layout.addStretch()

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.addRow("Ensayo del catálogo:", self.assay_combo)
        form.addRow("Tipo de material:", self.material_type_combo)
        form.addRow("Responsable:", self.responsible_edit)
        form.addRow("Periodicidad:", self.frequency_combo)
        form.addRow("Intervalo:", self.interval_spin)
        form.addRow("Fecha inicial / referencia:", self.start_date)
        form.addRow("Áreas aplicables:", areas)
        form.addRow("Observaciones:", self.observations)

        self.save_button = QPushButton("Crear entrada")
        self.save_button.clicked.connect(self._save)
        edit_button = QPushButton("Modificar seleccionada")
        edit_button.clicked.connect(self._edit_selected)
        deactivate_button = QPushButton("Retirar obligación")
        deactivate_button.clicked.connect(self._deactivate_selected)
        clear_button = QPushButton("Limpiar")
        clear_button.clicked.connect(self._clear_form)
        actions = QHBoxLayout()
        actions.addWidget(self.save_button)
        actions.addWidget(edit_button)
        actions.addWidget(deactivate_button)
        actions.addWidget(clear_button)
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(self.table, 1)
        layout.addWidget(form_widget)
        layout.addLayout(actions)

        self.frequency_combo.currentIndexChanged.connect(self._frequency_changed)
        self._load_catalog()
        self._frequency_changed()
        self.refresh()

    def _load_catalog(self) -> None:
        assays = self.catalog.list_assays(self.context_module_id)
        self.assay_combo.clear()
        for assay in assays:
            self.assay_combo.addItem(assay.name, assay.id)
        self.material_type_combo.clear()
        self.material_type_combo.addItem("No especificado", None)
        for material in self.catalog.list_material_types(self.context_module_id):
            self.material_type_combo.addItem(material.name, material.id)

    def refresh(self) -> None:
        selected = (self.context_module_id,) if self.context_module_id else None
        self._plans = self.service.list_plans(selected, include_inactive=False)
        self.table.setRowCount(len(self._plans))
        for row, plan in enumerate(self._plans):
            values = (
                plan.display_name + (" (legado)" if plan.assay_id is None else ""),
                plan.material_name or "—",
                self.frequency_label(plan),
                plan.start_date.strftime("%d/%m/%Y"),
                plan.responsible or "—",
                ", ".join(plan.module_ids),
                "Activo" if plan.active else "Retirado",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, plan.id)
                self.table.setItem(row, column, item)
        self.table.resizeRowsToContents()

    @staticmethod
    def frequency_label(plan: PiePlan) -> str:
        label = FREQUENCY_LABELS[plan.frequency]
        if plan.frequency in {PieFrequency.CUSTOM_DAYS, PieFrequency.CUSTOM_MONTHS}:
            return f"{label.replace('X', str(plan.interval))}"
        if plan.frequency == PieFrequency.WEEKLY and plan.interval > 1:
            return f"Cada {plan.interval} semanas"
        return label

    def _frequency_changed(self, *_args) -> None:
        frequency = PieFrequency(self.frequency_combo.currentData())
        custom = frequency in {PieFrequency.CUSTOM_DAYS, PieFrequency.CUSTOM_MONTHS}
        self.interval_spin.setEnabled(custom)
        if not custom:
            self.interval_spin.setValue(1)

    def _save(self) -> None:
        try:
            module_ids = tuple(
                module_id for module_id, check in self.module_checks.items() if check.isChecked()
            )
            qdate = self.start_date.date()
            existing = self.service.get_plan(self._editing_id) if self._editing_id else None
            plan = PiePlan(
                id=self._editing_id,
                assay_id=int(self.assay_combo.currentData()),
                method_id=existing.method_id if existing else None,
                material_type_id=self.material_type_combo.currentData(),
                material_object_id=existing.material_object_id if existing else None,
                module_ids=module_ids,
                responsible=self.responsible_edit.text(),
                frequency=PieFrequency(self.frequency_combo.currentData()),
                interval=self.interval_spin.value(),
                start_date=date(qdate.year(), qdate.month(), qdate.day()),
                duration_days=1,
                steps=["Ejecutar ensayo"],
                observations=self.observations.toPlainText(),
                legacy_name=existing.legacy_name if existing else "",
            )
            self.service.save_plan(plan)
        except (TypeError, ValueError) as error:
            QMessageBox.warning(self, "No se pudo guardar el PIE", str(error))
            return
        self._clear_form()
        self.refresh()

    def _selected_plan(self) -> PiePlan | None:
        row = self.table.currentRow()
        return self._plans[row] if 0 <= row < len(self._plans) else None

    def _edit_selected(self, *_args) -> None:
        plan = self._selected_plan()
        if plan is None:
            return
        if plan.assay_id is None:
            QMessageBox.information(
                self, "Entrada legada",
                "Esta entrada se conservó sin inventar una equivalencia. Cree una nueva entrada "
                "desde el catálogo y retire la legada cuando haya validado la correspondencia.",
            )
            return
        assay_index = self.assay_combo.findData(plan.assay_id)
        if assay_index < 0:
            QMessageBox.warning(self, "Ensayo no aplicable", "El ensayo ya no aplica al área actual.")
            return
        self._editing_id = plan.id
        self.assay_combo.setCurrentIndex(assay_index)
        material_index = self.material_type_combo.findData(plan.material_type_id)
        self.material_type_combo.setCurrentIndex(max(0, material_index))
        self.responsible_edit.setText(plan.responsible)
        self.frequency_combo.setCurrentIndex(self.frequency_combo.findData(plan.frequency.value))
        self.interval_spin.setValue(plan.interval)
        self.start_date.setDate(QDate(plan.start_date.year, plan.start_date.month, plan.start_date.day))
        self.observations.setPlainText(plan.observations)
        for module_id, check in self.module_checks.items():
            check.setChecked(module_id in plan.module_ids)
        self.save_button.setText("Guardar cambios")

    def _deactivate_selected(self) -> None:
        plan = self._selected_plan()
        if plan is None or plan.id is None:
            return
        answer = QMessageBox.question(
            self,
            "Retirar obligación PIE",
            "La entrada dejará de generar obligaciones nuevas. El historial se conservará. ¿Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.service.deactivate_plan(plan.id)
        self._clear_form()
        self.refresh()

    def _clear_form(self) -> None:
        self._editing_id = None
        self.responsible_edit.clear()
        self.observations.clear()
        self.save_button.setText("Crear entrada")
