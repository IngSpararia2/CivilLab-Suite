from __future__ import annotations

from datetime import datetime, timedelta, timezone

from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
from concrete_mix_designer.domain.laboratory_models import (
    FreshTestType,
    SpecimenStatus,
    SpecimenType,
)
from concrete_mix_designer.domain.models import MixDesign


def test_fresh_test_can_be_edited_and_deleted(tmp_path):
    repository = LaboratoryRepository(tmp_path / "laboratory.sqlite3")
    design = repository.create_design(name="Mezcla", design=MixDesign())
    produced_at = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
    production = repository.create_production(
        design_id=design.id,
        produced_at=produced_at,
        batch_code="L-001",
        batch_volume_m3=0.10,
    )

    fresh = repository.add_fresh_test(
        production_id=production.id,
        test_type="slump",
        measured_at=produced_at + timedelta(minutes=5),
        slump_mm=101.6,
        notes="Lectura original",
    )
    edited = repository.update_fresh_test(
        test_id=fresh.id,
        test_type="spread",
        measured_at=produced_at + timedelta(minutes=30),
        spread_d1_mm=510.0,
        spread_d2_mm=500.0,
        notes="Dato corregido",
    )

    assert edited.test_type == FreshTestType.SPREAD
    assert edited.elapsed_minutes == 30
    assert edited.slump_mm is None
    assert edited.spread_average_mm == 505.0
    assert edited.notes == "Dato corregido"

    repository.delete_fresh_test(fresh.id)
    assert repository.get_fresh_test(fresh.id) is None


def test_hardened_result_can_be_deleted_and_specimen_returns_to_planned(tmp_path):
    repository = LaboratoryRepository(tmp_path / "laboratory.sqlite3")
    design = repository.create_design(name="Mezcla", design=MixDesign())
    produced_at = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
    production = repository.create_production(
        design_id=design.id,
        produced_at=produced_at,
        batch_code="L-002",
        batch_volume_m3=0.10,
        schedules=[(SpecimenType.CYLINDER, 7, 1)],
    )
    specimen = repository.list_specimens(production.id)[0]
    repository.upsert_compression_result(
        specimen_id=specimen.id,
        tested_at=produced_at + timedelta(days=7),
        diameter_mm=100.0,
        height_mm=200.0,
        mass_kg=3.8,
        max_load_kn=200.0,
    )

    assert repository.get_specimen(specimen.id).status == SpecimenStatus.TESTED
    assert repository.delete_specimen_result(specimen.id) is True
    assert repository.get_compression_result(specimen.id) is None
    assert repository.get_specimen(specimen.id).status == SpecimenStatus.PLANNED
    assert repository.delete_specimen_result(specimen.id) is False
