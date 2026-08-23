from datetime import datetime
from pathlib import Path

from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
from concrete_mix_designer.domain.metadata_models import (
    ConcreteApplication,
    ConsistencyType,
    DesignSpecification,
    StrengthBasis,
)


class DummyDesign:
    def to_dict(self):
        return {
            "parameters": {
                "fc_mpa": 35.0,
                "slump_mm": 100.0,
                "nominal_max_size_mm": 19.0,
                "target_w_cm": 0.45,
            },
            "components": [],
            "ratio_constraints": [],
        }


def test_specification_is_saved_and_snapshotted_in_production(tmp_path: Path) -> None:
    repository = LaboratoryRepository(tmp_path / "laboratory.sqlite3")
    specification = DesignSpecification(
        application_type=ConcreteApplication.PAVEMENT,
        strength_basis=StrengthBasis.BOTH,
        expected_compressive_strength_mpa=35.0,
        expected_modulus_rupture_mpa=4.2,
        consistency_type=ConsistencyType.SLUMP,
        target_slump_mm=75.0,
        initial_set_minutes=120,
        accelerated=True,
        accelerated_age_days=3.0,
        nominal_max_size_mm=19.0,
        keywords="pavimento, MR 4.2",
    )
    design = repository.create_design(
        name="Pavimento MR 4.2",
        group_name="Pavimentos",
        design=DummyDesign(),
        specification=specification,
    )
    stored = repository.get_design_specification(design.id)
    assert stored.application_type == ConcreteApplication.PAVEMENT
    assert stored.expected_modulus_rupture_mpa == 4.2
    production = repository.create_production(
        design_id=design.id,
        produced_at=datetime.now().astimezone(),
        batch_code="P-001",
        batch_volume_m3=6.5,
    )
    snapshot = repository.get_production_specification(production.id)
    assert snapshot.accelerated is True
    assert snapshot.accelerated_age_days == 3.0
    assert snapshot.target_slump_mm == 75.0
