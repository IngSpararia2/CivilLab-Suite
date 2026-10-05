from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SpecimenType(StrEnum):
    CYLINDER = "cylinder"
    BEAM = "beam"


class SpecimenStatus(StrEnum):
    PLANNED = "planned"
    TESTED = "tested"
    CANCELLED = "cancelled"


class FreshTestType(StrEnum):
    SLUMP = "slump"
    SPREAD = "spread"


SPECIMEN_TYPE_LABELS = {
    SpecimenType.CYLINDER: "Cilindro",
    SpecimenType.BEAM: "Vigueta",
}

SPECIMEN_STATUS_LABELS = {
    SpecimenStatus.PLANNED: "Programado",
    SpecimenStatus.TESTED: "Ensayado",
    SpecimenStatus.CANCELLED: "Cancelado",
}

FRESH_TEST_TYPE_LABELS = {
    FreshTestType.SLUMP: "Asentamiento",
    FreshTestType.SPREAD: "Esparcimiento",
}


@dataclass(slots=True)
class SavedDesignRecord:
    id: int
    family_uid: str
    revision: int
    name: str
    group_name: str
    description: str
    source_design_id: int | None
    design_json: str
    created_at: datetime
    production_count: int = 0
    archived: bool = False


@dataclass(slots=True)
class ProductionRecord:
    id: int
    design_id: int
    design_name: str
    design_revision: int
    design_json_snapshot: str
    produced_at: datetime
    batch_code: str
    batch_volume_m3: float
    notes: str
    created_at: datetime
    specimen_count: int = 0
    tested_specimen_count: int = 0


@dataclass(slots=True)
class SpecimenRecord:
    id: int
    production_id: int
    specimen_code: str
    specimen_type: SpecimenType
    target_age_days: float
    planned_test_at: datetime
    status: SpecimenStatus
    notes: str = ""


@dataclass(slots=True)
class FreshTestRecord:
    id: int
    production_id: int
    test_type: FreshTestType
    measured_at: datetime
    elapsed_minutes: int
    slump_mm: float | None
    spread_d1_mm: float | None
    spread_d2_mm: float | None
    concrete_temperature_c: float | None
    air_content_pct: float | None
    unit_weight_kg_m3: float | None
    notes: str

    @property
    def spread_average_mm(self) -> float | None:
        values = [value for value in (self.spread_d1_mm, self.spread_d2_mm) if value is not None]
        return sum(values) / len(values) if values else None


@dataclass(slots=True)
class CompressionResultRecord:
    id: int
    specimen_id: int
    tested_at: datetime
    actual_age_days: float
    diameter_mm: float
    height_mm: float | None
    mass_kg: float | None
    max_load_kn: float
    strength_mpa: float
    failure_type: str
    machine: str
    technician: str
    notes: str


@dataclass(slots=True)
class FlexuralResultRecord:
    id: int
    specimen_id: int
    tested_at: datetime
    actual_age_days: float
    width_mm: float
    depth_mm: float
    span_mm: float
    fracture_distance_mm: float | None
    max_load_kn: float
    modulus_of_rupture_mpa: float
    failure_type: str
    machine: str
    technician: str
    notes: str


@dataclass(slots=True)
class DesignStatisticsRow:
    specimen_type: SpecimenType
    target_age_days: float
    result_count: int
    average_mpa: float
    minimum_mpa: float
    maximum_mpa: float
    standard_deviation_mpa: float | None
