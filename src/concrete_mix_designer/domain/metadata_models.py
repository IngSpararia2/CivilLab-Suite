from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any


class ConsistencyType(StrEnum):
    SLUMP = "slump"
    SPREAD = "spread"


class ConcreteApplication(StrEnum):
    STRUCTURAL = "structural"
    PAVEMENT = "pavement"
    PRECAST = "precast"
    SELF_CONSOLIDATING = "self_consolidating"
    MASS = "mass"
    GROUT = "grout"
    OTHER = "other"


class StrengthBasis(StrEnum):
    COMPRESSION = "compression"
    FLEXURAL = "flexural"
    BOTH = "both"


CONSISTENCY_LABELS = {
    ConsistencyType.SLUMP: "Asentamiento",
    ConsistencyType.SPREAD: "Esparcimiento",
}

APPLICATION_LABELS = {
    ConcreteApplication.STRUCTURAL: "Concreto estructural",
    ConcreteApplication.PAVEMENT: "Concreto para pavimento",
    ConcreteApplication.PRECAST: "Concreto prefabricado",
    ConcreteApplication.SELF_CONSOLIDATING: "Concreto autocompactante",
    ConcreteApplication.MASS: "Concreto masivo",
    ConcreteApplication.GROUT: "Grout / relleno fluido",
    ConcreteApplication.OTHER: "Otro",
}

STRENGTH_BASIS_LABELS = {
    StrengthBasis.COMPRESSION: "Resistencia a compresión",
    StrengthBasis.FLEXURAL: "Módulo de rotura",
    StrengthBasis.BOTH: "Compresión y módulo de rotura",
}


@dataclass(slots=True)
class GradationPoint:
    sieve_label: str
    opening_mm: float
    passing_pct: float | None = None
    sort_order: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GradationPoint":
        value = payload.get("passing_pct")
        return cls(
            sieve_label=str(payload.get("sieve_label", "")).strip(),
            opening_mm=_finite_float(
                payload.get("opening_mm", 0.0), "La abertura del tamiz"
            ),
            passing_pct=_optional_float(value, "El porcentaje pasante"),
            sort_order=int(payload.get("sort_order", 0)),
        )


@dataclass(slots=True)
class MaterialCharacterization:
    material_id: int | None = None
    supplier: str = ""
    source: str = ""
    lot_code: str = ""
    characterization_standard: str = ""
    cement_type: str = ""
    specific_gravity_dry: float | None = None
    specific_gravity_ssd: float | None = None
    compacted_unit_weight_kg_m3: float | None = None
    fineness_modulus: float | None = None
    nominal_max_size_mm: float | None = None
    aggregate_shape: str = ""
    aggregate_texture: str = ""
    admixture_density_kg_l: float | None = None
    water_reduction_pct: float | None = None
    recommended_dosage_pct: float | None = None
    notes: str = ""
    gradation: list[GradationPoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DesignSpecification:
    design_id: int | None = None
    application_type: ConcreteApplication = ConcreteApplication.STRUCTURAL
    strength_basis: StrengthBasis = StrengthBasis.COMPRESSION
    expected_compressive_strength_mpa: float | None = None
    compressive_strength_age_days: float = 28.0
    expected_modulus_rupture_mpa: float | None = None
    modulus_rupture_age_days: float = 28.0
    consistency_type: ConsistencyType = ConsistencyType.SLUMP
    target_slump_mm: float | None = None
    target_spread_mm: float | None = None
    initial_set_minutes: int | None = None
    accelerated: bool = False
    accelerated_age_days: float | None = None
    nominal_max_size_mm: float | None = None
    exposure_condition: str = ""
    air_entrained: bool = False
    placement_method: str = ""
    keywords: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["application_type"] = self.application_type.value
        payload["strength_basis"] = self.strength_basis.value
        payload["consistency_type"] = self.consistency_type.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "DesignSpecification":
        data = dict(payload or {})
        return cls(
            design_id=_optional_int(data.get("design_id")),
            application_type=ConcreteApplication(
                data.get("application_type", ConcreteApplication.STRUCTURAL)
            ),
            strength_basis=StrengthBasis(
                data.get("strength_basis", StrengthBasis.COMPRESSION)
            ),
            expected_compressive_strength_mpa=_optional_float(
                data.get("expected_compressive_strength_mpa")
            ),
            compressive_strength_age_days=_finite_float(
                data.get("compressive_strength_age_days", 28.0),
                "La edad de resistencia a compresión",
            ),
            expected_modulus_rupture_mpa=_optional_float(
                data.get("expected_modulus_rupture_mpa")
            ),
            modulus_rupture_age_days=_finite_float(
                data.get("modulus_rupture_age_days", 28.0),
                "La edad del módulo de rotura",
            ),
            consistency_type=ConsistencyType(
                data.get("consistency_type", ConsistencyType.SLUMP)
            ),
            target_slump_mm=_optional_float(data.get("target_slump_mm")),
            target_spread_mm=_optional_float(data.get("target_spread_mm")),
            initial_set_minutes=_optional_int(data.get("initial_set_minutes")),
            accelerated=bool(data.get("accelerated", False)),
            accelerated_age_days=_optional_float(data.get("accelerated_age_days")),
            nominal_max_size_mm=_optional_float(data.get("nominal_max_size_mm")),
            exposure_condition=str(data.get("exposure_condition", "")),
            air_entrained=bool(data.get("air_entrained", False)),
            placement_method=str(data.get("placement_method", "")),
            keywords=str(data.get("keywords", "")),
        )

    @classmethod
    def from_mix_design(cls, design) -> "DesignSpecification":
        params = design.parameters
        return cls(
            expected_compressive_strength_mpa=float(params.fc_mpa),
            compressive_strength_age_days=28.0,
            consistency_type=ConsistencyType.SLUMP,
            target_slump_mm=float(params.slump_mm),
            nominal_max_size_mm=float(params.nominal_max_size_mm),
        )

    @property
    def primary_strength_mpa(self) -> float | None:
        if self.strength_basis == StrengthBasis.FLEXURAL:
            return self.expected_modulus_rupture_mpa
        return self.expected_compressive_strength_mpa

    @property
    def consistency_value_mm(self) -> float | None:
        return (
            self.target_spread_mm
            if self.consistency_type == ConsistencyType.SPREAD
            else self.target_slump_mm
        )


def _finite_float(value: object, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} debe ser un número finito.") from error
    if not isfinite(numeric):
        raise ValueError(f"{label} debe ser un número finito.")
    return numeric


def _optional_float(value: object, label: str = "El valor") -> float | None:
    return None if value in (None, "") else _finite_float(value, label)


def _optional_int(value: object) -> int | None:
    return None if value in (None, "") else int(value)
