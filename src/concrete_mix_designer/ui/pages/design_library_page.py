from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.domain.laboratory_models import SPECIMEN_TYPE_LABELS
from concrete_mix_designer.domain.metadata_models import (
    APPLICATION_LABELS,
    CONSISTENCY_LABELS,
    ConcreteApplication,
    ConsistencyType,
    StrengthBasis,
)
from concrete_mix_designer.services.app_state import AppState


class DesignLibraryPage(QWidget):
    open_laboratory_requested = Signal()

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._records = []
        self._specifications = {}

        title = QLabel("Biblioteca de diseños")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Busca diseños por nombre, grupo y propiedades técnicas. La producción se registra "
            "desde Dosificación usando exclusivamente un diseño guardado."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        create_group_button = QPushButton("Crear grupo")
        create_group_button.setObjectName("Secondary")
        create_group_button.clicked.connect(self._create_group)
        load_button = QPushButton("Cargar seleccionado en Laboratorio")
        load_button.setObjectName("Secondary")
        load_button.clicked.connect(self._load_selected)
        archive_button = QPushButton("Archivar seleccionado")
        archive_button.setObjectName("Danger")
        archive_button.clicked.connect(self._archive_selected)
        actions = QHBoxLayout()
        actions.addWidget(create_group_button)
        actions.addWidget(load_button)
        actions.addStretch()
        actions.addWidget(archive_button)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar por nombre, grupo, descripción o etiquetas…")
        self.search_edit.textChanged.connect(lambda _text: self._apply_filters())
        self.group_filter = QComboBox()
        self.group_filter.currentIndexChanged.connect(lambda _index: self._apply_filters())

        self.structural_check = QCheckBox("Estructural")
        self.pavement_check = QCheckBox("Pavimento")
        self.precast_check = QCheckBox("Prefabricado")
        self.other_check = QCheckBox("Otros")
        self.slump_check = QCheckBox("Asentamiento")
        self.spread_check = QCheckBox("Esparcimiento")
        for check in (
            self.structural_check,
            self.pavement_check,
            self.precast_check,
            self.other_check,
            self.slump_check,
            self.spread_check,
        ):
            check.toggled.connect(lambda _checked: self._apply_filters())

        self.min_strength = QDoubleSpinBox()
        self.max_strength = QDoubleSpinBox()
        for spin in (self.min_strength, self.max_strength):
            spin.setRange(0.0, 200.0)
            spin.setDecimals(1)
            spin.setSuffix(" MPa")
        self.max_strength.setValue(200.0)
        for spin in (self.min_strength, self.max_strength):
            spin.valueChanged.connect(lambda _value: self._apply_filters())

        self.min_consistency = QDoubleSpinBox()
        self.max_consistency = QDoubleSpinBox()
        for spin in (self.min_consistency, self.max_consistency):
            spin.setRange(0.0, 1500.0)
            spin.setDecimals(0)
            spin.setSuffix(" mm")
        self.max_consistency.setValue(1500.0)
        for spin in (self.min_consistency, self.max_consistency):
            spin.valueChanged.connect(lambda _value: self._apply_filters())
        self.accelerated_only = QCheckBox("Solo acelerados")
        self.accelerated_only.toggled.connect(lambda _checked: self._apply_filters())
        clear_filters = QPushButton("Limpiar filtros")
        clear_filters.setObjectName("Secondary")
        clear_filters.clicked.connect(self._clear_filters)

        filters = QFrame()
        filters.setObjectName("Card")
        grid = QGridLayout(filters)
        grid.addWidget(QLabel("Buscar:"), 0, 0)
        grid.addWidget(self.search_edit, 0, 1, 1, 4)
        grid.addWidget(QLabel("Grupo:"), 0, 5)
        grid.addWidget(self.group_filter, 0, 6)
        grid.addWidget(QLabel("Tipo:"), 1, 0)
        grid.addWidget(self.structural_check, 1, 1)
        grid.addWidget(self.pavement_check, 1, 2)
        grid.addWidget(self.precast_check, 1, 3)
        grid.addWidget(self.other_check, 1, 4)
        grid.addWidget(QLabel("Consistencia:"), 2, 0)
        grid.addWidget(self.slump_check, 2, 1)
        grid.addWidget(self.spread_check, 2, 2)
        grid.addWidget(QLabel("Resistencia:"), 1, 5)
        grid.addWidget(self.min_strength, 1, 6)
        grid.addWidget(self.max_strength, 1, 7)
        grid.addWidget(QLabel("Valor consistencia:"), 2, 5)
        grid.addWidget(self.min_consistency, 2, 6)
        grid.addWidget(self.max_consistency, 2, 7)
        grid.addWidget(self.accelerated_only, 3, 5)
        grid.addWidget(clear_filters, 3, 7)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            [
                "Grupo",
                "Nombre",
                "Tipo",
                "Criterio",
                "Resistencia",
                "Consistencia",
                "TMN",
                "Acelerado",
                "Fecha",
                "Producciones",
                "Descripción",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._refresh_statistics)
        self.table.doubleClicked.connect(self._load_selected)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(10, QHeaderView.Stretch)
        for column in range(10):
            if column != 1:
                header.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        self.count_label = QLabel()
        self.count_label.setObjectName("Subtitle")
        table_layout.addWidget(self.count_label)
        table_layout.addWidget(self.table)

        stats_title = QLabel("Desempeño registrado del diseño seleccionado")
        stats_title.setObjectName("SectionTitle")
        self.stats_table = QTableWidget(0, 5)
        self.stats_table.setHorizontalHeaderLabels(
            ["Ensayo", "Edad", "n", "Promedio", "Rango y dispersión"]
        )
        self.stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setAlternatingRowColors(True)
        stats_header = self.stats_table.horizontalHeader()
        for column in (0, 1, 2, 3):
            stats_header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        stats_header.setSectionResizeMode(4, QHeaderView.Stretch)
        stats_card = QFrame()
        stats_card.setObjectName("Card")
        stats_layout = QVBoxLayout(stats_card)
        stats_layout.addWidget(stats_title)
        stats_layout.addWidget(self.stats_table)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(actions)
        layout.addWidget(filters)
        library_splitter = QSplitter(Qt.Horizontal)
        library_splitter.setChildrenCollapsible(False)
        table_card.setMinimumWidth(520)
        stats_card.setMinimumWidth(280)
        library_splitter.addWidget(table_card)
        library_splitter.addWidget(stats_card)
        library_splitter.setStretchFactor(0, 3)
        library_splitter.setStretchFactor(1, 2)
        library_splitter.setSizes([900, 460])
        layout.addWidget(library_splitter, 1)

        state.library_changed.connect(self.refresh)
        state.productions_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        selected_id = self.selected_design_id()
        self._records = self.state.saved_designs
        self._specifications = self.state.laboratory_repository.list_design_specifications()
        self.group_filter.blockSignals(True)
        current_group = self.group_filter.currentData()
        self.group_filter.clear()
        self.group_filter.addItem("Todos los grupos", None)
        self.group_filter.addItem("Sin grupo", "")
        for group in self.state.design_groups:
            self.group_filter.addItem(group, group)
        index = self.group_filter.findData(current_group)
        self.group_filter.setCurrentIndex(max(index, 0))
        self.group_filter.blockSignals(False)
        self._apply_filters(selected_id)

    def _selected_applications(self) -> set[ConcreteApplication]:
        selected = set()
        if self.structural_check.isChecked():
            selected.add(ConcreteApplication.STRUCTURAL)
        if self.pavement_check.isChecked():
            selected.add(ConcreteApplication.PAVEMENT)
        if self.precast_check.isChecked():
            selected.add(ConcreteApplication.PRECAST)
        if self.other_check.isChecked():
            selected.update(
                set(ConcreteApplication)
                - {
                    ConcreteApplication.STRUCTURAL,
                    ConcreteApplication.PAVEMENT,
                    ConcreteApplication.PRECAST,
                }
            )
        return selected

    def _apply_filters(self, selected_id: int | None = None) -> None:
        if selected_id is None or isinstance(selected_id, (str, bool)):
            selected_id = self.selected_design_id()
        query = self.search_edit.text().strip().casefold()
        group_value = self.group_filter.currentData()
        applications = self._selected_applications()
        consistency_types = set()
        if self.slump_check.isChecked():
            consistency_types.add(ConsistencyType.SLUMP)
        if self.spread_check.isChecked():
            consistency_types.add(ConsistencyType.SPREAD)

        filtered = []
        for record in self._records:
            spec = self._specifications.get(record.id) or self.state.get_design_specification(record.id)
            haystack = " ".join(
                [record.name, record.group_name, record.description, spec.keywords]
            ).casefold()
            if query and query not in haystack:
                continue
            if group_value is not None and record.group_name != group_value:
                continue
            if applications and spec.application_type not in applications:
                continue
            if consistency_types and spec.consistency_type not in consistency_types:
                continue
            strength = spec.primary_strength_mpa
            if strength is None or not self.min_strength.value() <= strength <= self.max_strength.value():
                continue
            consistency = spec.consistency_value_mm
            if consistency is None or not self.min_consistency.value() <= consistency <= self.max_consistency.value():
                continue
            if self.accelerated_only.isChecked() and not spec.accelerated:
                continue
            filtered.append((record, spec))

        self.table.setRowCount(len(filtered))
        row_to_select = -1
        for row, (record, spec) in enumerate(filtered):
            if spec.strength_basis == StrengthBasis.FLEXURAL:
                strength_label = "MR"
                strength_value = spec.expected_modulus_rupture_mpa
            elif spec.strength_basis == StrengthBasis.BOTH:
                strength_label = "f'c / MR"
                strength_value = spec.expected_compressive_strength_mpa
            else:
                strength_label = "f'c"
                strength_value = spec.expected_compressive_strength_mpa
            consistency = spec.consistency_value_mm
            values = [
                record.group_name or "Sin grupo",
                record.name,
                APPLICATION_LABELS[spec.application_type],
                strength_label,
                f"{strength_value:.2f} MPa" if strength_value is not None else "—",
                f"{CONSISTENCY_LABELS[spec.consistency_type]} {consistency:.0f} mm" if consistency is not None else "—",
                f"{spec.nominal_max_size_mm:g} mm" if spec.nominal_max_size_mm is not None else "—",
                f"Sí · {spec.accelerated_age_days:g} d" if spec.accelerated and spec.accelerated_age_days is not None else ("Sí" if spec.accelerated else "No"),
                record.created_at.strftime("%Y-%m-%d %H:%M"),
                str(record.production_count),
                record.description,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setData(Qt.UserRole, record.id)
                self.table.setItem(row, column, item)
            if record.id == selected_id:
                row_to_select = row
        self.count_label.setText(f"{len(filtered)} de {len(self._records)} diseños")
        if row_to_select >= 0:
            self.table.selectRow(row_to_select)
        elif filtered:
            self.table.selectRow(0)
        else:
            self.stats_table.setRowCount(0)

    def _clear_filters(self) -> None:
        self.search_edit.clear()
        self.group_filter.setCurrentIndex(0)
        for check in (
            self.structural_check,
            self.pavement_check,
            self.precast_check,
            self.other_check,
            self.slump_check,
            self.spread_check,
            self.accelerated_only,
        ):
            check.setChecked(False)
        self.min_strength.setValue(0.0)
        self.max_strength.setValue(200.0)
        self.min_consistency.setValue(0.0)
        self.max_consistency.setValue(1500.0)
        self._apply_filters()

    def selected_design_id(self) -> int | None:
        row = self.table.currentRow()
        item = self.table.item(row, 1) if row >= 0 else None
        return int(item.data(Qt.UserRole)) if item and item.data(Qt.UserRole) is not None else None

    def _create_group(self) -> None:
        name, accepted = QInputDialog.getText(self, "Crear grupo", "Nombre del grupo:")
        if accepted:
            try:
                self.state.create_design_group(name)
            except Exception as error:
                QMessageBox.critical(self, "No se pudo crear el grupo", str(error))

    def _load_selected(self, *_args) -> None:
        design_id = self.selected_design_id()
        if design_id is None:
            return
        try:
            self.state.load_design_from_library(design_id)
            self.open_laboratory_requested.emit()
        except Exception as error:
            QMessageBox.critical(self, "No se pudo cargar", str(error))

    def _archive_selected(self) -> None:
        design_id = self.selected_design_id()
        if design_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Archivar diseño",
            "El diseño desaparecerá de la lista activa, pero su historial se conservará. ¿Continuar?",
        )
        if answer == QMessageBox.Yes:
            self.state.archive_saved_design(design_id)

    def _refresh_statistics(self) -> None:
        design_id = self.selected_design_id()
        rows = self.state.laboratory_repository.design_statistics(design_id) if design_id else []
        self.stats_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                SPECIMEN_TYPE_LABELS[row.specimen_type],
                f"{row.target_age_days:g} días",
                str(row.result_count),
                f"{row.average_mpa:.3f} MPa",
                (
                    f"{row.minimum_mpa:.3f} – {row.maximum_mpa:.3f} MPa\n"
                    f"s = {row.standard_deviation_mpa if row.standard_deviation_mpa is not None else 'no estimable'} MPa"
                ),
            ]
            for column, value in enumerate(values):
                self.stats_table.setItem(row_index, column, QTableWidgetItem(value))
        self.stats_table.resizeRowsToContents()
