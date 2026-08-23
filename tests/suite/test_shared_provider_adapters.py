from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select

from civillab_suite.modules.prefabricados.scheduling import PrefabricadosScheduleProvider


def test_prefabricados_provider_projects_and_updates_without_copying_source(
    monkeypatch, tmp_path
):
    from precon_lab import database
    from precon_lab.models import Product, SampleSet, WorkflowTask
    from precon_lab.services import create_production

    monkeypatch.setenv("PRECON_LAB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_SessionFactory", None)
    database.initialize_database()
    production_day = date(2026, 8, 1)
    with database.session_scope() as session:
        product = session.scalar(select(Product).where(Product.category == "FLEXURE"))
        create_production(
            session,
            product_id=product.id,
            production_date=production_day,
            lot_code="PROVIDER-001",
            ages=[7],
        )
        source_count = int(session.scalar(select(func.count()).select_from(WorkflowTask)))

    provider = PrefabricadosScheduleProvider()
    activities = provider.activities_between(production_day, production_day + timedelta(days=10))
    assert len(activities) == source_count
    with database.session_scope() as session:
        assert int(session.scalar(select(func.count()).select_from(WorkflowTask))) == source_count

    activity = activities[-1]
    provider.set_completed(activity, True)
    assert provider.activities_between(activity.scheduled_date, activity.scheduled_date)[0].completed
    provider.set_completed(activity, False)

    new_test_date = date.fromisoformat(dict(activity.metadata)["reschedule_reference"]) + timedelta(days=2)
    provider.reschedule(activity, new_test_date)
    with database.session_scope() as session:
        sample_set = session.get(SampleSet, int(dict(activity.metadata)["sample_set_id"]))
        assert sample_set.planned_test_date == new_test_date
