from __future__ import annotations

import pytest

from concrete_mix_designer.data.database import MaterialRepository
from concrete_mix_designer.domain.models import DosageMode, Material, MaterialCategory


def test_material_repository_accepts_text_enums_for_create_and_edit(tmp_path):
    repository = MaterialRepository(tmp_path / "materials.sqlite3")

    material = Material(
        id=None,
        name="Arena de prueba",
        category="fine_aggregate",
        specific_gravity=2.61,
        absorption_pct=1.8,
        moisture_pct=3.2,
        dosage_mode="manual_kg",
    )
    saved = repository.save(material)

    assert saved.id is not None
    assert saved.category == MaterialCategory.FINE_AGGREGATE
    assert saved.dosage_mode == DosageMode.MANUAL_KG

    saved.name = "Arena de prueba editada"
    saved.category = "coarse_aggregate"
    saved.dosage_mode = "pct_cementitious"
    repository.save(saved)

    stored = repository.get(saved.id)
    assert stored is not None
    assert stored.name == "Arena de prueba editada"
    assert stored.category == MaterialCategory.COARSE_AGGREGATE
    assert stored.dosage_mode == DosageMode.PCT_CEMENTITIOUS


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_material_repository_rejects_non_finite_physical_values(tmp_path, value):
    repository = MaterialRepository(tmp_path / "materials.sqlite3")
    material = Material(
        id=None,
        name="Material inválido",
        category=MaterialCategory.OTHER,
        specific_gravity=value,
    )

    with pytest.raises(ValueError, match="número finito"):
        repository.save(material)


def test_material_repository_rejects_update_of_missing_material(tmp_path):
    repository = MaterialRepository(tmp_path / "materials.sqlite3")
    material = Material(
        id=999_999,
        name="Material inexistente",
        category=MaterialCategory.OTHER,
        specific_gravity=1.0,
    )

    with pytest.raises(ValueError, match="no existe"):
        repository.save(material)


def test_app_state_uses_renamed_seed_material_in_default_design(tmp_path):
    from concrete_mix_designer.services.app_state import AppState

    repository = MaterialRepository(tmp_path / "renamed-seed.sqlite3")
    cement = next(
        material
        for material in repository.list_all()
        if material.name == "Cemento Portland Tipo I"
    )
    cement.name = "Cemento de la planta"
    cement.specific_gravity = 3.08
    repository.save(cement)

    state = AppState(repository)
    restored_component = next(
        component for component in state.design.components if component.material.id == cement.id
    )

    assert restored_component.material.name == "Cemento de la planta"
    assert restored_component.material.specific_gravity == 3.08
    assert state.design.ratio_constraints[0].numerator_uid == restored_component.uid


def test_app_state_opens_when_an_entire_default_category_was_reclassified(tmp_path):
    from concrete_mix_designer.services.app_state import AppState

    repository = MaterialRepository(tmp_path / "missing-category.sqlite3")
    for material in repository.list_all():
        if material.category == MaterialCategory.CEMENTITIOUS:
            material.category = MaterialCategory.OTHER
            repository.save(material)

    state = AppState(repository)

    assert not state.design.by_category(MaterialCategory.CEMENTITIOUS)
    assert state.design.ratio_constraints == []
