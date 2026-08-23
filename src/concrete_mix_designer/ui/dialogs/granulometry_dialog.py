from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from concrete_mix_designer.domain.metadata_models import GradationPoint
from concrete_mix_designer.domain.models import MaterialCategory


FINE_SIEVES = [
    ("3/8 in", 9.50),
    ("No. 4", 4.75),
    ("No. 8", 2.36),
    ("No. 16", 1.18),
    ("No. 30", 0.600),
    ("No. 50", 0.300),
    ("No. 100", 0.150),
    ("No. 200", 0.075),
]

COARSE_SIEVES = [
    ("3 in", 75.0),
    ("2 1/2 in", 63.0),
    ("2 in", 50.0),
    ("1 1/2 in", 37.5),
    ("1 in", 25.0),
    ("3/4 in", 19.0),
    ("1/2 in", 12.5),
    ("3/8 in", 9.50),
    ("No. 4", 4.75),
    ("No. 8", 2.36),
    ("No. 16", 1.18),
    ("No. 200", 0.075),
]


class GranulometryDialog(QDialog):
    def __init__(
        self,
        category: MaterialCategory,
        existing: list[GradationPoint] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.category = MaterialCategory(category)
        self.setWindowTitle("Granulometría del agregado · porcentajes pasantes")
        self.resize(620, 650)

        explanation = QLabel(
            "Registra el porcentaje que pasa por cada tamiz. Puedes dejar como — los tamices "
            "no utilizados. La aplicación valida que el porcentaje pasante no aumente al "
            "disminuir la abertura del tamiz."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("Subtitle")

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Tamiz", "Abertura (mm)", "% pasa"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        existing_map = {
            point.sieve_label.casefold(): point for point in (existing or [])
        }
        presets = (
            FINE_SIEVES
            if self.category == MaterialCategory.FINE_AGGREGATE
            else COARSE_SIEVES
        )
        for label, opening in presets:
            existing_point = existing_map.pop(label.casefold(), None)
            self._add_row(
                label,
                opening,
                existing_point.passing_pct if existing_point else None,
            )
        for point in sorted(
            existing_map.values(), key=lambda item: item.opening_mm, reverse=True
        ):
            self._add_row(point.sieve_label, point.opening_mm, point.passing_pct)

        add_sieve = QPushButton("Añadir tamiz personalizado")
        add_sieve.setObjectName("Secondary")
        add_sieve.clicked.connect(self._add_custom_sieve)
        remove_sieve = QPushButton("Eliminar tamiz seleccionado")
        remove_sieve.setObjectName("Danger")
        remove_sieve.clicked.connect(self._remove_selected)

        actions = QHBoxLayout()
        actions.addWidget(add_sieve)
        actions.addWidget(remove_sieve)
        actions.addStretch()

        self.fm_label = QLabel()
        self.fm_label.setObjectName("Metric")
        calculate_fm = QPushButton("Calcular módulo de finura")
        calculate_fm.clicked.connect(self._show_fineness_modulus)
        fm_row = QHBoxLayout()
        fm_row.addWidget(calculate_fm)
        fm_row.addWidget(self.fm_label)
        fm_row.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addLayout(actions)
        layout.addWidget(self.table, 1)
        if self.category == MaterialCategory.FINE_AGGREGATE:
            layout.addLayout(fm_row)
        layout.addWidget(buttons)

    def _add_row(
        self,
        label: str,
        opening_mm: float,
        passing_pct: float | None,
    ) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        label_item = QTableWidgetItem(label)
        label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
        opening_item = QTableWidgetItem()
        opening_item.setData(Qt.DisplayRole, float(opening_mm))
        opening_item.setData(Qt.UserRole, float(opening_mm))
        opening_item.setFlags(opening_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, label_item)
        self.table.setItem(row, 1, opening_item)

        passing = QDoubleSpinBox()
        passing.setRange(-1.0, 100.0)
        passing.setDecimals(2)
        passing.setSuffix(" %")
        passing.setSpecialValueText("—")
        passing.setValue(-1.0 if passing_pct is None else float(passing_pct))
        self.table.setCellWidget(row, 2, passing)
        self._sort_rows()

    def _sort_rows(self) -> None:
        self.table.setSortingEnabled(True)
        self.table.sortItems(1, Qt.DescendingOrder)
        self.table.setSortingEnabled(False)

    def _add_custom_sieve(self) -> None:
        label, accepted = QInputDialog.getText(
            self, "Tamiz personalizado", "Identificación del tamiz:"
        )
        if not accepted or not label.strip():
            return
        opening, accepted = QInputDialog.getDouble(
            self,
            "Tamiz personalizado",
            "Abertura en milímetros:",
            1.0,
            0.001,
            1000.0,
            3,
        )
        if accepted:
            self._add_row(label.strip(), opening, None)

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    @property
    def gradation(self) -> list[GradationPoint]:
        rows: list[GradationPoint] = []
        for row in range(self.table.rowCount()):
            label_item = self.table.item(row, 0)
            opening_item = self.table.item(row, 1)
            passing_widget = self.table.cellWidget(row, 2)
            if label_item is None or opening_item is None:
                continue
            passing = None
            if isinstance(passing_widget, QDoubleSpinBox) and passing_widget.value() >= 0:
                passing = float(passing_widget.value())
            rows.append(
                GradationPoint(
                    sieve_label=label_item.text().strip(),
                    opening_mm=float(opening_item.data(Qt.UserRole)),
                    passing_pct=passing,
                    sort_order=row,
                )
            )
        return sorted(rows, key=lambda item: item.opening_mm, reverse=True)

    @property
    def fineness_modulus(self) -> float | None:
        values = {
            point.sieve_label.casefold(): point.passing_pct
            for point in self.gradation
            if point.passing_pct is not None
        }
        required = ["no. 4", "no. 8", "no. 16", "no. 30", "no. 50", "no. 100"]
        if not all(label in values for label in required):
            return None
        return sum(100.0 - float(values[label]) for label in required) / 100.0

    def _show_fineness_modulus(self) -> None:
        value = self.fineness_modulus
        self.fm_label.setText(
            f"MF calculado: {value:.2f}"
            if value is not None
            else "Completa No. 4, 8, 16, 30, 50 y 100"
        )

    def accept(self) -> None:
        populated = [point for point in self.gradation if point.passing_pct is not None]
        previous = 100.0
        for point in populated:
            if point.passing_pct is None:
                continue
            if point.passing_pct > previous + 1e-6:
                QMessageBox.warning(
                    self,
                    "Granulometría inconsistente",
                    f"El porcentaje pasante en {point.sieve_label} no puede ser mayor "
                    "que el registrado para un tamiz de mayor abertura.",
                )
                return
            previous = point.passing_pct
        super().accept()
