from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from concrete_mix_designer.domain.metadata_models import MaterialCharacterization
from concrete_mix_designer.domain.models import CATEGORY_LABELS, MaterialCategory
from concrete_mix_designer.services.app_state import AppState
from concrete_mix_designer.ui.dialogs.material_dialog import MaterialDialog


class MaterialsPage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._materials = []

        title = QLabel("Gestor de materiales")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Registra las propiedades físicas, trazabilidad y caracterización de cada materia prima. "
            "Los agregados admiten una granulometría completa por porcentajes pasantes."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Nombre",
                "Categoría",
                "G.E. cálculo",
                "G.E. seca / SSS",
                "Absorción %",
                "Humedad legacy %",
                "MF / MUC",
                "Granulometría",
                "Origen",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.doubleClicked.connect(lambda _index: self._edit())
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 9):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )

        new_button = QPushButton("Nuevo material")
        new_button.clicked.connect(self._new)
        edit_button = QPushButton("Editar caracterización")
        edit_button.setObjectName("Secondary")
        edit_button.clicked.connect(self._edit)
        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("Danger")
        delete_button.clicked.connect(self._delete)

        buttons = QHBoxLayout()
        buttons.addWidget(new_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addStretch()

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.addLayout(buttons)
        card_layout.addWidget(self.table, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card, 1)

        state.materials_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        selected = self._selected_material()
        selected_id = selected.id if selected else None
        characterizations = self.state.repository.list_characterizations()
        self._materials = self.state.materials
        self.table.setRowCount(len(self._materials))
        for row, material in enumerate(self._materials):
            characterization = characterizations.get(material.id, MaterialCharacterization(material_id=material.id))
            sg_pair = "—"
            if characterization.specific_gravity_dry is not None or characterization.specific_gravity_ssd is not None:
                dry = (
                    f"{characterization.specific_gravity_dry:.3f}"
                    if characterization.specific_gravity_dry is not None
                    else "—"
                )
                ssd = (
                    f"{characterization.specific_gravity_ssd:.3f}"
                    if characterization.specific_gravity_ssd is not None
                    else "—"
                )
                sg_pair = f"{dry} / {ssd}"

            aggregate_metric = "—"
            if material.category == MaterialCategory.FINE_AGGREGATE:
                aggregate_metric = (
                    f"MF {characterization.fineness_modulus:.2f}"
                    if characterization.fineness_modulus is not None
                    else "MF —"
                )
            elif material.category == MaterialCategory.COARSE_AGGREGATE:
                aggregate_metric = (
                    f"MUC {characterization.compacted_unit_weight_kg_m3:.0f} kg/m³"
                    if characterization.compacted_unit_weight_kg_m3 is not None
                    else "MUC —"
                )

            gradation_count = sum(
                point.passing_pct is not None for point in characterization.gradation
            )
            values = [
                material.name,
                CATEGORY_LABELS[material.category],
                f"{material.specific_gravity:.3f}",
                sg_pair,
                f"{material.absorption_pct:.3f}",
                f"{material.moisture_pct:.3f}",
                aggregate_metric,
                f"{gradation_count} tamices" if gradation_count else "—",
                "Inicial" if material.is_seed else "Personalizado",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, material.id)
                self.table.setItem(row, column, item)
            if material.id == selected_id:
                self.table.selectRow(row)

    def _selected_material(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._materials):
            return None
        return self._materials[row]

    def _new(self) -> None:
        dialog = MaterialDialog(parent=self)
        if dialog.exec():
            try:
                self.state.save_material_with_characterization(
                    dialog.result_material(), dialog.characterization
                )
            except Exception as error:
                QMessageBox.critical(self, "No se pudo guardar", str(error))

    def _edit(self) -> None:
        material = self._selected_material()
        if material is None:
            QMessageBox.information(
                self, "Selecciona un material", "Selecciona una fila para editarla."
            )
            return
        characterization = self.state.get_material_characterization(material.id)
        dialog = MaterialDialog(
            material=material,
            characterization=characterization,
            parent=self,
        )
        if dialog.exec():
            try:
                self.state.save_material_with_characterization(
                    dialog.result_material(), dialog.characterization
                )
            except Exception as error:
                QMessageBox.critical(self, "No se pudo guardar", str(error))

    def _delete(self) -> None:
        material = self._selected_material()
        if material is None:
            QMessageBox.information(
                self, "Selecciona un material", "Selecciona una fila para eliminarla."
            )
            return
        if material.is_seed:
            QMessageBox.warning(
                self,
                "Material inicial",
                "Los materiales iniciales pueden editarse, pero no eliminarse.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Eliminar material",
            f"¿Eliminar {material.name} y toda su caracterización?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.state.delete_material(material.id)
        except ValueError as error:
            QMessageBox.warning(self, "No se puede eliminar", str(error))
