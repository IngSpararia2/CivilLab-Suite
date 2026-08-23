from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .database import CoreDatabase
from .pie import PiePlan, PieService


ACCEPTABLE_RESULT_STATUSES = frozenset({"VALID", "APPROVED", "ACCEPTED", "FINAL"})


@dataclass(frozen=True, slots=True)
class SharedResult:
    id: int
    assay_id: int
    method_id: int | None
    material_object_id: int
    tested_on: date
    origin_module_id: str
    source_type: str
    source_id: str
    status: str
    report_reference: str
    valid_until: date | None


@dataclass(frozen=True, slots=True)
class Satisfaction:
    result_id: int
    plan_id: int
    occurrence_start: date
    match_basis: str


class SharedResultService:
    """Registry of pointers to specialized results; it never copies technical values."""

    def __init__(self, database: CoreDatabase, pie_service: PieService | None = None):
        self.database = database
        self.pie_service = pie_service or PieService(database)

    def register(
        self,
        *,
        assay_id: int,
        material_object_id: int,
        tested_on: date,
        origin_module_id: str,
        source_type: str,
        source_id: str,
        status: str,
        method_id: int | None = None,
        report_reference: str = "",
        valid_until: date | None = None,
    ) -> SharedResult:
        normalized_status = status.strip().upper()
        if not source_type.strip() or not source_id.strip():
            raise ValueError("El tipo y el identificador del registro fuente son obligatorios.")
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO shared_results (
                    assay_id, method_id, material_object_id, tested_on,
                    origin_module_id, source_type, source_id, status,
                    report_reference, valid_until, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(origin_module_id, source_type, source_id) DO UPDATE SET
                    assay_id = excluded.assay_id,
                    method_id = excluded.method_id,
                    material_object_id = excluded.material_object_id,
                    tested_on = excluded.tested_on,
                    status = excluded.status,
                    report_reference = excluded.report_reference,
                    valid_until = excluded.valid_until
                """,
                (
                    assay_id, method_id, material_object_id, tested_on.isoformat(),
                    origin_module_id, source_type.strip(), source_id.strip(),
                    normalized_status, report_reference.strip(),
                    valid_until.isoformat() if valid_until else None, now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM shared_results
                WHERE origin_module_id = ? AND source_type = ? AND source_id = ?
                """,
                (origin_module_id, source_type.strip(), source_id.strip()),
            ).fetchone()
        assert row is not None
        return self._row(row)

    def satisfy_compatible_obligations(self, result_id: int) -> list[Satisfaction]:
        result = self.get(result_id)
        if result is None:
            raise ValueError("El resultado compartido no existe.")
        if result.status not in ACCEPTABLE_RESULT_STATUSES:
            return []
        if result.valid_until is not None and result.valid_until < result.tested_on:
            return []

        matches: list[tuple[PiePlan, date]] = []
        for plan in self.pie_service.list_plans():
            if not self._compatible_identity(plan, result):
                continue
            occurrence_start = self._window_occurrence(plan, result.tested_on)
            if occurrence_start is not None:
                matches.append((plan, occurrence_start))

        now = datetime.now(timezone.utc).isoformat()
        basis = "material_object+canonical_assay+compatible_method+recurrence_window+valid_status"
        with self.database.connect() as connection:
            for plan, occurrence_start in matches:
                assert plan.id is not None
                connection.execute(
                    """
                    INSERT INTO pie_result_satisfactions (
                        result_id, plan_id, occurrence_start, matched_at, match_basis
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(result_id, plan_id, occurrence_start) DO UPDATE SET
                        matched_at = excluded.matched_at,
                        match_basis = excluded.match_basis
                    """,
                    (result.id, plan.id, occurrence_start.isoformat(), now, basis),
                )
        return [
            Satisfaction(result.id, int(plan.id), occurrence_start, basis)
            for plan, occurrence_start in matches if plan.id is not None
        ]

    def get(self, result_id: int) -> SharedResult | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM shared_results WHERE id = ?", (result_id,)
            ).fetchone()
        return self._row(row) if row is not None else None

    @staticmethod
    def _compatible_identity(plan: PiePlan, result: SharedResult) -> bool:
        if plan.assay_id != result.assay_id:
            return False
        if plan.material_object_id != result.material_object_id:
            return False
        # Conservative rule: a method-constrained obligation only accepts that exact method.
        if plan.method_id is not None and plan.method_id != result.method_id:
            return False
        return True

    @classmethod
    def _window_occurrence(cls, plan: PiePlan, tested_on: date) -> date | None:
        lookback = (
            max(370, plan.interval * 32 + 32)
            if plan.frequency.value.endswith("months")
            else max(14, plan.interval * 8)
        )
        starts = PieService._starts_between(
            plan, tested_on - timedelta(days=lookback), tested_on
        )
        if not starts:
            return None
        occurrence = starts[-1]
        following = cls._following_start(plan, occurrence)
        if occurrence <= tested_on < following:
            return occurrence
        return None

    @staticmethod
    def _following_start(plan: PiePlan, occurrence: date) -> date:
        probe_end = occurrence + timedelta(days=800)
        starts = PieService._starts_between(plan, occurrence + timedelta(days=1), probe_end)
        return starts[0] if starts else probe_end

    @staticmethod
    def _row(row) -> SharedResult:
        return SharedResult(
            id=int(row["id"]),
            assay_id=int(row["assay_id"]),
            method_id=int(row["method_id"]) if row["method_id"] is not None else None,
            material_object_id=int(row["material_object_id"]),
            tested_on=date.fromisoformat(str(row["tested_on"])),
            origin_module_id=str(row["origin_module_id"]),
            source_type=str(row["source_type"]),
            source_id=str(row["source_id"]),
            status=str(row["status"]),
            report_reference=str(row["report_reference"]),
            valid_until=(
                date.fromisoformat(str(row["valid_until"])) if row["valid_until"] else None
            ),
        )
