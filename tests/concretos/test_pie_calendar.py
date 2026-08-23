from __future__ import annotations

import os
import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from concrete_mix_designer.data.calendar_repository import CalendarRepository
from concrete_mix_designer.domain.pie_models import PieFrequency, PieInspectionPlan


def _plan(
    *,
    name: str = "Ensayo de control",
    frequency: PieFrequency = PieFrequency.DAILY,
    interval: int = 1,
    start: date = date(2026, 1, 1),
    steps: tuple[str, ...] = ("Ejecutar ensayo",),
) -> PieInspectionPlan:
    return PieInspectionPlan(
        name=name,
        frequency=frequency,
        interval=interval,
        start_date=start,
        duration_days=len(steps),
        steps=list(steps),
    )


def _initialize_calendar_schema(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
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


def test_pie_plan_crud_steps_and_cascade_are_atomic(tmp_path):
    database = tmp_path / "pie.sqlite3"
    repository = CalendarRepository(database)

    saved = repository.save_pie_plan(
        _plan(name="Contenido de aire", steps=("Tomar muestra", "Emitir informe"))
    )
    assert saved.id is not None
    assert saved.steps == ["Tomar muestra", "Emitir informe"]
    assert repository.list_pie_plans()[0].name == "Contenido de aire"

    saved.name = "Contenido de aire fresco"
    saved.steps = ["Preparar equipo", "Registrar resultado"]
    updated = repository.save_pie_plan(saved)
    assert updated.id == saved.id
    assert updated.steps == ["Preparar equipo", "Registrar resultado"]

    repository.set_pie_occurrence_completed(updated.id, date(2026, 1, 1), 1, True)
    assert repository.delete_pie_plan(updated.id)
    assert repository.list_pie_plans() == []
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM pie_inspection_steps").fetchone()[0] == 0
        checklist_count = connection.execute(
            "SELECT COUNT(*) FROM pie_occurrence_checklist"
        ).fetchone()[0]
        assert checklist_count == 0


def test_pie_daily_projection_only_builds_requested_range(tmp_path):
    database = tmp_path / "pie.sqlite3"
    repository = CalendarRepository(database)
    repository.save_pie_plan(
        _plan(name="Asentamiento diario", start=date(2000, 1, 1))
    )

    august = repository.list_month_pie_occurrences(2026, 8)

    assert len(august) == 31
    assert august[0].scheduled_date == date(2026, 8, 1)
    assert august[-1].scheduled_date == date(2026, 8, 31)
    with sqlite3.connect(database) as connection:
        # Recurrences are projections, not thousands of materialized event rows.
        checklist_count = connection.execute(
            "SELECT COUNT(*) FROM pie_occurrence_checklist"
        ).fetchone()[0]
        assert checklist_count == 0


def test_pie_custom_days_projects_each_duration_step(tmp_path):
    repository = CalendarRepository(tmp_path / "pie.sqlite3")
    repository.save_pie_plan(
        _plan(
            frequency=PieFrequency.CUSTOM_DAYS,
            interval=2,
            start=date(2026, 1, 30),
            steps=("Preparación", "Lectura"),
        )
    )

    occurrences = repository.list_pie_occurrences(date(2026, 2, 1), date(2026, 2, 5))
    assert [item.scheduled_date for item in occurrences] == [
        date(2026, 2, 1),
        date(2026, 2, 2),
        date(2026, 2, 3),
        date(2026, 2, 4),
        date(2026, 2, 5),
    ]
    assert [item.day_number for item in occurrences] == [1, 2, 1, 2, 1]
    assert occurrences[1].occurrence_start == date(2026, 2, 1)


def test_pie_monthly_recurrence_clamps_to_end_of_month_without_drift(tmp_path):
    repository = CalendarRepository(tmp_path / "pie.sqlite3")
    repository.save_pie_plan(
        _plan(
            frequency=PieFrequency.MONTHLY,
            start=date(2026, 1, 31),
            steps=("Muestreo", "Informe"),
        )
    )

    february = repository.list_month_pie_occurrences(2026, 2)
    march = repository.list_month_pie_occurrences(2026, 3)

    assert [(item.scheduled_date, item.day_number) for item in february] == [
        (date(2026, 2, 1), 2),
        (date(2026, 2, 28), 1)
    ]
    assert [(item.scheduled_date, item.day_number) for item in march] == [
        (date(2026, 3, 1), 2),
        (date(2026, 3, 31), 1),
    ]


def test_pie_checklist_is_sparse_and_can_be_reopened(tmp_path):
    database = tmp_path / "pie.sqlite3"
    repository = CalendarRepository(database)
    saved = repository.save_pie_plan(
        _plan(frequency=PieFrequency.WEEKLY, start=date(2026, 8, 3))
    )
    assert saved.id is not None

    repository.set_pie_occurrence_completed(saved.id, date(2026, 8, 10), 1, True)
    occurrence = repository.list_pie_occurrences_for_date(date(2026, 8, 10))[0]
    assert occurrence.is_completed
    assert occurrence.checklist_completed_at is not None

    repository.set_pie_occurrence_completed(saved.id, date(2026, 8, 10), 1, False)
    assert repository.list_pie_occurrences_for_date(date(2026, 8, 10))[0].is_pending
    with pytest.raises(ValueError, match="periodicidad"):
        repository.set_pie_occurrence_completed(saved.id, date(2026, 8, 11), 1, True)


def test_pie_edit_keeps_valid_checks_and_prunes_orphaned_schedule_rows(tmp_path):
    database = tmp_path / "pie.sqlite3"
    repository = CalendarRepository(database)
    saved = repository.save_pie_plan(
        _plan(frequency=PieFrequency.WEEKLY, start=date(2026, 8, 3))
    )
    assert saved.id is not None
    repository.set_pie_occurrence_completed(saved.id, date(2026, 8, 10), 1, True)

    saved.name = "Ensayo semanal actualizado"
    repository.save_pie_plan(saved)
    assert repository.list_pie_occurrences_for_date(date(2026, 8, 10))[0].is_completed

    saved.steps = ["Procedimiento actualizado"]
    repository.save_pie_plan(saved)
    assert repository.list_pie_occurrences_for_date(date(2026, 8, 10))[0].is_pending

    repository.set_pie_occurrence_completed(saved.id, date(2026, 8, 10), 1, True)
    saved.start_date = date(2026, 8, 4)
    repository.save_pie_plan(saved)
    with sqlite3.connect(database) as connection:
        checklist_count = connection.execute(
            "SELECT COUNT(*) FROM pie_occurrence_checklist"
        ).fetchone()[0]
        assert checklist_count == 0


def test_pie_plan_requires_one_described_step_per_day(tmp_path):
    repository = CalendarRepository(tmp_path / "pie.sqlite3")
    invalid = _plan(steps=("", "Lectura"))
    with pytest.raises(ValueError, match="Describe el paso"):
        repository.save_pie_plan(invalid)


def test_pie_dialog_rebuilds_one_step_field_per_duration_day(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    from PySide6.QtWidgets import QApplication

    from concrete_mix_designer.ui.dialogs.pie_dialog import PiePlanDialog

    app = QApplication.instance() or QApplication([])
    dialog = PiePlanDialog(CalendarRepository(tmp_path / "pie.sqlite3"))
    dialog.duration_input.setValue(3)
    app.processEvents()

    assert dialog.windowTitle() == "Plan de Inspección y Ensayo"
    assert len(dialog._step_inputs) == 3
    assert [field.placeholderText() for field in dialog._step_inputs] == [
        "Actividad o procedimiento del día 1",
        "Actividad o procedimiento del día 2",
        "Actividad o procedimiento del día 3",
    ]
    dialog.close()


def test_calendar_page_exposes_pie_button_and_daily_occurrence(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    from PySide6.QtCore import QDate, QObject, Signal
    from PySide6.QtWidgets import QApplication

    from concrete_mix_designer.ui.pages.calendar_page import LaboratoryCalendarPage

    class FakeState(QObject):
        productions_changed = Signal()
        message = Signal(str)

        def __init__(self, database_path):
            super().__init__()
            self.laboratory_repository = SimpleNamespace(database_path=database_path)

    database = tmp_path / "calendar.sqlite3"
    _initialize_calendar_schema(database)
    app = QApplication.instance() or QApplication([])
    page = LaboratoryCalendarPage(FakeState(database))
    page.repository.save_pie_plan(
        _plan(name="Densidad del concreto", start=date(2026, 8, 10))
    )
    page.calendar.setSelectedDate(QDate(2026, 8, 10))
    page.refresh()
    app.processEvents()

    assert page.pie_button.text() == "Añadir PIE"
    assert page.table.rowCount() == 1
    assert page.table.item(0, 2).text() == "PIE-1"
    assert page.table.item(0, 6).text() == "Densidad del concreto"
    assert page.table.item(0, 8).text() == "Ejecutar ensayo"
    page.close()


def test_calendar_summary_includes_only_bounded_pie_ranges(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    from datetime import timedelta

    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    from concrete_mix_designer.ui.pages.calendar_page import LaboratoryCalendarPage

    class FakeState(QObject):
        productions_changed = Signal()
        message = Signal(str)

        def __init__(self, database_path):
            super().__init__()
            self.laboratory_repository = SimpleNamespace(database_path=database_path)

    database = tmp_path / "calendar-summary.sqlite3"
    _initialize_calendar_schema(database)
    app = QApplication.instance() or QApplication([])
    page = LaboratoryCalendarPage(FakeState(database))
    today = date.today()
    current = page.repository.save_pie_plan(
        _plan(name="Control de hoy", frequency=PieFrequency.WEEKLY, start=today)
    )
    page.repository.save_pie_plan(
        _plan(
            name="Control de mañana",
            frequency=PieFrequency.WEEKLY,
            start=today + timedelta(days=1),
        )
    )
    page.refresh()
    app.processEvents()

    assert page.pending_today_value[1].text() == "1"
    assert page.completed_today_value[1].text() == "0"
    assert page.upcoming_value[1].text() == "2"
    assert page.pending_today_value[0].layout().itemAt(0).widget().text() == (
        "Actividades pendientes hoy"
    )
    assert page.overdue_value[0].layout().itemAt(0).widget().text() == "Muestras vencidas"

    assert current.id is not None
    page.repository.set_pie_occurrence_completed(current.id, today, 1, True)
    page.refresh()
    assert page.pending_today_value[1].text() == "0"
    assert page.completed_today_value[1].text() == "1"
    page.close()
