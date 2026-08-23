from datetime import date, timedelta

from sqlalchemy import select

from precon_lab.models import Product, SampleSet, WorkflowTask
from precon_lab.services import create_production, reprogram_sample_set


def test_block_production_creates_absorption_and_compression(session):
    product = session.scalar(select(Product).where(Product.category == "BLOCK"))
    production_day = date(2026, 7, 24)

    summary = create_production(
        session,
        product_id=product.id,
        production_date=production_day,
        lot_code="L-001",
        ages=[3, 7, 14, 28],
    )
    session.commit()

    assert summary.sample_set_count == 5
    assert summary.specimen_count == 15
    assert summary.task_count == 7

    sets = list(session.scalars(select(SampleSet).order_by(SampleSet.id)))
    absorption = sets[0]
    assert absorption.purpose == "ABSORPTION"
    assert [task.scheduled_date for task in absorption.tasks] == [
        production_day,
        production_day + timedelta(days=1),
        production_day + timedelta(days=2),
    ]

    compression = next(item for item in sets if item.target_age_days == 28)
    assert compression.planned_test_date == production_day + timedelta(days=28)
    assert compression.specimen_count == 3


def test_flexure_production_schedules_preparation_backwards(session):
    product = session.scalar(select(Product).where(Product.category == "FLEXURE"))
    production_day = date(2026, 7, 24)

    summary = create_production(
        session,
        product_id=product.id,
        production_date=production_day,
        lot_code="F-001",
        ages=[3, 7],
    )
    session.commit()

    assert summary.sample_set_count == 2
    assert summary.specimen_count == 10
    assert summary.task_count == 8

    set_7 = session.scalar(select(SampleSet).where(SampleSet.target_age_days == 7))
    dates = [task.scheduled_date for task in sorted(set_7.tasks, key=lambda item: item.sequence)]
    assert dates == [
        production_day + timedelta(days=4),
        production_day + timedelta(days=5),
        production_day + timedelta(days=6),
        production_day + timedelta(days=7),
    ]


def test_reprogram_moves_only_pending_tasks(session):
    product = session.scalar(select(Product).where(Product.category == "FLEXURE"))
    production_day = date(2026, 7, 24)
    create_production(
        session,
        product_id=product.id,
        production_date=production_day,
        lot_code="F-002",
        ages=[7],
    )
    session.commit()

    sample_set = session.scalar(select(SampleSet))
    first_task = sorted(sample_set.tasks, key=lambda item: item.sequence)[0]
    first_task.status = "DONE"
    original_first_date = first_task.scheduled_date
    original_pending_dates = {
        task.id: task.scheduled_date for task in sample_set.tasks if task.status != "DONE"
    }

    reprogram_sample_set(session, sample_set.id, sample_set.planned_test_date + timedelta(days=2))
    session.commit()

    assert first_task.scheduled_date == original_first_date
    for task in sample_set.tasks:
        if task.id in original_pending_dates:
            assert task.scheduled_date == original_pending_dates[task.id] + timedelta(days=2)
            assert task.original_scheduled_date != task.scheduled_date
