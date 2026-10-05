from __future__ import annotations

import sqlite3
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from civillab_suite.sqlite_support import connect as sqlite_connect
from concrete_mix_designer.domain.laboratory_models import SpecimenStatus, SpecimenType
from concrete_mix_designer.domain.pie_models import (
    PieFrequency,
    PieInspectionPlan,
    PieOccurrence,
)


def _now() -> datetime:
    return datetime.now().astimezone()


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.astimezone()
    return value.isoformat(timespec="seconds")


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(slots=True)
class CalendarTaskRecord:
    specimen_id: int
    production_id: int
    planned_test_at: datetime
    specimen_code: str
    specimen_type: SpecimenType
    target_age_days: float
    specimen_status: SpecimenStatus
    specimen_notes: str
    batch_code: str
    design_name: str
    group_name: str
    checklist_completed: bool
    checklist_completed_at: datetime | None

    @property
    def is_completed(self) -> bool:
        return (
            self.checklist_completed
            or self.specimen_status == SpecimenStatus.TESTED
            or self.specimen_status == SpecimenStatus.CANCELLED
        )

    @property
    def is_pending(self) -> bool:
        return self.specimen_status == SpecimenStatus.PLANNED and not self.checklist_completed

    def is_overdue(self, reference_date: date | None = None) -> bool:
        reference = reference_date or _now().date()
        return self.is_pending and self.planned_test_at.date() < reference


@dataclass(slots=True)
class CalendarOperationalSummary:
    pending_today: int = 0
    completed_today: int = 0
    overdue: int = 0
    upcoming_seven_days: int = 0


