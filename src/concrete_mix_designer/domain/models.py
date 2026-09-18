from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any
from uuid import uuid4


class MaterialCategory(StrEnum):
    WATER = "water"
    CEMENTITIOUS = "cementitious"
    FINE_AGGREGATE = "fine_aggregate"
    COARSE_AGGREGATE = "coarse_aggregate"
    ADMIXTURE = "admixture"
    AIR = "air"
    OTHER = "other"


class DosageMode(StrEnum):
    """Legacy material defaults kept for database compatibility.

    Since v0.3, active dosages are defined as explicit design constraints instead
    of hidden component parameters in the Laboratory table.
    """

    MANUAL_KG = "manual_kg"
    PCT_CEMENTITIOUS = "pct_cementitious"
    ML_PER_100KG = "ml_per_100kg"


class ConstraintMode(StrEnum):
    MASS_RATIO = "mass_ratio"
    PERCENT_OF_B = "percent_of_b"
    PERCENT_OF_PAIR = "percent_of_pair"
    PERCENT_OF_CEMENTITIOUS = "percent_of_cementitious"
    ML_PER_100KG_B = "ml_per_100kg_b"
    ML_PER_100KG_CEMENTITIOUS = "ml_per_100kg_cementitious"


CATEGORY_LABELS: dict[MaterialCategory, str] = {
    MaterialCategory.WATER: "Agua",
    MaterialCategory.CEMENTITIOUS: "Material cementante",
    MaterialCategory.FINE_AGGREGATE: "Agregado fino",
    MaterialCategory.COARSE_AGGREGATE: "Agregado grueso",
    MaterialCategory.ADMIXTURE: "Aditivo",
    MaterialCategory.AIR: "Aire",
    MaterialCategory.OTHER: "Otro",
}


def _finite_float(value: object, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} debe ser un número finito.") from error
    if not isfinite(numeric):
        raise ValueError(f"{label} debe ser un número finito.")
    return numeric


def _optional_finite_float(value: object | None, label: str) -> float | None:
    return None if value is None else _finite_float(value, label)


@dataclass(slots=True)
class Material:
    id: int | None
    name: str
    category: MaterialCategory
    specific_gravity: float
    absorption_pct: float = 0.0
    moisture_pct: float = 0.0
    dosage_mode: DosageMode = DosageMode.MANUAL_KG
    dosage_value: float = 0.0
    is_seed: bool = False

    @property
    def density_kg_l(self) -> float:
        return self.specific_gravity


@dataclass(slots=True)
class MixComponent:
    material: Material
    quantity: float
    locked: bool = False
    enabled: bool = True
    # Legacy fields are retained so v0.1/v0.2 JSON files still open. They are
    # migrated to visible constraints and no longer drive the solver directly.
    blend_pct: float = 0.0
    dosage_mode: DosageMode | None = None
    dosage_value: float | None = None
    uid: str = field(default_factory=lambda: uuid4().hex)

    @property
    def category(self) -> MaterialCategory:
        return self.material.category

    @property
    def unit(self) -> str:
        return "L" if self.category == MaterialCategory.AIR else "kg"

    @property
    def absolute_volume_l(self) -> float:
        if not self.enabled:
            return 0.0
        if self.category == MaterialCategory.AIR:
            return max(self.quantity, 0.0)
        sg = max(self.material.specific_gravity, 1e-9)
        return max(self.quantity, 0.0) / sg

    @property
    def effective_dosage_mode(self) -> DosageMode:
        return self.dosage_mode or self.material.dosage_mode

    @property
    def effective_dosage_value(self) -> float:
        return self.material.dosage_value if self.dosage_value is None else self.dosage_value


@dataclass(slots=True)
class RatioConstraint:
    """Visible relationship or dosage rule between design components.

    ``target_ratio`` is retained as the serialized field name for backward
    compatibility. Its meaning depends on ``mode``: ratio, percent or mL/100 kg.
    """

    numerator_uid: str
    denominator_uid: str | None
    target_ratio: float
    mode: ConstraintMode = ConstraintMode.MASS_RATIO
    name: str = ""
    enabled: bool = True
    uid: str = field(default_factory=lambda: uuid4().hex)

    @property
    def requires_denominator(self) -> bool:
        return self.mode in {
            ConstraintMode.MASS_RATIO,
            ConstraintMode.PERCENT_OF_B,
            ConstraintMode.PERCENT_OF_PAIR,
            ConstraintMode.ML_PER_100KG_B,
        }


