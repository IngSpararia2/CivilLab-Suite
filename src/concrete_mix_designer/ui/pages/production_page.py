from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.domain.laboratory_models import (
    FRESH_TEST_TYPE_LABELS,
    SPECIMEN_STATUS_LABELS,
    SPECIMEN_TYPE_LABELS,
    FreshTestType,
    SpecimenStatus,
    SpecimenType,
)
from concrete_mix_designer.domain.metadata_models import (
    APPLICATION_LABELS,
    CONSISTENCY_LABELS,
    ConcreteApplication,
    ConsistencyType,
)
from concrete_mix_designer.services.app_state import AppState
from concrete_mix_designer.ui.dialogs.production_dialogs import (
    AddSpecimensDialog,
    CompressionResultDialog,
    FlexuralResultDialog,
    FreshTestDialog,
    ProductionDialog,
)


class ProductionPage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._productions = []

        title = QLabel("Producción y seguimiento de laboratorio")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Cada producción conserva una copia inmutable del diseño fabricado. Puedes volver en cualquier momento para añadir asentamientos, esparcimientos y resultados de resistencia."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar por código, nombre del diseño, grupo u observaciones…")
        self.search_edit.textChanged.connect(
            lambda _text: self._apply_production_filters()
        )
        self.group_filter = QComboBox()
        self.group_filter.currentIndexChanged.connect(
            lambda _index: self._apply_production_filters()
        )
        self.structural_check = QCheckBox("Estructural")
        self.pavement_check = QCheckBox("Pavimento")
        self.precast_check = QCheckBox("Prefabricado")
        self.slump_check = QCheckBox("Asentamiento")
        self.spread_check = QCheckBox("Esparcimiento")
        for check in (
            self.structural_check,
            self.pavement_check,
            self.precast_check,
            self.slump_check,
            self.spread_check,
        ):
            check.toggled.connect(lambda _checked: self._apply_production_filters())
        self.min_strength = QDoubleSpinBox()
        self.max_strength = QDoubleSpinBox()
        for spin in (self.min_strength, self.max_strength):
            spin.setRange(0.0, 200.0)
            spin.setDecimals(1)
            spin.setSuffix(" MPa")
        self.max_strength.setValue(200.0)
        for spin in (self.min_strength, self.max_strength):
            spin.valueChanged.connect(lambda _value: self._apply_production_filters())
        refresh_button = QPushButton("Actualizar")
        refresh_button.setObjectName("Secondary")
        refresh_button.clicked.connect(self.refresh)
        clear_button = QPushButton("Limpiar filtros")
        clear_button.setObjectName("Secondary")
        clear_button.clicked.connect(self._clear_production_filters)

        filter_frame = QFrame()
        filter_frame.setObjectName("Card")
        filter_layout = QGridLayout(filter_frame)
        filter_layout.addWidget(QLabel("Buscar:"), 0, 0)
        filter_layout.addWidget(self.search_edit, 0, 1, 1, 4)
        filter_layout.addWidget(QLabel("Grupo:"), 0, 5)
        filter_layout.addWidget(self.group_filter, 0, 6)
        filter_layout.addWidget(QLabel("Tipo:"), 1, 0)
        filter_layout.addWidget(self.structural_check, 1, 1)
        filter_layout.addWidget(self.pavement_check, 1, 2)
        filter_layout.addWidget(self.precast_check, 1, 3)
        filter_layout.addWidget(self.slump_check, 2, 1)
        filter_layout.addWidget(self.spread_check, 2, 2)
        filter_layout.addWidget(QLabel("Resistencia:"), 1, 5)
        filter_layout.addWidget(self.min_strength, 1, 6)
        filter_layout.addWidget(self.max_strength, 1, 7)
        filter_layout.addWidget(refresh_button, 2, 6)
        filter_layout.addWidget(clear_button, 2, 7)

        self.production_table = QTableWidget(0, 10)
        self.production_table.setHorizontalHeaderLabels(
            [
                "Fecha y hora", "Código", "Grupo", "Diseño", "Tipo",
                "Resistencia", "Consistencia", "Volumen", "Muestras", "Ensayadas"
            ]
        )
        self.production_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.production_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.production_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.production_table.verticalHeader().setVisible(False)
        self.production_table.setAlternatingRowColors(True)
        self.production_table.itemSelectionChanged.connect(self._refresh_detail)
        header = self.production_table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        for column in (0, 1, 2, 4, 5, 6, 7, 8, 9):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        left_card = QFrame()
        left_card.setObjectName("Card")
        left_layout = QVBoxLayout(left_card)
        left_layout.addWidget(QLabel("Historial de producciones"))
        left_layout.addWidget(self.production_table)

        self.production_title = QLabel("Selecciona una producción")
        self.production_title.setObjectName("SectionTitle")
        self.production_summary = QLabel()
        self.production_summary.setWordWrap(True)
        self.production_summary.setObjectName("Subtitle")

        self.detail_tabs = QTabWidget()
        self.detail_tabs.addTab(self._build_fresh_tab(), "Concreto fresco")
        self.detail_tabs.addTab(self._build_specimen_tab(), "Muestras y resistencias")

        right_card = QFrame()
        right_card.setObjectName("Card")
        right_layout = QVBoxLayout(right_card)
        right_layout.addWidget(self.production_title)
        right_layout.addWidget(self.production_summary)
        right_layout.addWidget(self.detail_tabs, 1)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left_card)
        splitter.addWidget(right_card)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([560, 820])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(filter_frame)
        layout.addWidget(splitter, 1)

        state.productions_changed.connect(self.refresh)
        state.library_changed.connect(self.refresh)
        self.refresh()

    def _build_fresh_tab(self) -> QWidget:
        page = QWidget()
        self.add_fresh_button = QPushButton("Añadir dato de concreto fresco")
        self.add_fresh_button.clicked.connect(self._add_fresh_test)
        self.edit_fresh_button = QPushButton("Editar dato seleccionado")
        self.edit_fresh_button.setObjectName("Secondary")
        self.edit_fresh_button.clicked.connect(self._edit_fresh_test)
        self.delete_fresh_button = QPushButton("Eliminar dato seleccionado")
        self.delete_fresh_button.setObjectName("Danger")
        self.delete_fresh_button.clicked.connect(self._delete_fresh_test)

        self.fresh_table = QTableWidget(0, 8)
        self.fresh_table.setHorizontalHeaderLabels(
            ["Lectura", "Tiempo", "Tipo", "Resultado", "Temperatura", "Aire", "Masa unitaria", "Notas"]
        )
        self.fresh_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fresh_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.fresh_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.fresh_table.verticalHeader().setVisible(False)
        self.fresh_table.setAlternatingRowColors(True)
        self.fresh_table.doubleClicked.connect(self._edit_fresh_test)
        self.fresh_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        layout = QVBoxLayout(page)
        actions = QHBoxLayout()
        actions.addWidget(self.add_fresh_button)
        actions.addWidget(self.edit_fresh_button)
        actions.addStretch()
        actions.addWidget(self.delete_fresh_button)
        layout.addLayout(actions)
        layout.addWidget(self.fresh_table)
        return page

    def _build_specimen_tab(self) -> QWidget:
        page = QWidget()
        add_specimens = QPushButton("Añadir muestras")
        add_specimens.clicked.connect(self._add_specimens)
        self.result_button = QPushButton("Registrar o editar resultado")
        self.result_button.clicked.connect(self._register_result)
        delete_result_button = QPushButton("Eliminar resultado")
        delete_result_button.setObjectName("Danger")
        delete_result_button.clicked.connect(self._delete_result)
        cancel_button = QPushButton("Cancelar muestra")
        cancel_button.setObjectName("Danger")
        cancel_button.clicked.connect(self._cancel_specimen)

        actions = QHBoxLayout()
        actions.addWidget(add_specimens)
        actions.addWidget(self.result_button)
        actions.addStretch()
        actions.addWidget(delete_result_button)
        actions.addWidget(cancel_button)

        self.specimen_table = QTableWidget(0, 9)
        self.specimen_table.setHorizontalHeaderLabels(
            ["Código", "Tipo", "Edad obj.", "Fecha prevista", "Estado", "Carga máx.", "Resultado", "Edad real", "Ensayado"]
        )
        self.specimen_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.specimen_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.specimen_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.specimen_table.verticalHeader().setVisible(False)
        self.specimen_table.setAlternatingRowColors(True)
        self.specimen_table.doubleClicked.connect(self._register_result)
        self.specimen_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        layout = QVBoxLayout(page)
        layout.addLayout(actions)
        layout.addWidget(self.specimen_table)
        return page

    def refresh(self) -> None:
        selected = self.selected_production_id()
        self._all_productions = self.state.productions
        self._design_records = {
            record.id: record
            for record in self.state.laboratory_repository.list_designs(
                include_archived=True
            )
        }
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
        self._apply_production_filters(selected)

    def _apply_production_filters(self, selected_id=None) -> None:
        valid_ids = {item.id for item in getattr(self, "_all_productions", [])}
        if selected_id not in valid_ids:
            selected_id = self.selected_production_id()
        query = self.search_edit.text().strip().casefold()
        group_value = self.group_filter.currentData()
        applications = set()
        if self.structural_check.isChecked():
            applications.add(ConcreteApplication.STRUCTURAL)
        if self.pavement_check.isChecked():
            applications.add(ConcreteApplication.PAVEMENT)
        if self.precast_check.isChecked():
            applications.add(ConcreteApplication.PRECAST)
        consistencies = set()
        if self.slump_check.isChecked():
            consistencies.add(ConsistencyType.SLUMP)
        if self.spread_check.isChecked():
            consistencies.add(ConsistencyType.SPREAD)

        filtered = []
        self._production_specs = {}
        for production in getattr(self, "_all_productions", []):
            record = self._design_records.get(production.design_id)
            group_name = record.group_name if record else ""
            description = record.description if record else ""
            spec = self.state.laboratory_repository.get_production_specification(production.id)
            self._production_specs[production.id] = spec
            haystack = " ".join(
                [production.batch_code, production.design_name, group_name, description, production.notes]
            ).casefold()
            if query and query not in haystack:
                continue
            if group_value is not None and group_name != group_value:
                continue
            if applications and spec.application_type not in applications:
                continue
            if consistencies and spec.consistency_type not in consistencies:
                continue
            strength = spec.primary_strength_mpa
            if strength is None or not self.min_strength.value() <= strength <= self.max_strength.value():
                continue
            filtered.append((production, record, spec))

        self._productions = [item[0] for item in filtered]
        self.production_table.setRowCount(len(filtered))
        row_to_select = -1
        for row, (production, record, spec) in enumerate(filtered):
            consistency = spec.consistency_value_mm
            values = [
                production.produced_at.strftime("%Y-%m-%d %H:%M"),
                production.batch_code,
                (record.group_name if record and record.group_name else "Sin grupo"),
                production.design_name,
                APPLICATION_LABELS[spec.application_type],
                f"{spec.primary_strength_mpa:.2f} MPa" if spec.primary_strength_mpa is not None else "—",
                f"{CONSISTENCY_LABELS[spec.consistency_type]} {consistency:.0f} mm" if consistency is not None else "—",
                f"{production.batch_volume_m3:.4f} m³",
                str(production.specimen_count),
                str(production.tested_specimen_count),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, production.id)
                self.production_table.setItem(row, column, item)
            if production.id == selected_id:
                row_to_select = row
        if row_to_select >= 0:
            self.production_table.selectRow(row_to_select)
        elif filtered:
            self.production_table.selectRow(0)
        else:
            self._clear_detail()

    def _clear_production_filters(self) -> None:
        self.search_edit.clear()
        self.group_filter.setCurrentIndex(0)
        for check in (
            self.structural_check,
            self.pavement_check,
            self.precast_check,
            self.slump_check,
            self.spread_check,
        ):
            check.setChecked(False)
        self.min_strength.setValue(0.0)
        self.max_strength.setValue(200.0)
        self._apply_production_filters()

    def selected_production_id(self) -> int | None:
        row = self.production_table.currentRow()
        item = self.production_table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.UserRole)) if item and item.data(Qt.UserRole) is not None else None

    def selected_fresh_test_id(self) -> int | None:
        row = self.fresh_table.currentRow()
        item = self.fresh_table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.UserRole)) if item and item.data(Qt.UserRole) is not None else None

    def selected_specimen_id(self) -> int | None:
        row = self.specimen_table.currentRow()
        item = self.specimen_table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.UserRole)) if item and item.data(Qt.UserRole) is not None else None

    def select_production(self, production_id: int) -> None:
        self.refresh()
        for row in range(self.production_table.rowCount()):
            item = self.production_table.item(row, 0)
            if item and item.data(Qt.UserRole) == production_id:
                self.production_table.selectRow(row)
                self.production_table.scrollToItem(item)
                return

    def _new_production(self) -> None:
        designs = self.state.saved_designs
        if not designs:
            QMessageBox.information(
                self,
                "No hay diseños guardados",
                "Guarda el diseño calculado desde la pestaña Laboratorio antes de registrar producción.",
            )
            return
        dialog = ProductionDialog(designs, parent=self)
        if dialog.exec():
            try:
                production = self.state.create_production(**dialog.values)
                self.select_production(production.id)
            except Exception as error:
                QMessageBox.critical(self, "No se pudo registrar", str(error))

    def _refresh_detail(self) -> None:
        production_id = self.selected_production_id()
        production = self.state.laboratory_repository.get_production(production_id) if production_id else None
        if production is None:
            self._clear_detail()
            return

        self.production_title.setText(
            f"{production.batch_code} · {production.design_name}"
        )
        self.production_summary.setText(
            f"Fabricada: {production.produced_at:%Y-%m-%d %H:%M} · "
            f"Volumen: {production.batch_volume_m3:.4f} m³ · "
            f"Muestras ensayadas: {production.tested_specimen_count}/{production.specimen_count}\n"
            f"{production.notes or 'Sin observaciones.'}"
        )
        self._refresh_fresh_tests(production.id)
        self._refresh_specimens(production.id)

    def _refresh_fresh_tests(self, production_id: int) -> None:
        tests = self.state.laboratory_repository.list_fresh_tests(production_id)
        self.fresh_table.setRowCount(len(tests))
        for row, test in enumerate(tests):
            if test.test_type == FreshTestType.SLUMP:
                result = (
                    f"{test.slump_mm / 25.4:.2f} in ({test.slump_mm:.1f} mm)"
                    if test.slump_mm is not None
                    else "—"
                )
            else:
                d1 = f"{test.spread_d1_mm:.1f}" if test.spread_d1_mm is not None else "—"
                d2 = f"{test.spread_d2_mm:.1f}" if test.spread_d2_mm is not None else "—"
                average = test.spread_average_mm
                result = f"{d1} / {d2} mm (prom. {average:.1f})" if average is not None else "—"
            values = [
                test.measured_at.strftime("%Y-%m-%d %H:%M"),
                self._format_elapsed(test.elapsed_minutes),
                FRESH_TEST_TYPE_LABELS[test.test_type],
                result,
                f"{test.concrete_temperature_c:.1f} °C" if test.concrete_temperature_c is not None else "—",
                f"{test.air_content_pct:.2f} %" if test.air_content_pct is not None else "—",
                f"{test.unit_weight_kg_m3:.1f} kg/m³" if test.unit_weight_kg_m3 is not None else "—",
                test.notes,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, test.id)
                self.fresh_table.setItem(row, column, item)

    def _refresh_specimens(self, production_id: int) -> None:
        specimens = self.state.laboratory_repository.list_specimens(production_id)
        self.specimen_table.setRowCount(len(specimens))
        for row, specimen in enumerate(specimens):
            load = "—"
            result = "—"
            actual_age = "—"
            tested_at = "—"
            if specimen.specimen_type == SpecimenType.CYLINDER:
                record = self.state.laboratory_repository.get_compression_result(specimen.id)
                if record:
                    load = f"{record.max_load_kn:.3f} kN"
                    result = f"{record.strength_mpa:.3f} MPa"
                    actual_age = f"{record.actual_age_days:.2f} d"
                    tested_at = record.tested_at.strftime("%Y-%m-%d %H:%M")
            else:
                record = self.state.laboratory_repository.get_flexural_result(specimen.id)
                if record:
                    load = f"{record.max_load_kn:.3f} kN"
                    result = f"{record.modulus_of_rupture_mpa:.3f} MPa"
                    actual_age = f"{record.actual_age_days:.2f} d"
                    tested_at = record.tested_at.strftime("%Y-%m-%d %H:%M")
            values = [
                specimen.specimen_code,
                SPECIMEN_TYPE_LABELS[specimen.specimen_type],
                f"{specimen.target_age_days:g} d",
                specimen.planned_test_at.strftime("%Y-%m-%d %H:%M"),
                SPECIMEN_STATUS_LABELS[specimen.status],
                load,
                result,
                actual_age,
                tested_at,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, specimen.id)
                self.specimen_table.setItem(row, column, item)

    def _add_fresh_test(self) -> None:
        production_id = self.selected_production_id()
        production = self.state.laboratory_repository.get_production(production_id) if production_id else None
        if production is None:
            QMessageBox.information(self, "Selecciona producción", "Selecciona una producción primero.")
            return
        dialog = FreshTestDialog(produced_at=production.produced_at, parent=self)
        if dialog.exec():
            try:
                self.state.add_fresh_test(production_id=production.id, **dialog.values)
                self._refresh_detail()
            except Exception as error:
                QMessageBox.critical(self, "No se pudo guardar", str(error))

    def _edit_fresh_test(self, *_args) -> None:
        test_id = self.selected_fresh_test_id()
        test = self.state.laboratory_repository.get_fresh_test(test_id) if test_id else None
        if test is None:
            QMessageBox.information(
                self,
                "Selecciona un dato",
                "Selecciona una lectura de concreto fresco para editarla.",
            )
            return
        production = self.state.laboratory_repository.get_production(test.production_id)
        if production is None:
            QMessageBox.warning(self, "Producción no disponible", "La producción asociada no existe.")
            return
        dialog = FreshTestDialog(
            produced_at=production.produced_at, existing=test, parent=self
        )
        if dialog.exec():
            try:
                self.state.update_fresh_test(test_id=test.id, **dialog.values)
                self._refresh_detail()
            except Exception as error:
                QMessageBox.critical(self, "No se pudo actualizar", str(error))

    def _delete_fresh_test(self) -> None:
        test_id = self.selected_fresh_test_id()
        if test_id is None:
            QMessageBox.information(
                self,
                "Selecciona un dato",
                "Selecciona una lectura de concreto fresco para eliminarla.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Eliminar dato de concreto fresco",
            "La lectura se eliminará permanentemente. ¿Continuar?",
        )
        if answer == QMessageBox.Yes:
            try:
                self.state.delete_fresh_test(test_id)
                self._refresh_detail()
            except Exception as error:
                QMessageBox.critical(self, "No se pudo eliminar", str(error))

    def _add_specimens(self) -> None:
        production_id = self.selected_production_id()
        if production_id is None:
            return
        dialog = AddSpecimensDialog(self)
        if dialog.exec():
            try:
                self.state.add_specimen_schedule(production_id=production_id, **dialog.values)
                self._refresh_detail()
            except Exception as error:
                QMessageBox.critical(self, "No se pudo añadir", str(error))

    def _register_result(self, *_args) -> None:
        specimen_id = self.selected_specimen_id()
        specimen = self.state.laboratory_repository.get_specimen(specimen_id) if specimen_id else None
        if specimen is None:
            QMessageBox.information(self, "Selecciona muestra", "Selecciona una muestra programada.")
            return
        try:
            if specimen.specimen_type == SpecimenType.CYLINDER:
                existing = self.state.laboratory_repository.get_compression_result(specimen.id)
                dialog = CompressionResultDialog(
                    self.state.laboratory_repository, specimen, existing, self
                )
                if dialog.exec():
                    self.state.record_compression_result(
                        specimen_id=specimen.id, **dialog.values
                    )
            else:
                existing = self.state.laboratory_repository.get_flexural_result(specimen.id)
                dialog = FlexuralResultDialog(
                    self.state.laboratory_repository, specimen, existing, self
                )
                if dialog.exec():
                    self.state.record_flexural_result(
                        specimen_id=specimen.id, **dialog.values
                    )
            self._refresh_detail()
        except Exception as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))

    def _delete_result(self) -> None:
        specimen_id = self.selected_specimen_id()
        if specimen_id is None:
            QMessageBox.information(
                self, "Selecciona muestra", "Selecciona una muestra programada."
            )
            return
        specimen = self.state.laboratory_repository.get_specimen(specimen_id)
        if specimen is None:
            return
        existing = (
            self.state.laboratory_repository.get_compression_result(specimen_id)
            if specimen.specimen_type == SpecimenType.CYLINDER
            else self.state.laboratory_repository.get_flexural_result(specimen_id)
        )
        if existing is None:
            QMessageBox.information(
                self,
                "Sin resultado",
                "La muestra seleccionada todavía no tiene un resultado registrado.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Eliminar resultado",
            "El resultado se eliminará y la muestra volverá al estado Programado. ¿Continuar?",
        )
        if answer == QMessageBox.Yes:
            try:
                self.state.delete_specimen_result(specimen_id)
                self._refresh_detail()
            except Exception as error:
                QMessageBox.critical(self, "No se pudo eliminar", str(error))

    def _cancel_specimen(self) -> None:
        specimen_id = self.selected_specimen_id()
        if specimen_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Cancelar muestra",
            "La muestra quedará registrada como cancelada. ¿Continuar?",
        )
        if answer == QMessageBox.Yes:
            self.state.set_specimen_status(specimen_id, SpecimenStatus.CANCELLED)
            self._refresh_detail()

    def _clear_detail(self) -> None:
        self.production_title.setText("Selecciona una producción")
        self.production_summary.clear()
        self.fresh_table.setRowCount(0)
        self.specimen_table.setRowCount(0)

    @staticmethod
    def _format_elapsed(minutes: int) -> str:
        hours, remaining = divmod(minutes, 60)
        if hours:
            return f"{hours} h {remaining} min"
        return f"{remaining} min"
