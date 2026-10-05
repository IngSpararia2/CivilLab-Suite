import sqlite3
from contextlib import closing
from datetime import date

import pytest

from civillab_suite.core.catalog import CatalogService
from civillab_suite.core.database import CoreDatabase
from civillab_suite.core.pie import PieService
from civillab_suite.core.results import SharedResultService
from civillab_suite.data_portability import DataPortabilityError, DataPortabilityService
from civillab_suite.demo import locations_for
from civillab_suite.storage import initialize_workspace
from concrete_mix_designer.data.database import MaterialRepository
from concrete_mix_designer.domain.models import Material, MaterialCategory


def shared_plan(path):
    initialize_workspace(path)
    core = CoreDatabase(path)
    catalog = CatalogService(core)
    assay = core.link_assay_to_module("Granulometría de aceptación", "concretos")
    assert core.link_assay_to_module("Granulometría de aceptación", "prefabricados") == assay
    material_type = next(t for t in catalog.list_material_types() if t.code == "COARSE_AGGREGATE")
    identity = catalog.create_material_object(
        material_type_id=material_type.id, code="AG-003", name="Grava 3/4"
    )
    concrete = MaterialRepository(path, seed=False).save(
        Material(None, "Grava 3/4", MaterialCategory.COARSE_AGGREGATE, 2.7, code="AG-003")
    )
    assert concrete.canonical_id == identity.id
    assert len(catalog.list_material_objects()) == 1
    pie = PieService(core)
    plan = pie.create_plan(
        assay_id=assay,
        module_ids=["concretos", "prefabricados"],
        responsible="Laboratorio",
        frequency="daily",
        start_date=date(2026, 1, 1),
        material_type_id=material_type.id,
        material_object_id=identity.id,
    )
    return core, pie, plan, assay, identity


def test_same_identity_two_areas_and_revoked_result_reopens_obligation(tmp_path):
    core, pie, plan, assay, identity = shared_plan(tmp_path / "core.sqlite3")
    service = SharedResultService(core)
    args = dict(
        assay_id=assay,
        material_object_id=identity.id,
        tested_on=date(2026, 10, 4),
        origin_module_id="concretos",
        source_type="report",
        source_id="1",
    )
    result = service.register(**args, status="VALID")
    assert len(service.satisfy_compatible_obligations(result.id)) == 1
    for module in ("concretos", "prefabricados"):
        occurrences = pie.list_occurrences(date(2026, 10, 4), date(2026, 10, 4), module)
        assert len(occurrences) == 1 and occurrences[0].is_completed
    assert service.register(**args, status="REJECTED").id == result.id
    assert service.satisfy_compatible_obligations(result.id) == []
    assert not pie.list_occurrences(date(2026, 10, 4), date(2026, 10, 4))[0].is_completed


def test_pie_rescheduling_across_projection_windows_is_not_duplicated(tmp_path):
    _, pie, plan, _, _ = shared_plan(tmp_path / "core.sqlite3")
    old, new = date(2026, 1, 2), date(2026, 10, 4)
    pie.reschedule_occurrence(plan.id, old, 1, new)
    assert not any(o.occurrence_start == old for o in pie.list_occurrences(old, old))
    selected = [o for o in pie.list_occurrences(new, new) if o.occurrence_start == old]
    assert len(selected) == 1 and selected[0].scheduled_date == new
    pie.reschedule_occurrence(plan.id, new, 1, date(2027, 1, 1))
    assert not any(o.occurrence_start == new for o in pie.list_occurrences(new, new))


def test_unified_replacement_failure_rolls_back_and_keeps_backup(tmp_path, monkeypatch):
    import civillab_suite.data_portability as portability

    path = tmp_path / "core.sqlite3"
    initialize_workspace(path)
    service = DataPortabilityService(locations_for(path))
    empty = service.export_data(tmp_path / "empty.civillab")
    repo = MaterialRepository(path, seed=False)
    repo.save(Material(None, "Conservar", MaterialCategory.OTHER, 2))
    real_replace = portability.os.replace

    def fail_incoming(source, target):
        if str(source).endswith(".incoming"):
            raise PermissionError("fallo simulado de publicación")
        return real_replace(source, target)

    monkeypatch.setattr(portability.os, "replace", fail_incoming)
    with pytest.raises(DataPortabilityError):
        service.import_data(empty)
    assert MaterialRepository(path, seed=False).list_all()[0].name == "Conservar"
    assert list((tmp_path / "backups").glob("antes-de-importar-*.civillab"))


def test_restore_checkpoints_old_wal_before_replacing(tmp_path):
    path = tmp_path / "core.sqlite3"
    initialize_workspace(path)
    service = DataPortabilityService(locations_for(path))
    package = service.export_data(tmp_path / "empty.civillab")
    # Keep a WAL connection open through export; release it before replacement.
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(
            "INSERT INTO concretos_design_groups(name,created_at) VALUES ('WAL', '2026-10-04')"
        )
        db.commit()
        backup = service.export_data(tmp_path / "wal.civillab")
    service.import_data(package)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM concretos_design_groups").fetchone()[0] == 0
    service.import_data(backup)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT name FROM concretos_design_groups").fetchone()[0] == "WAL"


def test_invalid_provisional_result_does_not_change_sample(tmp_path):
    from precon_lab.database import dispose_database_connections, session_scope, use_database
    from precon_lab.models import ProductionBatch
    from precon_lab.services import (
        create_product,
        create_production,
        reprogram_sample_set,
        save_provisional_result,
    )

    path = tmp_path / "core.sqlite3"
    initialize_workspace(path)
    use_database(path)
    try:
        with session_scope() as session:
            product = create_product(session, "Bloque", "B1", "BLOCK")
            summary = create_production(
                session,
                product_id=product.id,
                production_date=date(2026, 1, 1),
                lot_code="1",
                ages=[7],
            )
            sample = next(
                s
                for s in session.get(ProductionBatch, summary.batch_id).sample_sets
                if s.purpose == "COMPRESSION"
            )
            for invalid in (-1, float("nan"), float("inf"), None):
                with pytest.raises(ValueError):
                    save_provisional_result(
                        session,
                        sample_set_id=sample.id,
                        test_date=date(2026, 1, 8),
                        strength_avg=invalid,
                    )
            assert sample.status == "PLANNED"
            assert sample.result is None
            save_provisional_result(
                session, sample_set_id=sample.id, test_date=date(2026, 1, 8), strength_avg=12
            )
            assert sample.status == "TESTED"
            assert sample.tasks[-1].status == "DONE"
            with pytest.raises(ValueError):
                reprogram_sample_set(session, sample.id, date(2026, 1, 10))
    finally:
        dispose_database_connections()