class CalendarRepository:
    """Operational checklist for specimens scheduled by laboratory production.

    Checklist completion is intentionally independent from ``specimens.status``.
    Marking an itinerary item as completed never invents a strength result and does
    not alter laboratory statistics. A tested or cancelled specimen is displayed as
    completed automatically, even when it has no manual checklist row.
    """

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        from civillab_suite.storage import ensure_domain_namespace
        ensure_domain_namespace(self.database_path, "concretos")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite_connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS concretos_specimen_checklist (
                    specimen_id INTEGER PRIMARY KEY
                        REFERENCES concretos_specimens(id) ON DELETE CASCADE,
                    completed INTEGER NOT NULL DEFAULT 0,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_specimen_checklist_completed
                    ON concretos_specimen_checklist(completed, updated_at);

                CREATE TABLE IF NOT EXISTS concretos_pie_inspection_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    frequency TEXT NOT NULL CHECK(frequency IN (
                        'daily', 'weekly', 'monthly', 'custom_days', 'custom_months'
                    )),
                    recurrence_interval INTEGER NOT NULL
                        CHECK(recurrence_interval > 0),
                    start_date TEXT NOT NULL,
                    duration_days INTEGER NOT NULL
                        CHECK(duration_days BETWEEN 1 AND 365),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS concretos_pie_inspection_steps (
                    plan_id INTEGER NOT NULL
                        REFERENCES concretos_pie_inspection_plans(id) ON DELETE CASCADE,
                    day_number INTEGER NOT NULL CHECK(day_number > 0),
                    description TEXT NOT NULL,
                    PRIMARY KEY(plan_id, day_number)
                );

                CREATE TABLE IF NOT EXISTS concretos_pie_occurrence_checklist (
                    plan_id INTEGER NOT NULL
                        REFERENCES concretos_pie_inspection_plans(id) ON DELETE CASCADE,
                    occurrence_start TEXT NOT NULL,
                    day_number INTEGER NOT NULL CHECK(day_number > 0),
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY(plan_id, occurrence_start, day_number)
                );

                CREATE INDEX IF NOT EXISTS idx_pie_plans_start
                    ON concretos_pie_inspection_plans(start_date, frequency);
                CREATE INDEX IF NOT EXISTS idx_pie_checklist_date
                    ON concretos_pie_occurrence_checklist(occurrence_start, plan_id);
                """
            )

    @staticmethod
    def month_bounds(year: int, month: int) -> tuple[date, date]:
        start = date(year, month, 1)
        if month == 12:
            following = date(year + 1, 1, 1)
        else:
            following = date(year, month + 1, 1)
        return start, following - timedelta(days=1)

    def list_month_tasks(self, year: int, month: int) -> list[CalendarTaskRecord]:
        start, end = self.month_bounds(year, month)
        return self.list_tasks(start, end)

    def list_tasks_for_date(self, selected_date: date) -> list[CalendarTaskRecord]:
        return self.list_tasks(selected_date, selected_date)

    def list_tasks(self, start_date: date, end_date: date) -> list[CalendarTaskRecord]:
        if end_date < start_date:
            raise ValueError("La fecha final no puede ser anterior a la fecha inicial.")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    s.id AS specimen_id,
                    s.production_id,
                    s.planned_test_at,
                    s.specimen_code,
                    s.specimen_type,
                    s.target_age_days,
                    s.status AS specimen_status,
                    s.notes AS specimen_notes,
                    p.batch_code,
                    p.design_name,
                    COALESCE(d.group_name, '') AS group_name,
                    COALESCE(c.completed, 0) AS checklist_completed,
                    c.completed_at AS checklist_completed_at
                FROM concretos_specimens s
                JOIN concretos_productions p ON p.id = s.production_id
                LEFT JOIN concretos_mix_designs d ON d.id = p.design_id
                LEFT JOIN concretos_specimen_checklist c ON c.specimen_id = s.id
                WHERE substr(s.planned_test_at, 1, 10) BETWEEN ? AND ?
                ORDER BY s.planned_test_at, p.batch_code, s.specimen_type, s.specimen_code
                """,
                (start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def set_task_completed(self, specimen_id: int, completed: bool) -> None:
        now = _now()
        with self._connect() as connection:
            specimen = connection.execute(
                "SELECT status FROM concretos_specimens WHERE id = ?", (specimen_id,)
            ).fetchone()
            if specimen is None:
                raise ValueError("La muestra seleccionada ya no existe.")
            status = SpecimenStatus(specimen["status"])
            if status in {SpecimenStatus.TESTED, SpecimenStatus.CANCELLED}:
                return
            connection.execute(
                """
                INSERT INTO concretos_specimen_checklist (
                    specimen_id, completed, completed_at, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(specimen_id) DO UPDATE SET
                    completed = excluded.completed,
                    completed_at = excluded.completed_at,
                    updated_at = excluded.updated_at
                """,
                (
                    specimen_id,
                    int(bool(completed)),
                    _serialize_datetime(now) if completed else None,
                    _serialize_datetime(now),
                ),
            )

    def operational_summary(
        self, reference_date: date | None = None
    ) -> CalendarOperationalSummary:
        reference = reference_date or _now().date()
        following = reference + timedelta(days=1)
        seven_days = reference + timedelta(days=7)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    SUM(CASE
                        WHEN substr(s.planned_test_at, 1, 10) = ?
                         AND s.status = 'planned'
                         AND COALESCE(c.completed, 0) = 0
                        THEN 1 ELSE 0 END
                    ) AS pending_today,
                    SUM(CASE
                        WHEN substr(s.planned_test_at, 1, 10) = ?
                         AND (s.status IN ('tested', 'cancelled') OR COALESCE(c.completed, 0) = 1)
                        THEN 1 ELSE 0 END
                    ) AS completed_today,
                    SUM(CASE
                        WHEN substr(s.planned_test_at, 1, 10) < ?
                         AND s.status = 'planned'
                         AND COALESCE(c.completed, 0) = 0
                        THEN 1 ELSE 0 END
                    ) AS overdue,
                    SUM(CASE
                        WHEN substr(s.planned_test_at, 1, 10) BETWEEN ? AND ?
                         AND s.status = 'planned'
                         AND COALESCE(c.completed, 0) = 0
                        THEN 1 ELSE 0 END
                    ) AS upcoming_seven_days
                FROM concretos_specimens s
                LEFT JOIN concretos_specimen_checklist c ON c.specimen_id = s.id
                """,
                (
                    reference.isoformat(),
                    reference.isoformat(),
                    reference.isoformat(),
                    following.isoformat(),
                    seven_days.isoformat(),
                ),
            ).fetchone()
        return CalendarOperationalSummary(
            pending_today=int(row["pending_today"] or 0),
            completed_today=int(row["completed_today"] or 0),
            overdue=int(row["overdue"] or 0),
            upcoming_seven_days=int(row["upcoming_seven_days"] or 0),
        )

    # ------------------------------------------------------------------
    # Plan de Inspección y Ensayo (PIE)
    # ------------------------------------------------------------------
    def list_pie_plans(self) -> list[PieInspectionPlan]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM concretos_pie_inspection_plans
                ORDER BY name COLLATE NOCASE, start_date, id
                """
            ).fetchall()
            return [self._row_to_pie_plan(connection, row) for row in rows]

    def get_pie_plan(self, plan_id: int) -> PieInspectionPlan | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM concretos_pie_inspection_plans WHERE id = ?", (plan_id,)
            ).fetchone()
            return self._row_to_pie_plan(connection, row) if row else None

    def save_pie_plan(self, plan: PieInspectionPlan) -> PieInspectionPlan:
        self._validate_pie_plan(plan)
        now = _now()
        name = plan.name.strip()
        steps = [step.strip() for step in plan.steps]
        frequency = PieFrequency(plan.frequency)
        interval = self._normalized_interval(frequency, plan.interval)
        with self._connect() as connection:
            if plan.id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO concretos_pie_inspection_plans (
                        name, frequency, recurrence_interval, start_date,
                        duration_days, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        frequency.value,
                        interval,
                        plan.start_date.isoformat(),
                        int(plan.duration_days),
                        _serialize_datetime(now),
                        _serialize_datetime(now),
                    ),
                )
                plan_id = int(cursor.lastrowid)
            else:
                plan_id = int(plan.id)
                cursor = connection.execute(
                    """
                    UPDATE concretos_pie_inspection_plans SET
                        name = ?, frequency = ?, recurrence_interval = ?,
                        start_date = ?, duration_days = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        name,
                        frequency.value,
                        interval,
                        plan.start_date.isoformat(),
                        int(plan.duration_days),
                        _serialize_datetime(now),
                        plan_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise ValueError("El ensayo PIE seleccionado ya no existe.")
                previous_steps = {
                    int(row["day_number"]): str(row["description"])
                    for row in connection.execute(
                        """
                        SELECT day_number, description FROM concretos_pie_inspection_steps
                        WHERE plan_id = ?
                        """,
                        (plan_id,),
                    ).fetchall()
                }
                connection.execute(
                    "DELETE FROM concretos_pie_inspection_steps WHERE plan_id = ?", (plan_id,)
                )
                schedule = PieInspectionPlan(
                    id=plan_id,
                    name=name,
                    frequency=frequency,
                    interval=interval,
                    start_date=plan.start_date,
                    duration_days=int(plan.duration_days),
                    steps=steps,
                )
                changed_days = {
                    day_number
                    for day_number, step in enumerate(steps, 1)
                    if previous_steps.get(day_number) != step
                }
                checklist_rows = connection.execute(
                    """
                    SELECT occurrence_start, day_number
                    FROM concretos_pie_occurrence_checklist WHERE plan_id = ?
                    """,
                    (plan_id,),
                ).fetchall()
                obsolete = [
                    (plan_id, str(row["occurrence_start"]), int(row["day_number"]))
                    for row in checklist_rows
                    if int(row["day_number"]) in changed_days
                    or int(row["day_number"]) > schedule.duration_days
                    or not self._is_occurrence_start(
                        schedule, date.fromisoformat(str(row["occurrence_start"]))
                    )
                ]
                connection.executemany(
                    """
                    DELETE FROM concretos_pie_occurrence_checklist
                    WHERE plan_id = ? AND occurrence_start = ? AND day_number = ?
                    """,
                    obsolete,
                )
            connection.executemany(
                """
                INSERT INTO concretos_pie_inspection_steps (plan_id, day_number, description)
                VALUES (?, ?, ?)
                """,
                [(plan_id, day_number, step) for day_number, step in enumerate(steps, 1)],
            )
        saved = self.get_pie_plan(plan_id)
        if saved is None:
            raise RuntimeError("No fue posible recuperar el ensayo PIE guardado.")
        return saved

    def delete_pie_plan(self, plan_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM concretos_pie_inspection_plans WHERE id = ?", (plan_id,)
            )
        return cursor.rowcount > 0

    def list_month_pie_occurrences(self, year: int, month: int) -> list[PieOccurrence]:
        start, end = self.month_bounds(year, month)
        return self.list_pie_occurrences(start, end)

    def list_pie_occurrences_for_date(self, selected_date: date) -> list[PieOccurrence]:
        return self.list_pie_occurrences(selected_date, selected_date)

    def list_pie_occurrences(
        self, start_date: date, end_date: date
    ) -> list[PieOccurrence]:
        if end_date < start_date:
            raise ValueError("La fecha final no puede ser anterior a la fecha inicial.")
        plans = self.list_pie_plans()
        projected: list[tuple[PieInspectionPlan, date, date, int, str]] = []
        for plan in plans:
            for occurrence_start in self._occurrence_starts_in_range(
                plan, start_date, end_date
            ):
                first_day = max(1, (start_date - occurrence_start).days + 1)
                last_day = min(
                    plan.duration_days, (end_date - occurrence_start).days + 1
                )
                for day_number in range(first_day, last_day + 1):
                    step = plan.steps[day_number - 1]
                    scheduled = occurrence_start + timedelta(days=day_number - 1)
                    projected.append(
                        (plan, occurrence_start, scheduled, day_number, step)
                    )

        if not projected:
            return []
        first_occurrence = min(item[1] for item in projected).isoformat()
        last_occurrence = max(item[1] for item in projected).isoformat()
        plan_ids = sorted({int(item[0].id) for item in projected if item[0].id is not None})
        placeholders = ",".join("?" for _ in plan_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT plan_id, occurrence_start, day_number, completed_at
                FROM concretos_pie_occurrence_checklist
                WHERE plan_id IN ({placeholders})
                  AND occurrence_start BETWEEN ? AND ?
                """,
                (*plan_ids, first_occurrence, last_occurrence),
            ).fetchall()
        completed = {
            (int(row["plan_id"]), str(row["occurrence_start"]), int(row["day_number"])):
            _parse_datetime(str(row["completed_at"]))
            for row in rows
        }
        output = []
        for plan, occurrence_start, scheduled, day_number, step in projected:
            if plan.id is None:
                continue
            completed_at = completed.get(
                (plan.id, occurrence_start.isoformat(), day_number)
            )
            output.append(
                PieOccurrence(
                    plan_id=plan.id,
                    plan_name=plan.name,
                    frequency=plan.frequency,
                    interval=plan.interval,
                    occurrence_start=occurrence_start,
                    scheduled_date=scheduled,
                    day_number=day_number,
                    duration_days=plan.duration_days,
                    step_description=step,
                    checklist_completed=completed_at is not None,
                    checklist_completed_at=completed_at,
                )
            )
        return sorted(
            output,
            key=lambda item: (
                item.scheduled_date,
                item.plan_name.casefold(),
                item.occurrence_start,
                item.day_number,
            ),
        )

    def set_pie_occurrence_completed(
        self,
        plan_id: int,
        occurrence_start: date,
        day_number: int,
        completed: bool,
    ) -> None:
        plan = self.get_pie_plan(plan_id)
        if plan is None:
            raise ValueError("El ensayo PIE seleccionado ya no existe.")
        if not 1 <= day_number <= plan.duration_days:
            raise ValueError("El día del ensayo PIE no es válido.")
        if not self._is_occurrence_start(plan, occurrence_start):
            raise ValueError("La fecha no corresponde a la periodicidad del ensayo PIE.")
        with self._connect() as connection:
            if completed:
                connection.execute(
                    """
                    INSERT INTO concretos_pie_occurrence_checklist (
                        plan_id, occurrence_start, day_number, completed_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(plan_id, occurrence_start, day_number) DO UPDATE SET
                        completed_at = excluded.completed_at
                    """,
                    (
                        plan_id,
                        occurrence_start.isoformat(),
                        day_number,
                        _serialize_datetime(_now()),
                    ),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM concretos_pie_occurrence_checklist
                    WHERE plan_id = ? AND occurrence_start = ? AND day_number = ?
                    """,
                    (plan_id, occurrence_start.isoformat(), day_number),
                )

    @staticmethod
    def pie_frequency_label(frequency: PieFrequency, interval: int) -> str:
        frequency = PieFrequency(frequency)
        if frequency == PieFrequency.DAILY:
            return "Diario"
        if frequency == PieFrequency.WEEKLY:
            return "Semanal"
        if frequency == PieFrequency.MONTHLY:
            return "Mensual"
        if frequency == PieFrequency.CUSTOM_DAYS:
            return f"Cada {interval} día" + ("s" if interval != 1 else "")
        return f"Cada {interval} mes" + ("es" if interval != 1 else "")

    @staticmethod
    def _normalized_interval(frequency: PieFrequency, interval: int) -> int:
        if frequency in {PieFrequency.DAILY, PieFrequency.WEEKLY, PieFrequency.MONTHLY}:
            return 1
        return int(interval)

    @classmethod
    def _validate_pie_plan(cls, plan: PieInspectionPlan) -> None:
        if not plan.name.strip():
            raise ValueError("Escribe el nombre del ensayo.")
        frequency = PieFrequency(plan.frequency)
        interval = cls._normalized_interval(frequency, plan.interval)
        if interval < 1:
            raise ValueError("La periodicidad debe ser mayor que cero.")
        if not 1 <= int(plan.duration_days) <= 365:
            raise ValueError("La duración debe estar entre 1 y 365 días.")
        if len(plan.steps) != int(plan.duration_days):
            raise ValueError("Debe existir un paso para cada día de duración.")
        if any(not step.strip() for step in plan.steps):
            raise ValueError("Describe el paso correspondiente a cada día.")

    @staticmethod
    def _row_to_pie_plan(
        connection: sqlite3.Connection, row: sqlite3.Row
    ) -> PieInspectionPlan:
        step_rows = connection.execute(
            """
            SELECT description FROM concretos_pie_inspection_steps
            WHERE plan_id = ? ORDER BY day_number
            """,
            (int(row["id"]),),
        ).fetchall()
        return PieInspectionPlan(
            id=int(row["id"]),
            name=str(row["name"]),
            frequency=PieFrequency(row["frequency"]),
            interval=int(row["recurrence_interval"]),
            start_date=date.fromisoformat(str(row["start_date"])),
            duration_days=int(row["duration_days"]),
            steps=[str(step["description"]) for step in step_rows],
            created_at=_parse_datetime(str(row["created_at"])),
            updated_at=_parse_datetime(str(row["updated_at"])),
        )

    @classmethod
    def _occurrence_starts_in_range(
        cls, plan: PieInspectionPlan, start_date: date, end_date: date
    ) -> list[date]:
        lower_ordinal = max(
            date.min.toordinal(), start_date.toordinal() - plan.duration_days + 1
        )
        earliest_start = date.fromordinal(lower_ordinal)
        if plan.start_date > end_date:
            return []

        if plan.frequency in {
            PieFrequency.DAILY,
            PieFrequency.WEEKLY,
            PieFrequency.CUSTOM_DAYS,
        }:
            day_interval = {
                PieFrequency.DAILY: 1,
                PieFrequency.WEEKLY: 7,
                PieFrequency.CUSTOM_DAYS: plan.interval,
            }[plan.frequency]
            delta = (earliest_start - plan.start_date).days
            first_index = max(0, -(-delta // day_interval))
            occurrence = plan.start_date + timedelta(days=first_index * day_interval)
            output = []
            while occurrence <= end_date:
                output.append(occurrence)
                occurrence += timedelta(days=day_interval)
            return output

        month_interval = 1 if plan.frequency == PieFrequency.MONTHLY else plan.interval
        month_delta = (
            (earliest_start.year - plan.start_date.year) * 12
            + earliest_start.month
            - plan.start_date.month
        )
        first_index = max(0, month_delta // month_interval - 1)
        output = []
        while True:
            try:
                occurrence = cls._add_months(
                    plan.start_date, first_index * month_interval
                )
            except (OverflowError, ValueError):
                break
            if occurrence > end_date:
                break
            if occurrence >= earliest_start:
                output.append(occurrence)
            first_index += 1
        return output

    @classmethod
    def _is_occurrence_start(cls, plan: PieInspectionPlan, value: date) -> bool:
        if value < plan.start_date:
            return False
        if plan.frequency in {
            PieFrequency.DAILY,
            PieFrequency.WEEKLY,
            PieFrequency.CUSTOM_DAYS,
        }:
            interval = {
                PieFrequency.DAILY: 1,
                PieFrequency.WEEKLY: 7,
                PieFrequency.CUSTOM_DAYS: plan.interval,
            }[plan.frequency]
            return (value - plan.start_date).days % interval == 0
        month_interval = 1 if plan.frequency == PieFrequency.MONTHLY else plan.interval
        month_delta = (
            (value.year - plan.start_date.year) * 12
            + value.month
            - plan.start_date.month
        )
        return (
            month_delta >= 0
            and month_delta % month_interval == 0
            and cls._add_months(plan.start_date, month_delta) == value
        )

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        absolute_month = value.year * 12 + value.month - 1 + months
        year, zero_based_month = divmod(absolute_month, 12)
        month = zero_based_month + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> CalendarTaskRecord:
        return CalendarTaskRecord(
            specimen_id=int(row["specimen_id"]),
            production_id=int(row["production_id"]),
            planned_test_at=datetime.fromisoformat(str(row["planned_test_at"])),
            specimen_code=str(row["specimen_code"]),
            specimen_type=SpecimenType(row["specimen_type"]),
            target_age_days=float(row["target_age_days"]),
            specimen_status=SpecimenStatus(row["specimen_status"]),
            specimen_notes=str(row["specimen_notes"] or ""),
            batch_code=str(row["batch_code"]),
            design_name=str(row["design_name"]),
            group_name=str(row["group_name"] or ""),
            checklist_completed=bool(row["checklist_completed"]),
            checklist_completed_at=_parse_datetime(row["checklist_completed_at"]),
        )
