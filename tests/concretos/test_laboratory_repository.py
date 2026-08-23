from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
from concrete_mix_designer.domain.laboratory_models import FreshTestType, SpecimenType
from concrete_mix_designer.domain.models import MixDesign, MixParameters


def test_design_versions_production_and_results(tmp_path):
    repository = LaboratoryRepository(tmp_path / "app.sqlite3")
    design = MixDesign(parameters=MixParameters(fc_mpa=28.0, target_w_cm=0.50))

    revision_1 = repository.create_design(
        name="Mezcla 28 MPa", design=design, group_name="Estructurales"
    )
    design.parameters.target_w_cm = 0.48
    revision_2 = repository.create_design(
        name="Mezcla 28 MPa ajustada",
        design=design,
        source_design_id=revision_1.id,
    )

    assert revision_1.group_name == "Estructurales"
    assert revision_1.family_uid == revision_2.family_uid
    assert revision_2.revision == 2

    produced_at = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
    production = repository.create_production(
        design_id=revision_2.id,
        produced_at=produced_at,
        batch_code="LOT-001",
        batch_volume_m3=0.25,
        schedules=[
            (SpecimenType.CYLINDER, 3, 2),
            (SpecimenType.CYLINDER, 28, 2),
            ("beam", 28, 1),
        ],
    )

    specimens = repository.list_specimens(production.id)
    assert len(specimens) == 5
    assert specimens[0].planned_test_at >= produced_at + timedelta(days=3)

    fresh = repository.add_fresh_test(
        production_id=production.id,
        test_type="slump",
        measured_at=produced_at + timedelta(minutes=30),
        slump_mm=95,
    )
    assert fresh.elapsed_minutes == 30

    cylinder = next(
        item
        for item in specimens
        if item.specimen_type == SpecimenType.CYLINDER and item.target_age_days == 3
    )
    result = repository.upsert_compression_result(
        specimen_id=cylinder.id,
        tested_at=produced_at + timedelta(days=3),
        diameter_mm=100,
        height_mm=200,
        mass_kg=3.8,
        max_load_kn=180,
    )
    assert result.strength_mpa == pytest.approx(22.918, rel=1e-3)

    stats = repository.design_statistics(revision_2.id)
    assert len(stats) == 1
    assert stats[0].result_count == 1
    assert stats[0].average_mpa == pytest.approx(result.strength_mpa)


def test_production_keeps_immutable_design_snapshot(tmp_path):
    repository = LaboratoryRepository(tmp_path / "app.sqlite3")
    design = MixDesign(parameters=MixParameters(fc_mpa=21.0))
    saved = repository.create_design(name="Original", design=design)
    production = repository.create_production(
        design_id=saved.id,
        produced_at=datetime.now(timezone.utc),
        batch_code="P-01",
        batch_volume_m3=1.0,
    )

    design.parameters.fc_mpa = 35.0
    repository.create_design(
        name="Revisión",
        design=design,
        source_design_id=saved.id,
    )

    stored_production = repository.get_production(production.id)
    assert stored_production is not None
    assert '"fc_mpa":21.0' in stored_production.design_json_snapshot


def test_flexural_result_and_archived_design_visibility(tmp_path):
    repository = LaboratoryRepository(tmp_path / "app.sqlite3")
    design = MixDesign(parameters=MixParameters(fc_mpa=35.0))
    saved = repository.create_design(name="Pavimento 35 MPa", design=design)
    produced_at = datetime(2026, 7, 25, 9, 30, tzinfo=timezone.utc)
    production = repository.create_production(
        design_id=saved.id,
        produced_at=produced_at,
        batch_code="VIG-001",
        batch_volume_m3=0.50,
        schedules=[(SpecimenType.BEAM, 28, 1)],
    )
    beam = repository.list_specimens(production.id)[0]
    result = repository.upsert_flexural_result(
        specimen_id=beam.id,
        tested_at=produced_at + timedelta(days=28),
        width_mm=150,
        depth_mm=150,
        span_mm=450,
        fracture_distance_mm=220,
        max_load_kn=30,
    )
    assert result.modulus_of_rupture_mpa == pytest.approx(4.0)

    repository.archive_design(saved.id)
    assert repository.list_designs() == []
    assert repository.list_designs(include_archived=True)[0].id == saved.id
    assert repository.get_production(production.id) is not None


