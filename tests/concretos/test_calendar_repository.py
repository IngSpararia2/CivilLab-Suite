from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

from concrete_mix_designer.data.calendar_repository import CalendarRepository
from concrete_mix_designer.domain.laboratory_models import SpecimenStatus, SpecimenType


def _initialize_base_schema(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE mix_designs (
                id INTEGER PRIMARY KEY,
                group_name TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE productions (
                id INTEGER PRIMARY KEY,
                design_id INTEGER NOT NULL REFERENCES mix_designs(id),
                design_name TEXT NOT NULL,
                batch_code TEXT NOT NULL
            );
            CREATE TABLE specimens (
                id INTEGER PRIMARY KEY,
                production_id INTEGER NOT NULL REFERENCES productions(id) ON DELETE CASCADE,
                specimen_code TEXT NOT NULL,
                specimen_type TEXT NOT NULL,
                target_age_days REAL NOT NULL,
                planned_test_at TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT ''
            );
            """
        )


def _iso(day: date, hour: int = 8) -> str:
    return datetime(
        day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc
    ).isoformat(timespec="seconds")


def test_calendar_checklist_is_independent_from_specimen_result_status(tmp_path):
    database = tmp_path / "calendar.sqlite3"
    _initialize_base_schema(database)
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO mix_designs (id, group_name) VALUES (1, 'Estructural')")
        connection.execute(
            "INSERT INTO productions (id, design_id, design_name, batch_code) "
            "VALUES (1, 1, 'Diseño 28 MPa', 'PROD-001')"
        )
        connection.executemany(
            """
            INSERT INTO specimens (
                id, production_id, specimen_code, specimen_type,
                target_age_days, planned_test_at, status, notes
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "C-7D-001", "cylinder", 7.0, _iso(today), "planned", "Ensayo principal"),
                (2, "V-28D-001", "beam", 28.0, _iso(today, 9), "tested", ""),
                (3, "C-3D-001", "cylinder", 3.0, _iso(yesterday), "planned", ""),
                (4, "C-14D-001", "cylinder", 14.0, _iso(tomorrow), "cancelled", ""),
            ],
        )

    repository = CalendarRepository(database)
    tasks = repository.list_tasks_for_date(today)
    assert len(tasks) == 2
    assert tasks[0].specimen_type == SpecimenType.CYLINDER
    assert tasks[0].specimen_status == SpecimenStatus.PLANNED
    assert tasks[0].is_pending
    assert tasks[1].is_completed

    repository.set_task_completed(1, True)
    completed = repository.list_tasks_for_date(today)[0]
    assert completed.checklist_completed
    assert completed.is_completed
    assert completed.specimen_status == SpecimenStatus.PLANNED

    summary = repository.operational_summary(today)
    assert summary.pending_today == 0
    assert summary.completed_today == 2
    assert summary.overdue == 1

    repository.set_task_completed(1, False)
    reopened = repository.list_tasks_for_date(today)[0]
    assert reopened.is_pending
    assert reopened.specimen_status == SpecimenStatus.PLANNED


def test_calendar_month_query_and_cascade_cleanup(tmp_path):
    database = tmp_path / "calendar.sqlite3"
    _initialize_base_schema(database)
    selected = date(2026, 7, 26)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("INSERT INTO mix_designs (id, group_name) VALUES (1, 'Pavimentos')")
        connection.execute(
            "INSERT INTO productions (id, design_id, design_name, batch_code) "
            "VALUES (1, 1, 'MR 4.5 MPa', 'PAV-001')"
        )
        connection.execute(
            """
            INSERT INTO specimens (
                id, production_id, specimen_code, specimen_type,
                target_age_days, planned_test_at, status, notes
            ) VALUES (10, 1, 'V-28D-001', 'beam', 28, ?, 'planned', '')
            """,
            (_iso(selected),),
        )

    repository = CalendarRepository(database)
    tasks = repository.list_month_tasks(2026, 7)
    assert len(tasks) == 1
    assert tasks[0].group_name == "Pavimentos"
    repository.set_task_completed(10, True)

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DELETE FROM specimens WHERE id = 10")
        remaining = connection.execute(
            "SELECT COUNT(*) FROM specimen_checklist WHERE specimen_id = 10"
        ).fetchone()[0]
    assert remaining == 0
