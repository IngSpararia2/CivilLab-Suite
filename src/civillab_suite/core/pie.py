from __future__ import annotations

import sqlite3
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from .database import CoreDatabase, _normalized


class PieFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM_DAYS = "custom_days"
    CUSTOM_MONTHS = "custom_months"


@dataclass(slots=True)
class PiePlan:
    assay_id: int | None
    module_ids: tuple[str, ...]
    responsible: str
    frequency: PieFrequency
    interval: int
    start_date: date
    duration_days: int = 1
    steps: list[str] = field(default_factory=lambda: ["Ejecutar ensayo"])
    material_type_id: int | None = None
    material_object_id: int | None = None
    method_id: int | None = None
    observations: str = ""
    id: int | None = None
    assay_name: str = ""
    material_name: str = ""
    legacy_name: str = ""
    active: bool = True
    weekday: int | None = None
    week_ordinal: int | None = None
    source_module_id: str | None = None
    source_table: str = ""
    source_id: str = ""

    @property
    def display_name(self) -> str:
        return self.assay_name or self.legacy_name


@dataclass(frozen=True, slots=True)
class PieOccurrence:
    plan_id: int
    assay_id: int | None
    module_ids: tuple[str, ...]
    title: str
    occurrence_start: date
    scheduled_date: date
    original_scheduled_date: date
    day_number: int
    step_description: str
    completed_at: datetime | None = None
    notes: str = ""

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def is_pending(self) -> bool:
        return not self.is_completed

    def is_overdue(self, reference_date: date | None = None) -> bool:
        return self.is_pending and self.scheduled_date < (reference_date or date.today())


