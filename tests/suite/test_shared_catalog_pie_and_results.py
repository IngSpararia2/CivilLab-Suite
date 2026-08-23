from __future__ import annotations

from datetime import date

from civillab_suite.core.catalog import CatalogService
from civillab_suite.core.database import CoreDatabase, _normalized
from civillab_suite.core.pie import PieFrequency, PieService
from civillab_suite.core.results import SharedResultService
from civillab_suite.registry import create_default_registry


def _ready(tmp_path):
    database = CoreDatabase(tmp_path / "core.sqlite3")
    database.initialize()
    database.sync_modules(create_default_registry().all())
    return database


def _material_type(database: CoreDatabase, code: str = "COARSE_AGGREGATE") -> int:
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO material_types (code, canonical_name, normalized_name)
            VALUES (?, ?, ?)
            """,
            (code, "Agregado grueso", _normalized("Agregado grueso")),
        )
        return int(connection.execute(
            "SELECT id FROM material_types WHERE code = ?", (code,)
        ).fetchone()[0])


def test_catalog_filters_one_shared_assay_by_area_without_duplication(tmp_path):
    database = _ready(tmp_path)
    assay_id = database.link_assay_to_module("Granulometría", "concretos")
    assert database.link_assay_to_module("Granulometría", "prefabricados") == assay_id
    database.link_assay_to_module("CBR", "suelos")
    service = CatalogService(database)

    assert [item.name for item in service.list_assays("concretos")] == ["Granulometría"]
    assert [item.name for item in service.list_assays("prefabricados")] == ["Granulometría"]
    assert [item.name for item in service.list_assays("suelos")] == ["CBR"]
    assert database.counts()["assays"] == 2


def test_shared_pie_crud_and_month_end_projection_are_deterministic(tmp_path):
    database = _ready(tmp_path)
    assay_id = database.link_assay_to_module("Granulometría", "concretos")
    service = PieService(database)
    saved = service.create_plan(
        assay_id=assay_id,
        module_ids=("concretos",),
        responsible="Laboratorista",
        frequency=PieFrequency.CUSTOM_MONTHS,
        interval=1,
        start_date=date(2024, 1, 31),
    )

    assert [item.scheduled_date for item in service.list_occurrences(
        date(2024, 2, 1), date(2024, 2, 29), "concretos"
    )] == [date(2024, 2, 29)]

    saved.responsible = "Jefe de laboratorio"
    saved.module_ids = ("concretos", "prefabricados")
    updated = service.save_plan(saved)
    assert updated.responsible == "Jefe de laboratorio"
    assert updated.module_ids == ("concretos", "prefabricados")
    assert service.deactivate_plan(int(updated.id))
    assert service.list_plans() == []
    assert service.list_plans(include_inactive=True)[0].active is False


def test_one_shared_result_can_satisfy_two_module_obligations(tmp_path):
    database = _ready(tmp_path)
    assay_id = database.link_assay_to_module("Granulometría", "concretos")
    database.link_assay_to_module("Granulometría", "prefabricados")
    material_type_id = _material_type(database)
    material = CatalogService(database).create_material_object(
        material_type_id=material_type_id,
        code="AG-003",
        name="Grava 3/4",
        supplier_source="Fuente X",
    )
    pie = PieService(database)
    for module_id in ("concretos", "prefabricados"):
        pie.create_plan(
            assay_id=assay_id,
            material_type_id=material_type_id,
            material_object_id=material.id,
            module_ids=(module_id,),
            responsible="Laboratorio",
            frequency=PieFrequency.MONTHLY,
            start_date=date(2026, 8, 1),
        )

    results = SharedResultService(database, pie)
    result = results.register(
        assay_id=assay_id,
        material_object_id=material.id,
        tested_on=date(2026, 8, 5),
        origin_module_id="prefabricados",
        source_type="test_result",
        source_id="51",
        status="VALID",
        report_reference="INF-005",
    )
    satisfactions = results.satisfy_compatible_obligations(result.id)

    assert len(satisfactions) == 2
    assert {item.occurrence_start for item in satisfactions} == {date(2026, 8, 1)}
    counts = database.counts()
    assert counts["shared_results"] == 1
    assert counts["pie_result_satisfactions"] == 2


def test_checking_pie_activity_never_creates_a_result(tmp_path):
    database = _ready(tmp_path)
    assay_id = database.link_assay_to_module("Granulometría", "concretos")
    pie = PieService(database)
    plan = pie.create_plan(
        assay_id=assay_id,
        module_ids=("concretos",),
        responsible="Laboratorio",
        frequency=PieFrequency.DAILY,
        start_date=date(2026, 8, 5),
    )
    pie.set_occurrence_completed(int(plan.id), date(2026, 8, 5), 1, True)

    assert database.counts()["shared_results"] == 0