def test_modulus_of_rupture_uses_fracture_location_rules():
    calculate = LaboratoryRepository.calculate_modulus_of_rupture

    middle_third = calculate(30.0, 450.0, 150.0, 150.0, 220.0)
    outer_five_percent = calculate(30.0, 450.0, 150.0, 150.0, 140.0)

    assert middle_third == pytest.approx(4.0)
    assert outer_five_percent == pytest.approx(3.7333333333)
    with pytest.raises(ValueError, match="descartarse"):
        calculate(30.0, 450.0, 150.0, 150.0, 120.0)
    with pytest.raises(ValueError, match="mitad de la luz"):
        calculate(30.0, 450.0, 150.0, 150.0, 230.0)


def test_repository_rejects_non_finite_design_and_production_values(tmp_path):
    repository = LaboratoryRepository(tmp_path / "app.sqlite3")
    invalid_design = MixDesign(parameters=MixParameters(target_w_cm=float("nan")))
    with pytest.raises(ValueError, match="no finitos"):
        repository.create_design(name="Diseño inválido", design=invalid_design)

    saved = repository.create_design(name="Diseño válido", design=MixDesign())
    with pytest.raises(ValueError, match="número finito"):
        repository.create_production(
            design_id=saved.id,
            produced_at=datetime.now(timezone.utc),
            batch_code="NAN-001",
            batch_volume_m3=float("nan"),
        )


def test_repository_rejects_measurements_before_production_and_invalid_loads(tmp_path):
    repository = LaboratoryRepository(tmp_path / "app.sqlite3")
    saved = repository.create_design(name="Control temporal", design=MixDesign())
    produced_at = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
    production = repository.create_production(
        design_id=saved.id,
        produced_at=produced_at,
        batch_code="TIME-001",
        batch_volume_m3=0.25,
        schedules=[(SpecimenType.CYLINDER, 7, 1)],
    )

    with pytest.raises(ValueError, match="anterior"):
        repository.add_fresh_test(
            production_id=production.id,
            test_type=FreshTestType.SLUMP,
            measured_at=produced_at - timedelta(minutes=1),
            slump_mm=90.0,
        )

    specimen = repository.list_specimens(production.id)[0]
    with pytest.raises(ValueError, match="número finito"):
        repository.upsert_compression_result(
            specimen_id=specimen.id,
            tested_at=produced_at + timedelta(days=7),
            diameter_mm=100.0,
            height_mm=200.0,
            mass_kg=3.8,
            max_load_kn=float("inf"),
        )
    with pytest.raises(ValueError, match="anterior"):
        repository.upsert_compression_result(
            specimen_id=specimen.id,
            tested_at=produced_at - timedelta(seconds=1),
            diameter_mm=100.0,
            height_mm=200.0,
            mass_kg=3.8,
            max_load_kn=180.0,
        )


def test_grouped_saves_are_independent_records(tmp_path):
    repository = LaboratoryRepository(tmp_path / "app.sqlite3")
    first = repository.create_design(
        name="Mezcla base", group_name="Pavimento MR", design=MixDesign()
    )
    second = repository.create_design(
        name="Mezcla con ajuste de arena",
        group_name="Pavimento MR",
        design=MixDesign(),
    )

    assert first.id != second.id
    assert first.revision == 1
    assert second.revision == 1
    assert first.group_name == second.group_name == "Pavimento MR"
    assert first.family_uid != second.family_uid


def test_existing_v04_database_is_migrated_with_group_column(tmp_path):
    import sqlite3

    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE mix_designs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_uid TEXT NOT NULL,
                revision INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                source_design_id INTEGER,
                design_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                UNIQUE(family_uid, revision)
            )
            """
        )

    repository = LaboratoryRepository(database_path)
    saved = repository.create_design(name="Migrada", group_name="Grupo A", design=MixDesign())
    assert saved.group_name == "Grupo A"