class PieService:
    """Shared PIE repository. Recurrences are projected; only state changes are stored."""

    def __init__(self, database: CoreDatabase):
        self.database = database

    def create_plan(
        self,
        *,
        assay_id: int,
        module_ids: Iterable[str],
        responsible: str,
        frequency: PieFrequency | str,
        start_date: date,
        interval: int = 1,
        duration_days: int = 1,
        steps: Iterable[str] | None = None,
        material_type_id: int | None = None,
        material_object_id: int | None = None,
        method_id: int | None = None,
        observations: str = "",
    ) -> PiePlan:
        plan = PiePlan(
            assay_id=assay_id,
            module_ids=tuple(dict.fromkeys(module_ids)),
            responsible=responsible,
            frequency=PieFrequency(frequency),
            interval=interval,
            start_date=start_date,
            duration_days=duration_days,
            steps=list(steps or ["Ejecutar ensayo"]),
            material_type_id=material_type_id,
            material_object_id=material_object_id,
            method_id=method_id,
            observations=observations,
        )
        return self.save_plan(plan)

    def save_plan(self, plan: PiePlan) -> PiePlan:
        self._validate(plan, require_catalog=True)
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            self._validate_references(connection, plan)
            if plan.id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO pie_plans (
                        assay_id, method_id, material_type_id, material_object_id,
                        legacy_name, responsible, frequency, recurrence_interval,
                        start_date, duration_days, weekday, week_ordinal, observations,
                        active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        plan.assay_id, plan.method_id, plan.material_type_id,
                        plan.material_object_id, plan.legacy_name.strip(),
                        plan.responsible.strip(), PieFrequency(plan.frequency).value,
                        int(plan.interval), plan.start_date.isoformat(),
                        int(plan.duration_days), plan.weekday, plan.week_ordinal,
                        plan.observations.strip(), now, now,
                    ),
                )
                plan_id = int(cursor.lastrowid)
            else:
                plan_id = int(plan.id)
                cursor = connection.execute(
                    """
                    UPDATE pie_plans SET
                        assay_id = ?, method_id = ?, material_type_id = ?,
                        material_object_id = ?, legacy_name = ?, responsible = ?,
                        frequency = ?, recurrence_interval = ?, start_date = ?,
                        duration_days = ?, weekday = ?, week_ordinal = ?,
                        observations = ?, active = 1, deactivated_at = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        plan.assay_id, plan.method_id, plan.material_type_id,
                        plan.material_object_id, plan.legacy_name.strip(),
                        plan.responsible.strip(), PieFrequency(plan.frequency).value,
                        int(plan.interval), plan.start_date.isoformat(),
                        int(plan.duration_days), plan.weekday, plan.week_ordinal,
                        plan.observations.strip(), now, plan_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise ValueError("La entrada PIE ya no existe.")
                connection.execute("DELETE FROM pie_plan_modules WHERE plan_id = ?", (plan_id,))
                connection.execute("DELETE FROM pie_plan_steps WHERE plan_id = ?", (plan_id,))
            connection.executemany(
                "INSERT INTO pie_plan_modules (plan_id, module_id) VALUES (?, ?)",
                [(plan_id, module_id) for module_id in plan.module_ids],
            )
            connection.executemany(
                """
                INSERT INTO pie_plan_steps (plan_id, day_number, description)
                VALUES (?, ?, ?)
                """,
                [
                    (plan_id, day_number, description.strip())
                    for day_number, description in enumerate(plan.steps, 1)
                ],
            )
        saved = self.get_plan(plan_id)
        assert saved is not None
        return saved

    def get_plan(self, plan_id: int) -> PiePlan | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT p.*, a.canonical_name AS assay_name,
                       COALESCE(mo.canonical_name, mt.canonical_name, '') AS material_name
                FROM pie_plans p
                LEFT JOIN assays a ON a.id = p.assay_id
                LEFT JOIN material_objects mo ON mo.id = p.material_object_id
                LEFT JOIN material_types mt ON mt.id = p.material_type_id
                WHERE p.id = ?
                """,
                (plan_id,),
            ).fetchone()
            return self._row_to_plan(connection, row) if row is not None else None

    def list_plans(
        self, module_ids: str | Iterable[str] | None = None, *, include_inactive: bool = False
    ) -> list[PiePlan]:
        modules = self._module_tuple(module_ids)
        clauses = [] if include_inactive else ["p.active = 1"]
        parameters: list[object] = []
        if modules:
            placeholders = ",".join("?" for _ in modules)
            clauses.append(
                "EXISTS (SELECT 1 FROM pie_plan_modules ppm "
                f"WHERE ppm.plan_id = p.id AND ppm.module_id IN ({placeholders}))"
            )
            parameters.extend(modules)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT p.*, a.canonical_name AS assay_name,
                       COALESCE(mo.canonical_name, mt.canonical_name, '') AS material_name
                FROM pie_plans p
                LEFT JOIN assays a ON a.id = p.assay_id
                LEFT JOIN material_objects mo ON mo.id = p.material_object_id
                LEFT JOIN material_types mt ON mt.id = p.material_type_id
                {where}
                ORDER BY p.active DESC, COALESCE(a.canonical_name, p.legacy_name)
                         COLLATE NOCASE, p.id
                """,
                parameters,
            ).fetchall()
            return [self._row_to_plan(connection, row) for row in rows]

    def deactivate_plan(self, plan_id: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pie_plans
                SET active = 0, deactivated_at = ?, updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (now, now, plan_id),
            )
        return cursor.rowcount > 0

    def list_occurrences(
        self,
        start: date,
        end: date,
        module_ids: str | Iterable[str] | None = None,
    ) -> list[PieOccurrence]:
        if end < start:
            raise ValueError("La fecha final no puede ser anterior a la inicial.")
        plans = self.list_plans(module_ids)
        output: list[PieOccurrence] = []
        with self.database.connect() as connection:
            status_rows = connection.execute(
                """
                SELECT * FROM pie_occurrence_status
                WHERE (rescheduled_date BETWEEN ? AND ?)
                   OR (rescheduled_date IS NULL AND occurrence_start <= ?)
                """,
                (start.isoformat(), end.isoformat(), end.isoformat()),
            ).fetchall()
        status = {
            (int(row["plan_id"]), str(row["occurrence_start"]), int(row["day_number"])): row
            for row in status_rows
        }
        for plan in plans:
            if plan.id is None:
                continue
            projection_start = start - timedelta(days=max(plan.duration_days, 1))
            for occurrence_start in self._starts_between(plan, projection_start, end):
                for day_number, description in enumerate(plan.steps, 1):
                    original = occurrence_start + timedelta(days=day_number - 1)
                    state = status.get((plan.id, occurrence_start.isoformat(), day_number))
                    scheduled = (
                        date.fromisoformat(str(state["rescheduled_date"]))
                        if state is not None and state["rescheduled_date"] else original
                    )
                    if not start <= scheduled <= end:
                        continue
                    completed_at = (
                        datetime.fromisoformat(str(state["completed_at"]))
                        if state is not None and state["completed_at"] else None
                    )
                    output.append(
                        PieOccurrence(
                            plan_id=plan.id,
                            assay_id=plan.assay_id,
                            module_ids=plan.module_ids,
                            title=plan.display_name,
                            occurrence_start=occurrence_start,
                            scheduled_date=scheduled,
                            original_scheduled_date=original,
                            day_number=day_number,
                            step_description=description,
                            completed_at=completed_at,
                            notes=str(state["notes"]) if state is not None else "",
                        )
                    )
        return sorted(
            output,
            key=lambda item: (
                item.scheduled_date, item.title.casefold(), item.plan_id, item.day_number
            ),
        )

    def set_occurrence_completed(
        self,
        plan_id: int,
        occurrence_start: date,
        day_number: int,
        completed: bool,
        notes: str = "",
    ) -> None:
        plan = self.get_plan(plan_id)
        self._validate_occurrence(plan, occurrence_start, day_number)
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO pie_occurrence_status (
                    plan_id, occurrence_start, day_number, completed_at, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id, occurrence_start, day_number) DO UPDATE SET
                    completed_at = excluded.completed_at,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    plan_id, occurrence_start.isoformat(), day_number,
                    now if completed else None, notes.strip(), now,
                ),
            )

    def reschedule_occurrence(
        self, plan_id: int, occurrence_start: date, day_number: int, new_date: date
    ) -> None:
        plan = self.get_plan(plan_id)
        self._validate_occurrence(plan, occurrence_start, day_number)
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO pie_occurrence_status (
                    plan_id, occurrence_start, day_number, rescheduled_date, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(plan_id, occurrence_start, day_number) DO UPDATE SET
                    rescheduled_date = excluded.rescheduled_date,
                    updated_at = excluded.updated_at
                """,
                (plan_id, occurrence_start.isoformat(), day_number, new_date.isoformat(), now),
            )

    def import_concretos_legacy(self, path: Path) -> int:
        path = Path(path)
        if not path.is_file():
            return 0
        source = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        try:
            tables = {row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not {"pie_inspection_plans", "pie_inspection_steps"}.issubset(tables):
                return 0
            rows = source.execute("SELECT * FROM pie_inspection_plans ORDER BY id").fetchall()
            steps = {
                int(row["plan_id"]): [] for row in source.execute(
                    "SELECT DISTINCT plan_id FROM pie_inspection_steps"
                )
            }
            for row in source.execute(
                "SELECT plan_id, day_number, description FROM pie_inspection_steps "
                "ORDER BY plan_id, day_number"
            ):
                steps.setdefault(int(row["plan_id"]), []).append(str(row["description"]))
        finally:
            source.close()
        imported = 0
        with self.database.connect() as connection:
            for row in rows:
                assay = connection.execute(
                    "SELECT id FROM assays WHERE normalized_name = ?",
                    (_normalized(str(row["name"])),),
                ).fetchone()
                imported += self._upsert_legacy(
                    connection,
                    assay_id=int(assay["id"]) if assay is not None else None,
                    legacy_name=str(row["name"]),
                    module_ids=("concretos",),
                    responsible="",
                    frequency=str(row["frequency"]),
                    interval=int(row["recurrence_interval"]),
                    start_date=str(row["start_date"]),
                    duration_days=int(row["duration_days"]),
                    steps=steps.get(int(row["id"]), []) or ["Ejecutar ensayo"],
                    source_module="concretos",
                    source_table="pie_inspection_plans",
                    source_id=str(row["id"]),
                    active=True,
                )
        return imported

    def import_prefabricados_legacy(self, path: Path) -> int:
        path = Path(path)
        if not path.is_file():
            return 0
        source = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        try:
            tables = {row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if "inspection_plan_entries" not in tables:
                return 0
            rows = source.execute(
                """
                SELECT p.*, t.code AS test_code, t.name AS test_name,
                       m.code AS material_code
                FROM inspection_plan_entries p
                JOIN laboratory_tests t ON t.id = p.laboratory_test_id
                JOIN material_types m ON m.id = p.material_type_id
                ORDER BY p.id
                """
            ).fetchall()
        finally:
            source.close()
        imported = 0
        with self.database.connect() as connection:
            for row in rows:
                method = connection.execute(
                    """
                    SELECT id, assay_id FROM assay_methods
                    WHERE module_id = 'prefabricados' AND source_key = ?
                    """,
                    (str(row["test_code"]),),
                ).fetchone()
                material = connection.execute(
                    "SELECT id FROM material_types WHERE code = ?",
                    (str(row["material_code"]),),
                ).fetchone()
                frequency, interval = self._prefabricados_frequency(row)
                start = self._prefabricados_start(row)
                imported += self._upsert_legacy(
                    connection,
                    assay_id=int(method["assay_id"]) if method is not None else None,
                    method_id=int(method["id"]) if method is not None else None,
                    material_type_id=int(material["id"]) if material is not None else None,
                    legacy_name=str(row["test_name"]),
                    module_ids=("prefabricados",),
                    responsible=str(row["responsible"]),
                    frequency=frequency,
                    interval=interval,
                    start_date=start.isoformat(),
                    duration_days=1,
                    steps=["Ejecutar ensayo"],
                    observations=str(row["observations"]),
                    weekday=row["weekday"],
                    week_ordinal=row["week_ordinal"],
                    source_module="prefabricados",
                    source_table="inspection_plan_entries",
                    source_id=str(row["id"]),
                    active=bool(row["active"]),
                )
        return imported

    def _upsert_legacy(
        self,
        connection: sqlite3.Connection,
        *,
        assay_id: int | None,
        legacy_name: str,
        module_ids: tuple[str, ...],
        responsible: str,
        frequency: str,
        interval: int,
        start_date: str,
        duration_days: int,
        steps: list[str],
        source_module: str,
        source_table: str,
        source_id: str,
        active: bool,
        method_id: int | None = None,
        material_type_id: int | None = None,
        observations: str = "",
        weekday: int | None = None,
        week_ordinal: int | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        existing = connection.execute(
            """
            SELECT id FROM pie_plans
            WHERE source_module_id = ? AND source_table = ? AND source_id = ?
            """,
            (source_module, source_table, source_id),
        ).fetchone()
        if existing is not None:
            return 0
        cursor = connection.execute(
            """
            INSERT INTO pie_plans (
                assay_id, method_id, material_type_id, legacy_name, responsible,
                frequency, recurrence_interval, start_date, duration_days,
                weekday, week_ordinal, observations, active, source_module_id,
                source_table, source_id, created_at, updated_at, deactivated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assay_id, method_id, material_type_id, legacy_name, responsible,
                PieFrequency(frequency).value, interval, start_date, duration_days,
                weekday, week_ordinal, observations, int(active), source_module,
                source_table, source_id, now, now, None if active else now,
            ),
        )
        plan_id = int(cursor.lastrowid)
        connection.executemany(
            "INSERT INTO pie_plan_modules (plan_id, module_id) VALUES (?, ?)",
            [(plan_id, module_id) for module_id in module_ids],
        )
        connection.executemany(
            "INSERT INTO pie_plan_steps (plan_id, day_number, description) VALUES (?, ?, ?)",
            [(plan_id, index, text) for index, text in enumerate(steps, 1)],
        )
        return 1

    @staticmethod
    def _prefabricados_frequency(row: sqlite3.Row) -> tuple[str, int]:
        kind = str(row["frequency_type"])
        if kind == "DAILY":
            return PieFrequency.DAILY.value, 1
        if kind == "WEEKLY":
            return PieFrequency.WEEKLY.value, 1
        if kind == "MONTHLY":
            return PieFrequency.MONTHLY.value, 1
        return PieFrequency.CUSTOM_MONTHS.value, int(row["month_interval"] or 1)

    @staticmethod
    def _prefabricados_start(row: sqlite3.Row) -> date:
        if row["reference_date"]:
            return date.fromisoformat(str(row["reference_date"]))
        created = str(row["created_at"])
        base = datetime.fromisoformat(created).date() if created else date.today()
        weekday = row["weekday"]
        if str(row["frequency_type"]) == "WEEKLY" and weekday is not None:
            return base + timedelta(days=(int(weekday) - base.weekday()) % 7)
        return base

    @classmethod
    def _starts_between(cls, plan: PiePlan, start: date, end: date) -> list[date]:
        if end < plan.start_date:
            return []
        if plan.frequency in {PieFrequency.DAILY, PieFrequency.CUSTOM_DAYS}:
            interval = 1 if plan.frequency == PieFrequency.DAILY else plan.interval
            first_index = max(0, (start - plan.start_date).days // interval)
            current = plan.start_date + timedelta(days=first_index * interval)
            while current < start:
                current += timedelta(days=interval)
            output = []
            while current <= end:
                output.append(current)
                current += timedelta(days=interval)
            return output
        if plan.frequency == PieFrequency.WEEKLY:
            interval_days = plan.interval * 7
            first_index = max(0, (start - plan.start_date).days // interval_days)
            current = plan.start_date + timedelta(days=first_index * interval_days)
            while current < start:
                current += timedelta(days=interval_days)
            output = []
            while current <= end:
                output.append(current)
                current += timedelta(days=interval_days)
            return output

        month_interval = 1 if plan.frequency == PieFrequency.MONTHLY else plan.interval
        start_index = plan.start_date.year * 12 + plan.start_date.month - 1
        range_index = start.year * 12 + start.month - 1
        occurrence_index = start_index + max(0, (range_index - start_index) // month_interval) * month_interval
        output = []
        while occurrence_index <= end.year * 12 + end.month - 1:
            year, zero_month = divmod(occurrence_index, 12)
            month = zero_month + 1
            current = cls._monthly_date(plan, year, month)
            if current >= plan.start_date and start <= current <= end:
                output.append(current)
            occurrence_index += month_interval
        return output

    @staticmethod
    def _monthly_date(plan: PiePlan, year: int, month: int) -> date:
        last = monthrange(year, month)[1]
        if plan.weekday is None or plan.week_ordinal is None:
            return date(year, month, min(plan.start_date.day, last))
        first = date(year, month, 1)
        day = 1 + (plan.weekday - first.weekday()) % 7 + (plan.week_ordinal - 1) * 7
        if day > last:
            day -= 7
        return date(year, month, day)

    @classmethod
    def _is_start(cls, plan: PiePlan, value: date) -> bool:
        return value in cls._starts_between(plan, value, value)

    @classmethod
    def _validate_occurrence(
        cls, plan: PiePlan | None, occurrence_start: date, day_number: int
    ) -> None:
        if plan is None or not plan.active:
            raise ValueError("La entrada PIE no existe o está inactiva.")
        if not 1 <= day_number <= plan.duration_days:
            raise ValueError("El día de la ocurrencia PIE no es válido.")
        if not cls._is_start(plan, occurrence_start):
            raise ValueError("La fecha no corresponde a la periodicidad del PIE.")

    @staticmethod
    def _validate(plan: PiePlan, *, require_catalog: bool) -> None:
        if require_catalog and plan.assay_id is None:
            raise ValueError("Las nuevas entradas PIE deben seleccionar un ensayo del catálogo.")
        if not tuple(plan.module_ids):
            raise ValueError("La entrada PIE debe aplicar al menos a un área.")
        if not plan.responsible.strip():
            raise ValueError("El responsable es obligatorio.")
        if int(plan.interval) < 1:
            raise ValueError("El intervalo debe ser mayor que cero.")
        if not 1 <= int(plan.duration_days) <= 365:
            raise ValueError("La duración debe estar entre 1 y 365 días.")
        if len(plan.steps) != int(plan.duration_days) or any(not item.strip() for item in plan.steps):
            raise ValueError("Debe describir una actividad por cada día de duración.")

    @staticmethod
    def _validate_references(connection: sqlite3.Connection, plan: PiePlan) -> None:
        if connection.execute("SELECT 1 FROM assays WHERE id = ?", (plan.assay_id,)).fetchone() is None:
            raise ValueError("El ensayo seleccionado ya no existe en el catálogo.")
        placeholders = ",".join("?" for _ in plan.module_ids)
        count = int(connection.execute(
            f"SELECT COUNT(*) FROM suite_modules WHERE id IN ({placeholders})",
            plan.module_ids,
        ).fetchone()[0])
        if count != len(plan.module_ids):
            raise ValueError("Una de las áreas seleccionadas no existe.")
        if plan.material_object_id is not None:
            material = connection.execute(
                "SELECT material_type_id FROM material_objects WHERE id = ? AND active = 1",
                (plan.material_object_id,),
            ).fetchone()
            if material is None:
                raise ValueError("El material concreto seleccionado no existe.")
            if plan.material_type_id not in {None, int(material["material_type_id"])}:
                raise ValueError("El material concreto no pertenece al tipo seleccionado.")

    @staticmethod
    def _module_tuple(value: str | Iterable[str] | None) -> tuple[str, ...]:
        if value is None:
            return ()
        return (value,) if isinstance(value, str) else tuple(dict.fromkeys(value))

    @staticmethod
    def _row_to_plan(connection: sqlite3.Connection, row: sqlite3.Row) -> PiePlan:
        plan_id = int(row["id"])
        modules = tuple(str(item[0]) for item in connection.execute(
            "SELECT module_id FROM pie_plan_modules WHERE plan_id = ? ORDER BY module_id",
            (plan_id,),
        ))
        steps = [str(item[0]) for item in connection.execute(
            "SELECT description FROM pie_plan_steps WHERE plan_id = ? ORDER BY day_number",
            (plan_id,),
        )]
        return PiePlan(
            id=plan_id,
            assay_id=int(row["assay_id"]) if row["assay_id"] is not None else None,
            method_id=int(row["method_id"]) if row["method_id"] is not None else None,
            material_type_id=(
                int(row["material_type_id"]) if row["material_type_id"] is not None else None
            ),
            material_object_id=(
                int(row["material_object_id"]) if row["material_object_id"] is not None else None
            ),
            module_ids=modules,
            responsible=str(row["responsible"]),
            frequency=PieFrequency(str(row["frequency"])),
            interval=int(row["recurrence_interval"]),
            start_date=date.fromisoformat(str(row["start_date"])),
            duration_days=int(row["duration_days"]),
            steps=steps,
            observations=str(row["observations"]),
            assay_name=str(row["assay_name"] or ""),
            material_name=str(row["material_name"] or ""),
            legacy_name=str(row["legacy_name"]),
            active=bool(row["active"]),
            weekday=int(row["weekday"]) if row["weekday"] is not None else None,
            week_ordinal=(
                int(row["week_ordinal"]) if row["week_ordinal"] is not None else None
            ),
            source_module_id=(
                str(row["source_module_id"]) if row["source_module_id"] else None
            ),
            source_table=str(row["source_table"]),
            source_id=str(row["source_id"]),
        )
