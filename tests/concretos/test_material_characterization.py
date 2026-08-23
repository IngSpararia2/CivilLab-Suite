from pathlib import Path

import pytest

from concrete_mix_designer.data.database import MaterialRepository
from concrete_mix_designer.domain.metadata_models import (
    GradationPoint,
    MaterialCharacterization,
)
from concrete_mix_designer.domain.models import DosageMode, Material, MaterialCategory


def test_aggregate_characterization_and_gradation_roundtrip(tmp_path: Path) -> None:
    repository = MaterialRepository(tmp_path / "materials.sqlite3")
    material = repository.save(
        Material(
            id=None,
            name="Arena de prueba",
            category=MaterialCategory.FINE_AGGREGATE,
            specific_gravity=2.61,
            absorption_pct=1.4,
            moisture_pct=3.2,
            dosage_mode=DosageMode.MANUAL_KG,
        )
    )
    characterization = MaterialCharacterization(
        supplier="Cantera Norte",
        source="Frente 2",
        specific_gravity_dry=2.58,
        specific_gravity_ssd=2.61,
        fineness_modulus=2.72,
        notes="Muestra compuesta",
        gradation=[
            GradationPoint("No. 4", 4.75, 96.0, 0),
            GradationPoint("No. 8", 2.36, 82.0, 1),
            GradationPoint("No. 16", 1.18, 63.0, 2),
            GradationPoint("No. 30", 0.60, 39.0, 3),
            GradationPoint("No. 50", 0.30, 16.0, 4),
            GradationPoint("No. 100", 0.15, 4.0, 5),
        ],
    )
    saved = repository.save_characterization(material.id, characterization)
    assert saved.supplier == "Cantera Norte"
    assert saved.fineness_modulus == 2.72
    assert [point.passing_pct for point in saved.gradation] == [96, 82, 63, 39, 16, 4]


def test_deleting_material_removes_characterization(tmp_path: Path) -> None:
    repository = MaterialRepository(tmp_path / "materials.sqlite3")
    material = repository.save(
        Material(
            id=None,
            name="Grava temporal",
            category=MaterialCategory.COARSE_AGGREGATE,
            specific_gravity=2.70,
            dosage_mode=DosageMode.MANUAL_KG,
        )
    )
    repository.save_characterization(
        material.id,
        MaterialCharacterization(
            compacted_unit_weight_kg_m3=1570.0,
            gradation=[GradationPoint("3/4 in", 19.0, 95.0)],
        ),
    )
    repository.delete(material.id)
    assert repository.get(material.id) is None


def test_characterization_rejects_non_finite_gradation(tmp_path: Path) -> None:
    repository = MaterialRepository(tmp_path / "materials.sqlite3")
    material = repository.save(
        Material(
            id=None,
            name="Arena no finita",
            category=MaterialCategory.FINE_AGGREGATE,
            specific_gravity=2.60,
        )
    )

    with pytest.raises(ValueError, match="número finito"):
        repository.save_characterization(
            material.id,
            MaterialCharacterization(
                gradation=[GradationPoint("No. 4", 4.75, float("nan"))]
            ),
        )
