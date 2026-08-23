from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from concrete_mix_designer.domain.models import ConstraintMode, MaterialCategory


CONSTRAINT_LABELS = {
    ConstraintMode.MASS_RATIO: "Relación por masa A/B",
    ConstraintMode.PERCENT_OF_B: "A como porcentaje de B",
    ConstraintMode.PERCENT_OF_PAIR: "A como porcentaje del total A + B",
    ConstraintMode.PERCENT_OF_CEMENTITIOUS: "A como porcentaje del cementante total",
    ConstraintMode.ML_PER_100KG_B: "A en mL por 100 kg de B",
    ConstraintMode.ML_PER_100KG_CEMENTITIOUS: "A en mL por 100 kg de cementante total",
}

DEFAULT_TARGETS = {
    ConstraintMode.MASS_RATIO: 1.0,
    ConstraintMode.PERCENT_OF_B: 10.0,
    ConstraintMode.PERCENT_OF_PAIR: 50.0,
    ConstraintMode.PERCENT_OF_CEMENTITIOUS: 0.8,
    ConstraintMode.ML_PER_100KG_B: 100.0,
    ConstraintMode.ML_PER_100KG_CEMENTITIOUS: 100.0,
}


class RatioConstraintDialog(QDialog):
    """Select components and rule type; the target is edited in the workspace."""

    def __init__(self, components, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva relación o dosificación")
        self.resize(520, 250)
        self.components = [component for component in components if component.enabled]

        self.numerator_combo = QComboBox()
        for component in self.components:
            self.numerator_combo.addItem(
                f"{component.material.name} · {component.unit}", component.uid
            )

        self.mode_combo = QComboBox()
        for mode, label in CONSTRAINT_LABELS.items():
            self.mode_combo.addItem(label, mode)

        self.denominator_combo = QComboBox()
        self.help_label = QLabel()
        self.help_label.setWordWrap(True)
        self.help_label.setObjectName("Subtitle")

        self.numerator_combo.currentIndexChanged.connect(self._refresh_denominator)
        self.mode_combo.currentIndexChanged.connect(self._refresh_denominator)
        self._refresh_denominator()

        form = QFormLayout()
        form.addRow("Material controlado (A):", self.numerator_combo)
        form.addRow("Tipo de relación:", self.mode_combo)
        form.addRow("Material base (B):", self.denominator_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.help_label)
        layout.addWidget(buttons)

    def _refresh_denominator(self) -> None:
        mode = self.mode_combo.currentData()
        numerator_uid = self.numerator_combo.currentData()
        requires_b = mode in {
            ConstraintMode.MASS_RATIO,
            ConstraintMode.PERCENT_OF_B,
            ConstraintMode.PERCENT_OF_PAIR,
            ConstraintMode.ML_PER_100KG_B,
        }
        self.denominator_combo.setEnabled(requires_b)
        self.denominator_combo.clear()
        if requires_b:
            numerator = next((item for item in self.components if item.uid == numerator_uid), None)
            for component in self.components:
                if component.uid == numerator_uid or component.category == MaterialCategory.AIR:
                    continue
                if mode in {
                    ConstraintMode.MASS_RATIO,
                    ConstraintMode.PERCENT_OF_B,
                    ConstraintMode.PERCENT_OF_PAIR,
                } and numerator is not None and component.unit != numerator.unit:
                    continue
                if mode == ConstraintMode.ML_PER_100KG_B and component.unit != "kg":
                    continue
                self.denominator_combo.addItem(
                    f"{component.material.name} · {component.unit}", component.uid
                )

        help_text = {
            ConstraintMode.MASS_RATIO: "Ejemplo: A/B = 0,60. La cantidad de A será 0,60 veces la cantidad de B.",
            ConstraintMode.PERCENT_OF_B: "Ejemplo: A = 20 % de B.",
            ConstraintMode.PERCENT_OF_PAIR: "Ejemplo: A = 80 % del total A+B; útil para cemento y ceniza.",
            ConstraintMode.PERCENT_OF_CEMENTITIOUS: "La masa de A se calcula como porcentaje de la suma de todos los cementantes.",
            ConstraintMode.ML_PER_100KG_B: "La dosis de A se expresa en mL por cada 100 kg del material B.",
            ConstraintMode.ML_PER_100KG_CEMENTITIOUS: "La dosis de A se expresa en mL por cada 100 kg de cementante total.",
        }[mode]
        self.help_label.setText(
            help_text + " Después de guardar, escribe el objetivo directamente en la tabla."
        )

    def _accept(self) -> None:
        if not self.components:
            QMessageBox.warning(self, "Sin componentes", "No hay componentes disponibles.")
            return
        mode = self.mode_combo.currentData()
        numerator = next(
            (item for item in self.components if item.uid == self.numerator_combo.currentData()),
            None,
        )
        if numerator is None:
            return
        if mode in {
            ConstraintMode.PERCENT_OF_CEMENTITIOUS,
            ConstraintMode.ML_PER_100KG_CEMENTITIOUS,
            ConstraintMode.ML_PER_100KG_B,
        } and numerator.category not in {MaterialCategory.ADMIXTURE, MaterialCategory.OTHER}:
            QMessageBox.warning(
                self,
                "Material no compatible",
                "Para una dosificación en porcentaje o mL, selecciona un aditivo u otro material añadido como A.",
            )
            return
        if self.denominator_combo.isEnabled() and self.denominator_combo.currentData() is None:
            QMessageBox.warning(self, "Relación incompleta", "Selecciona el material B.")
            return
        self.accept()

    def values(self) -> tuple[ConstraintMode, str, str | None, float]:
        mode = self.mode_combo.currentData()
        denominator_uid = self.denominator_combo.currentData() if self.denominator_combo.isEnabled() else None
        return (
            mode,
            self.numerator_combo.currentData(),
            denominator_uid,
            DEFAULT_TARGETS[mode],
        )
