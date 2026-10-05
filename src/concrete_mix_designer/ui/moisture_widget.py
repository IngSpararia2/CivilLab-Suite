"""Operational moisture inputs; never writes the material catalog."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLabel, QWidget

from concrete_mix_designer.domain.models import MaterialCategory


class MoistureWidget(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.form = QFormLayout(self)
        self.inputs = {}

    def set_design(self, design):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.inputs = {}
        self.form.addRow(
            QLabel("Humedad de esta amasada (% sobre masa seca OD). Diseño en base SSD.")
        )
        if design is None:
            return
        for component in design.enabled_components():
            if component.category not in (
                MaterialCategory.FINE_AGGREGATE,
                MaterialCategory.COARSE_AGGREGATE,
            ):
                continue
            spin = QDoubleSpinBox()
            spin.setRange(0, 100)
            spin.setDecimals(2)
            spin.setSuffix(" %")
            spin.setKeyboardTracking(False)
            spin.setValue(
                design.batch_moistures.get(component.uid, component.material.moisture_pct)
            )
            spin.setToolTip(
                "Verifica la medición actual. El valor inicial puede proceder del registro legacy."
            )
            self.inputs[component.uid] = spin
            self.form.addRow(
                f"{component.material.name} · absorción {component.material.absorption_pct:g}%",
                spin,
            )
            spin.valueChanged.connect(self.changed)

    def values(self):
        return {uid: spin.value() for uid, spin in self.inputs.items()}