@dataclass(slots=True)
class MixParameters:
    fc_mpa: float = 28.0
    slump_mm: float = 100.0
    nominal_max_size_mm: float = 19.0
    target_w_cm: float = 0.50
    w_cm_locked: bool = True
    target_volume_l: float = 1000.0


@dataclass(slots=True)
class MixDesign:
    parameters: MixParameters = field(default_factory=MixParameters)
    components: list[MixComponent] = field(default_factory=list)
    ratio_constraints: list[RatioConstraint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def enabled_components(self) -> list[MixComponent]:
        return [component for component in self.components if component.enabled]

    def by_category(self, category: MaterialCategory) -> list[MixComponent]:
        return [
            component
            for component in self.components
            if component.enabled and component.category == category
        ]

    def component(self, uid: str | None) -> MixComponent | None:
        if uid is None:
            return None
        return next((component for component in self.components if component.uid == uid), None)

    @property
    def relation_controlled_uids(self) -> set[str]:
        """Components whose manual quantity is governed by an active relation."""

        return {
            constraint.numerator_uid
            for constraint in self.ratio_constraints
            if constraint.enabled
        }

    @property
    def total_absolute_volume_l(self) -> float:
        return sum(component.absolute_volume_l for component in self.enabled_components())

    @property
    def total_cementitious_kg(self) -> float:
        return sum(component.quantity for component in self.by_category(MaterialCategory.CEMENTITIOUS))

    @property
    def water_kg(self) -> float:
        return sum(component.quantity for component in self.by_category(MaterialCategory.WATER))

    @property
    def actual_w_cm(self) -> float:
        cementitious = self.total_cementitious_kg
        return self.water_kg / cementitious if cementitious > 0 else 0.0

    @property
    def fine_aggregate_pct(self) -> float:
        fine = sum(component.quantity for component in self.by_category(MaterialCategory.FINE_AGGREGATE))
        coarse = sum(component.quantity for component in self.by_category(MaterialCategory.COARSE_AGGREGATE))
        total = fine + coarse
        return 100.0 * fine / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        constraints = []
        for constraint in self.ratio_constraints:
            row = asdict(constraint)
            row["mode"] = constraint.mode.value
            constraints.append(row)
        return {
            "parameters": asdict(self.parameters),
            "ratio_constraints": constraints,
            "components": [
                {
                    "uid": component.uid,
                    "quantity": component.quantity,
                    "locked": component.locked,
                    "enabled": component.enabled,
                    "blend_pct": component.blend_pct,
                    "dosage_mode": component.dosage_mode.value if component.dosage_mode else None,
                    "dosage_value": component.dosage_value,
                    "material": {
                        "id": component.material.id,
                        "name": component.material.name,
                        "category": component.material.category.value,
                        "specific_gravity": component.material.specific_gravity,
                        "absorption_pct": component.material.absorption_pct,
                        "moisture_pct": component.material.moisture_pct,
                        "dosage_mode": component.material.dosage_mode.value,
                        "dosage_value": component.material.dosage_value,
                        "is_seed": component.material.is_seed,
                    },
                }
                for component in self.components
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MixDesign":
        parameter_data = dict(payload.get("parameters", {}))
        params = MixParameters(
            fc_mpa=_finite_float(parameter_data.get("fc_mpa", 28.0), "La resistencia"),
            slump_mm=_finite_float(
                parameter_data.get("slump_mm", 100.0), "El asentamiento"
            ),
            nominal_max_size_mm=_finite_float(
                parameter_data.get("nominal_max_size_mm", 19.0),
                "El tamaño máximo nominal",
            ),
            target_w_cm=_finite_float(
                parameter_data.get("target_w_cm", 0.50),
                "La relación agua/material cementante",
            ),
            w_cm_locked=bool(parameter_data.get("w_cm_locked", True)),
            target_volume_l=_finite_float(
                parameter_data.get("target_volume_l", 1000.0), "El volumen objetivo"
            ),
        )
        components: list[MixComponent] = []
        for row in payload.get("components", []):
            material_data = row["material"]
            material = Material(
                id=material_data.get("id"),
                name=material_data["name"],
                category=MaterialCategory(material_data["category"]),
                specific_gravity=_finite_float(
                    material_data["specific_gravity"], "La gravedad específica"
                ),
                absorption_pct=_finite_float(
                    material_data.get("absorption_pct", 0.0), "La absorción"
                ),
                moisture_pct=_finite_float(
                    material_data.get("moisture_pct", 0.0), "La humedad"
                ),
                dosage_mode=DosageMode(material_data.get("dosage_mode", DosageMode.MANUAL_KG)),
                dosage_value=_finite_float(
                    material_data.get("dosage_value", 0.0), "La dosificación"
                ),
                is_seed=bool(material_data.get("is_seed", False)),
            )
            mode_value = row.get("dosage_mode")
            components.append(
                MixComponent(
                    uid=row.get("uid", uuid4().hex),
                    material=material,
                    quantity=_finite_float(
                        row.get("quantity", 0.0), f"La cantidad de {material.name}"
                    ),
                    locked=bool(row.get("locked", False)),
                    enabled=bool(row.get("enabled", True)),
                    blend_pct=_finite_float(
                        row.get("blend_pct", 0.0), "El porcentaje de combinación"
                    ),
                    dosage_mode=DosageMode(mode_value) if mode_value else None,
                    dosage_value=_optional_finite_float(
                        row.get("dosage_value"), "La dosificación del componente"
                    ),
                )
            )

        constraints: list[RatioConstraint] = []
        for row in payload.get("ratio_constraints", []):
            constraints.append(
                RatioConstraint(
                    uid=row.get("uid", uuid4().hex),
                    name=str(row.get("name", "")),
                    numerator_uid=row["numerator_uid"],
                    denominator_uid=row.get("denominator_uid"),
                    target_ratio=_finite_float(
                        row.get("target_ratio", 1.0),
                        "El objetivo de la relación o dosificación",
                    ),
                    mode=ConstraintMode(row.get("mode", ConstraintMode.MASS_RATIO)),
                    enabled=bool(row.get("enabled", True)),
                )
            )

        design = cls(parameters=params, components=components, ratio_constraints=constraints)
        design._migrate_legacy_parameters()
        return design

    def _migrate_legacy_parameters(self) -> None:
        """Convert v0.1/v0.2 hidden parameters into visible constraints."""

        cementitious = self.by_category(MaterialCategory.CEMENTITIOUS)
        weighted = [component for component in cementitious if component.blend_pct > 0]
        if len(weighted) == 2:
            total_weight = weighted[0].blend_pct + weighted[1].blend_pct
            pair_already_defined = any(
                constraint.mode in {
                    ConstraintMode.MASS_RATIO,
                    ConstraintMode.PERCENT_OF_B,
                    ConstraintMode.PERCENT_OF_PAIR,
                }
                and {constraint.numerator_uid, constraint.denominator_uid}
                == {weighted[0].uid, weighted[1].uid}
                for constraint in self.ratio_constraints
            )
            if total_weight > 0 and not pair_already_defined:
                self.ratio_constraints.append(
                    RatioConstraint(
                        numerator_uid=weighted[0].uid,
                        denominator_uid=weighted[1].uid,
                        target_ratio=100.0 * weighted[0].blend_pct / total_weight,
                        mode=ConstraintMode.PERCENT_OF_PAIR,
                    )
                )

        for component in self.by_category(MaterialCategory.ADMIXTURE):
            mode = component.effective_dosage_mode
            value = component.effective_dosage_value
            if value <= 0:
                continue
            if mode == DosageMode.PCT_CEMENTITIOUS:
                constraint_mode = ConstraintMode.PERCENT_OF_CEMENTITIOUS
            elif mode == DosageMode.ML_PER_100KG:
                constraint_mode = ConstraintMode.ML_PER_100KG_CEMENTITIOUS
            else:
                continue
            already_defined = any(
                constraint.numerator_uid == component.uid
                and constraint.mode in {
                    ConstraintMode.PERCENT_OF_CEMENTITIOUS,
                    ConstraintMode.ML_PER_100KG_CEMENTITIOUS,
                }
                for constraint in self.ratio_constraints
            )
            if not already_defined:
                self.ratio_constraints.append(
                    RatioConstraint(
                        numerator_uid=component.uid,
                        denominator_uid=None,
                        target_ratio=value,
                        mode=constraint_mode,
                    )
                )
