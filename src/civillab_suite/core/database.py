from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from civillab_suite.registry import ModuleDescriptor


SCHEMA_VERSION = 3


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.strip())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().split())


@dataclass(frozen=True, slots=True)
class CatalogSyncResult:
    standards: int
    assays: int
    methods: int
    fingerprint: str


class CoreDatabase:
    """Small SQLite core for genuinely shared suite metadata.

    Technical production/result tables stay in their original modules.  This core
    only owns the module registry and normalized catalog relationships.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS suite_modules (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS laboratories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS assays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS standards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issuer TEXT NOT NULL DEFAULT '',
                    code TEXT NOT NULL,
                    edition TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    source_reference TEXT NOT NULL DEFAULT '',
                    location_reference TEXT NOT NULL DEFAULT '',
                    verification_status TEXT NOT NULL DEFAULT '',
                    issuer_key TEXT NOT NULL,
                    code_key TEXT NOT NULL,
                    edition_key TEXT NOT NULL,
                    UNIQUE (issuer_key, code_key, edition_key)
                );

                CREATE TABLE IF NOT EXISTS assay_methods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assay_id INTEGER NOT NULL REFERENCES assays(id) ON DELETE RESTRICT,
                    module_id TEXT NOT NULL REFERENCES suite_modules(id) ON DELETE RESTRICT,
                    source_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    equipment TEXT NOT NULL DEFAULT '',
                    procedure_summary TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    UNIQUE (module_id, source_key)
                );

                CREATE TABLE IF NOT EXISTS assay_modules (
                    assay_id INTEGER NOT NULL REFERENCES assays(id) ON DELETE CASCADE,
                    module_id TEXT NOT NULL REFERENCES suite_modules(id) ON DELETE CASCADE,
                    source TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (assay_id, module_id)
                );

                CREATE TABLE IF NOT EXISTS standard_modules (
                    standard_id INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
                    module_id TEXT NOT NULL REFERENCES suite_modules(id) ON DELETE CASCADE,
                    source TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (standard_id, module_id)
                );

                CREATE TABLE IF NOT EXISTS standard_assays (
                    standard_id INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
                    assay_id INTEGER NOT NULL REFERENCES assays(id) ON DELETE CASCADE,
                    source TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (standard_id, assay_id)
                );

                CREATE TABLE IF NOT EXISTS method_standards (
                    method_id INTEGER NOT NULL REFERENCES assay_methods(id) ON DELETE CASCADE,
                    standard_id INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
                    relation_type TEXT NOT NULL DEFAULT 'reference',
                    PRIMARY KEY (method_id, standard_id)
                );

                CREATE TABLE IF NOT EXISTS migration_runs (
                    source_key TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_seed_versions (
                    seed_key TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS material_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    canonical_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS material_type_modules (
                    material_type_id INTEGER NOT NULL
                        REFERENCES material_types(id) ON DELETE CASCADE,
                    module_id TEXT NOT NULL
                        REFERENCES suite_modules(id) ON DELETE CASCADE,
                    source TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (material_type_id, module_id)
                );

                CREATE TABLE IF NOT EXISTS material_objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_type_id INTEGER NOT NULL
                        REFERENCES material_types(id) ON DELETE RESTRICT,
                    code TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    supplier_source TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (material_type_id, code)
                );

                CREATE TABLE IF NOT EXISTS assay_material_types (
                    assay_id INTEGER NOT NULL REFERENCES assays(id) ON DELETE CASCADE,
                    material_type_id INTEGER NOT NULL
                        REFERENCES material_types(id) ON DELETE CASCADE,
                    module_id TEXT NOT NULL REFERENCES suite_modules(id) ON DELETE CASCADE,
                    standard_id INTEGER REFERENCES standards(id) ON DELETE SET NULL,
                    normative_frequency TEXT NOT NULL DEFAULT '',
                    procedure_detail TEXT NOT NULL DEFAULT '',
                    preferred INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (assay_id, material_type_id, module_id)
                );

                CREATE TABLE IF NOT EXISTS catalog_requirements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_key TEXT NOT NULL,
                    material_type_id INTEGER NOT NULL
                        REFERENCES material_types(id) ON DELETE CASCADE,
                    assay_id INTEGER NOT NULL REFERENCES assays(id) ON DELETE CASCADE,
                    standard_id INTEGER REFERENCES standards(id) ON DELETE SET NULL,
                    module_id TEXT NOT NULL REFERENCES suite_modules(id) ON DELETE CASCADE,
                    minimum REAL,
                    maximum REAL,
                    unit TEXT NOT NULL DEFAULT '',
                    comparison_operator TEXT NOT NULL DEFAULT '',
                    requirement_text TEXT NOT NULL DEFAULT '',
                    condition_text TEXT NOT NULL DEFAULT '',
                    aggregation TEXT NOT NULL DEFAULT '',
                    age_days INTEGER,
                    grading TEXT NOT NULL DEFAULT '',
                    source_detail TEXT NOT NULL DEFAULT '',
                    verification_status TEXT NOT NULL DEFAULT '',
                    UNIQUE (module_id, source_key)
                );

                CREATE TABLE IF NOT EXISTS pie_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assay_id INTEGER REFERENCES assays(id) ON DELETE RESTRICT,
                    method_id INTEGER REFERENCES assay_methods(id) ON DELETE SET NULL,
                    material_type_id INTEGER REFERENCES material_types(id) ON DELETE RESTRICT,
                    material_object_id INTEGER REFERENCES material_objects(id) ON DELETE RESTRICT,
                    legacy_name TEXT NOT NULL DEFAULT '',
                    responsible TEXT NOT NULL DEFAULT '',
                    frequency TEXT NOT NULL CHECK(frequency IN (
                        'daily', 'weekly', 'monthly', 'custom_days', 'custom_months'
                    )),
                    recurrence_interval INTEGER NOT NULL CHECK(recurrence_interval > 0),
                    start_date TEXT NOT NULL,
                    duration_days INTEGER NOT NULL DEFAULT 1
                        CHECK(duration_days BETWEEN 1 AND 365),
                    weekday INTEGER,
                    week_ordinal INTEGER,
                    observations TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    source_module_id TEXT REFERENCES suite_modules(id) ON DELETE RESTRICT,
                    source_table TEXT NOT NULL DEFAULT '',
                    source_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deactivated_at TEXT,
                    UNIQUE (source_module_id, source_table, source_id)
                );

                CREATE TABLE IF NOT EXISTS pie_plan_modules (
                    plan_id INTEGER NOT NULL REFERENCES pie_plans(id) ON DELETE CASCADE,
                    module_id TEXT NOT NULL REFERENCES suite_modules(id) ON DELETE CASCADE,
                    PRIMARY KEY (plan_id, module_id)
                );

                CREATE TABLE IF NOT EXISTS pie_plan_steps (
                    plan_id INTEGER NOT NULL REFERENCES pie_plans(id) ON DELETE CASCADE,
                    day_number INTEGER NOT NULL CHECK(day_number > 0),
                    description TEXT NOT NULL,
                    PRIMARY KEY (plan_id, day_number)
                );

                CREATE TABLE IF NOT EXISTS pie_occurrence_status (
                    plan_id INTEGER NOT NULL REFERENCES pie_plans(id) ON DELETE RESTRICT,
                    occurrence_start TEXT NOT NULL,
                    day_number INTEGER NOT NULL CHECK(day_number > 0),
                    rescheduled_date TEXT,
                    completed_at TEXT,
                    notes TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (plan_id, occurrence_start, day_number)
                );

                CREATE TABLE IF NOT EXISTS shared_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assay_id INTEGER NOT NULL REFERENCES assays(id) ON DELETE RESTRICT,
                    method_id INTEGER REFERENCES assay_methods(id) ON DELETE SET NULL,
                    material_object_id INTEGER NOT NULL
                        REFERENCES material_objects(id) ON DELETE RESTRICT,
                    tested_on TEXT NOT NULL,
                    origin_module_id TEXT NOT NULL
                        REFERENCES suite_modules(id) ON DELETE RESTRICT,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report_reference TEXT NOT NULL DEFAULT '',
                    valid_until TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (origin_module_id, source_type, source_id)
                );

                CREATE TABLE IF NOT EXISTS pie_result_satisfactions (
                    result_id INTEGER NOT NULL REFERENCES shared_results(id) ON DELETE RESTRICT,
                    plan_id INTEGER NOT NULL REFERENCES pie_plans(id) ON DELETE RESTRICT,
                    occurrence_start TEXT NOT NULL,
                    matched_at TEXT NOT NULL,
                    match_basis TEXT NOT NULL,
                    PRIMARY KEY (result_id, plan_id, occurrence_start)
                );

                CREATE INDEX IF NOT EXISTS idx_assay_methods_assay
                    ON assay_methods(assay_id);
                CREATE INDEX IF NOT EXISTS idx_standard_assays_assay
                    ON standard_assays(assay_id);
                CREATE INDEX IF NOT EXISTS idx_assay_material_module
                    ON assay_material_types(module_id, assay_id);
                CREATE INDEX IF NOT EXISTS idx_catalog_requirements_lookup
                    ON catalog_requirements(module_id, assay_id, material_type_id);
                CREATE INDEX IF NOT EXISTS idx_pie_plans_active_start
                    ON pie_plans(active, start_date);
                CREATE INDEX IF NOT EXISTS idx_pie_plan_modules_module
                    ON pie_plan_modules(module_id, plan_id);
                CREATE INDEX IF NOT EXISTS idx_shared_results_match
                    ON shared_results(material_object_id, assay_id, tested_on, status);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (version, applied_at)
                VALUES (?, ?)
                """,
                (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )

    def sync_modules(self, modules: Iterable["ModuleDescriptor"]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO suite_modules (id, display_name, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name = excluded.display_name,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                ((item.id, item.name, item.status.value, now) for item in modules),
            )

    def _upsert_assay(self, connection: sqlite3.Connection, name: str) -> int:
        normalized_name = _normalized(name)
        connection.execute(
            """
            INSERT INTO assays (canonical_name, normalized_name)
            VALUES (?, ?)
            ON CONFLICT(normalized_name) DO UPDATE SET
                canonical_name = excluded.canonical_name
            """,
            (name.strip(), normalized_name),
        )
        row = connection.execute(
            "SELECT id FROM assays WHERE normalized_name = ?", (normalized_name,)
        ).fetchone()
        assert row is not None
        return int(row["id"])

    def upsert_assay(self, name: str) -> int:
        """Create or update one canonical assay without exposing catalog CRUD in UI."""

        with self.connect() as connection:
            return self._upsert_assay(connection, name)

    def link_assay_to_module(
        self,
        assay_name: str,
        module_id: str,
        *,
        source: str = "manual",
    ) -> int:
        with self.connect() as connection:
            assay_id = self._upsert_assay(connection, assay_name)
            connection.execute(
                """
                INSERT INTO assay_modules (assay_id, module_id, source)
                VALUES (?, ?, ?)
                ON CONFLICT(assay_id, module_id) DO UPDATE SET source = excluded.source
                """,
                (assay_id, module_id, source),
            )
        return assay_id

    def _upsert_standard(self, connection: sqlite3.Connection, row: sqlite3.Row) -> int:
        identity = (_normalized(row["issuer"]), _normalized(row["code"]), _normalized(row["edition"]))
        connection.execute(
            """
            INSERT INTO standards (
                issuer, code, edition, title, source_reference, location_reference,
                verification_status, issuer_key, code_key, edition_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(issuer_key, code_key, edition_key) DO UPDATE SET
                title = excluded.title,
                source_reference = excluded.source_reference,
                location_reference = excluded.location_reference,
                verification_status = excluded.verification_status
            """,
            (
                row["issuer"], row["code"], row["edition"], row["title"],
                row["source_reference"], row["location_reference"],
                row["verification_status"], *identity,
            ),
        )
        target = connection.execute(
            """
            SELECT id FROM standards
            WHERE issuer_key = ? AND code_key = ? AND edition_key = ?
            """,
            identity,
        ).fetchone()
        assert target is not None
        return int(target["id"])

    @staticmethod
    def _catalog_fingerprint(source: sqlite3.Connection) -> str:
        payload: dict[str, list[list[object]]] = {}
        queries = {
            "standards": """
                SELECT id, code, title, issuer, edition, source_reference,
                       location_reference, verification_status
                FROM standard_references ORDER BY id
            """,
            "tests": """
                SELECT id, code, name, standard_id, equipment, procedure_summary, active
                FROM laboratory_tests ORDER BY id
            """,
            "applicabilities": """
                SELECT material_type_id, laboratory_test_id, standard_id,
                       normative_frequency, procedure_detail, preferred
                FROM test_applicabilities
                ORDER BY material_type_id, laboratory_test_id, standard_id
            """,
            "materials": """
                SELECT id, code, name, active FROM material_types ORDER BY id
            """,
            "requirements": """
                SELECT seed_key, material_type_id, laboratory_test_id, standard_id,
                       minimum, maximum, unit, operator, requirement_text, condition,
                       aggregation, age_days, grading, source_detail, verification_status
                FROM test_requirements ORDER BY seed_key
            """,
        }
        for key, query in queries.items():
            payload[key] = [list(row) for row in source.execute(query)]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def sync_prefabricados_catalog(self, source_path: Path) -> CatalogSyncResult:
        source_path = Path(source_path)
        if not source_path.is_file():
            return CatalogSyncResult(0, 0, 0, "")

        source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        try:
            required = {
                "material_types", "standard_references", "laboratory_tests",
                "test_applicabilities", "test_requirements",
            }
            existing = {
                row[0]
                for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            if not required.issubset(existing):
                return CatalogSyncResult(0, 0, 0, "")

            fingerprint = self._catalog_fingerprint(source)
            standard_rows = list(
                source.execute(
                    """
                    SELECT id, code, title, issuer, edition, source_reference,
                           location_reference, verification_status
                    FROM standard_references ORDER BY id
                    """
                )
            )
            test_rows = list(
                source.execute(
                    """
                    SELECT id, code, name, standard_id, equipment, procedure_summary, active
                    FROM laboratory_tests ORDER BY id
                    """
                )
            )
            relation_rows = list(
                source.execute(
                    """
                    SELECT laboratory_test_id, standard_id
                    FROM test_applicabilities
                    WHERE standard_id IS NOT NULL
                    """
                )
            )
            material_rows = list(
                source.execute(
                    "SELECT id, code, name, active FROM material_types ORDER BY id"
                )
            )
            applicability_rows = list(
                source.execute(
                    """
                    SELECT material_type_id, laboratory_test_id, standard_id,
                           normative_frequency, procedure_detail, preferred
                    FROM test_applicabilities
                    ORDER BY material_type_id, laboratory_test_id
                    """
                )
            )
            requirement_rows = list(
                source.execute(
                    """
                    SELECT seed_key, material_type_id, laboratory_test_id, standard_id,
                           minimum, maximum, unit, operator, requirement_text, condition,
                           aggregation, age_days, grading, source_detail,
                           verification_status
                    FROM test_requirements ORDER BY seed_key
                    """
                )
            )
        finally:
            source.close()

        relations: dict[int, set[int]] = {}
        for item in relation_rows:
            relations.setdefault(int(item["laboratory_test_id"]), set()).add(
                int(item["standard_id"])
            )
        for item in test_rows:
            if item["standard_id"] is not None:
                relations.setdefault(int(item["id"]), set()).add(int(item["standard_id"]))

        with self.connect() as target:
            module_exists = target.execute(
                "SELECT 1 FROM suite_modules WHERE id = 'prefabricados'"
            ).fetchone()
            if module_exists is None:
                raise RuntimeError("El registro de módulos debe sincronizarse antes del catálogo.")

            standard_ids: dict[int, int] = {}
            for item in standard_rows:
                standard_id = self._upsert_standard(target, item)
                standard_ids[int(item["id"])] = standard_id
                target.execute(
                    """
                    INSERT INTO standard_modules (standard_id, module_id, source)
                    VALUES (?, 'prefabricados', 'precon_lab')
                    ON CONFLICT(standard_id, module_id) DO UPDATE SET source = excluded.source
                    """,
                    (standard_id,),
                )

            material_ids: dict[int, int] = {}
            for item in material_rows:
                code = str(item["code"])
                target.execute(
                    """
                    INSERT INTO material_types (
                        code, canonical_name, normalized_name, active
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                        canonical_name = excluded.canonical_name,
                        normalized_name = excluded.normalized_name,
                        active = excluded.active
                    """,
                    (
                        code, item["name"], _normalized(item["name"]),
                        int(bool(item["active"])),
                    ),
                )
                material = target.execute(
                    "SELECT id FROM material_types WHERE code = ?", (code,)
                ).fetchone()
                assert material is not None
                material_id = int(material["id"])
                material_ids[int(item["id"])] = material_id
                target.execute(
                    """
                    INSERT INTO material_type_modules (material_type_id, module_id, source)
                    VALUES (?, 'prefabricados', 'precon_lab')
                    ON CONFLICT(material_type_id, module_id)
                    DO UPDATE SET source = excluded.source
                    """,
                    (material_id,),
                )

            assay_ids: set[int] = set()
            method_ids: set[int] = set()
            source_assay_ids: dict[int, int] = {}
            for item in test_rows:
                assay_id = self._upsert_assay(target, item["name"])
                source_assay_ids[int(item["id"])] = assay_id
                assay_ids.add(assay_id)
                target.execute(
                    """
                    INSERT INTO assay_modules (assay_id, module_id, source)
                    VALUES (?, 'prefabricados', 'precon_lab')
                    ON CONFLICT(assay_id, module_id) DO UPDATE SET source = excluded.source
                    """,
                    (assay_id,),
                )
                target.execute(
                    """
                    INSERT INTO assay_methods (
                        assay_id, module_id, source_key, display_name, equipment,
                        procedure_summary, active
                    ) VALUES (?, 'prefabricados', ?, ?, ?, ?, ?)
                    ON CONFLICT(module_id, source_key) DO UPDATE SET
                        assay_id = excluded.assay_id,
                        display_name = excluded.display_name,
                        equipment = excluded.equipment,
                        procedure_summary = excluded.procedure_summary,
                        active = excluded.active
                    """,
                    (
                        assay_id, item["code"], item["name"], item["equipment"],
                        item["procedure_summary"], int(bool(item["active"])),
                    ),
                )
                method = target.execute(
                    """
                    SELECT id FROM assay_methods
                    WHERE module_id = 'prefabricados' AND source_key = ?
                    """,
                    (item["code"],),
                ).fetchone()
                assert method is not None
                method_id = int(method["id"])
                method_ids.add(method_id)

                for source_standard_id in relations.get(int(item["id"]), set()):
                    standard_id = standard_ids.get(source_standard_id)
                    if standard_id is None:
                        continue
                    target.execute(
                        """
                        INSERT OR IGNORE INTO method_standards (method_id, standard_id)
                        VALUES (?, ?)
                        """,
                        (method_id, standard_id),
                    )
                    target.execute(
                        """
                        INSERT INTO standard_assays (standard_id, assay_id, source)
                        VALUES (?, ?, 'precon_lab')
                        ON CONFLICT(standard_id, assay_id) DO UPDATE SET source = excluded.source
                        """,
                        (standard_id, assay_id),
                    )

            for item in applicability_rows:
                assay_id = source_assay_ids.get(int(item["laboratory_test_id"]))
                material_id = material_ids.get(int(item["material_type_id"]))
                if assay_id is None or material_id is None:
                    continue
                standard_id = (
                    standard_ids.get(int(item["standard_id"]))
                    if item["standard_id"] is not None else None
                )
                for module_id in ("prefabricados",):
                    target.execute(
                        """
                        INSERT INTO assay_modules (assay_id, module_id, source)
                        VALUES (?, ?, 'core_catalog_v1')
                        ON CONFLICT(assay_id, module_id)
                        DO UPDATE SET source = excluded.source
                        """,
                        (assay_id, module_id),
                    )
                    target.execute(
                        """
                        INSERT INTO material_type_modules (
                            material_type_id, module_id, source
                        ) VALUES (?, ?, 'core_catalog_v1')
                        ON CONFLICT(material_type_id, module_id)
                        DO UPDATE SET source = excluded.source
                        """,
                        (material_id, module_id),
                    )
                    target.execute(
                        """
                        INSERT INTO assay_material_types (
                            assay_id, material_type_id, module_id, standard_id,
                            normative_frequency, procedure_detail, preferred, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'precon_lab_v1')
                        ON CONFLICT(assay_id, material_type_id, module_id) DO UPDATE SET
                            standard_id = excluded.standard_id,
                            normative_frequency = excluded.normative_frequency,
                            procedure_detail = excluded.procedure_detail,
                            preferred = excluded.preferred,
                            source = excluded.source
                        """,
                        (
                            assay_id, material_id, module_id, standard_id,
                            item["normative_frequency"], item["procedure_detail"],
                            int(bool(item["preferred"])),
                        ),
                    )

            for item in requirement_rows:
                assay_id = source_assay_ids.get(int(item["laboratory_test_id"]))
                material_id = material_ids.get(int(item["material_type_id"]))
                if assay_id is None or material_id is None:
                    continue
                standard_id = (
                    standard_ids.get(int(item["standard_id"]))
                    if item["standard_id"] is not None else None
                )
                target.execute(
                    """
                    INSERT INTO catalog_requirements (
                        source_key, material_type_id, assay_id, standard_id, module_id,
                        minimum, maximum, unit, comparison_operator, requirement_text,
                        condition_text, aggregation, age_days, grading, source_detail,
                        verification_status
                    ) VALUES (?, ?, ?, ?, 'prefabricados', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(module_id, source_key) DO UPDATE SET
                        material_type_id = excluded.material_type_id,
                        assay_id = excluded.assay_id,
                        standard_id = excluded.standard_id,
                        minimum = excluded.minimum,
                        maximum = excluded.maximum,
                        unit = excluded.unit,
                        comparison_operator = excluded.comparison_operator,
                        requirement_text = excluded.requirement_text,
                        condition_text = excluded.condition_text,
                        aggregation = excluded.aggregation,
                        age_days = excluded.age_days,
                        grading = excluded.grading,
                        source_detail = excluded.source_detail,
                        verification_status = excluded.verification_status
                    """,
                    (
                        item["seed_key"], material_id, assay_id, standard_id,
                        item["minimum"], item["maximum"], item["unit"], item["operator"],
                        item["requirement_text"], item["condition"], item["aggregation"],
                        item["age_days"], item["grading"], item["source_detail"],
                        item["verification_status"],
                    ),
                )

            target.execute(
                """
                INSERT INTO migration_runs (source_key, fingerprint, applied_at)
                VALUES ('prefabricados_catalog_v3', ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    applied_at = excluded.applied_at
                """,
                (fingerprint, datetime.now(timezone.utc).isoformat()),
            )

        return CatalogSyncResult(
            standards=len(standard_ids),
            assays=len(assay_ids),
            methods=len(method_ids),
            fingerprint=fingerprint,
        )

    def migration_applied(self, source_key: str) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM migration_runs WHERE source_key = ?", (source_key,)
            ).fetchone() is not None

    def counts(self) -> dict[str, int]:
        tables = (
            "suite_modules", "laboratories", "assays", "assay_methods", "standards",
            "assay_modules", "standard_modules", "standard_assays", "method_standards",
            "material_types", "material_objects", "assay_material_types", "pie_plans",
            "pie_plan_modules", "shared_results", "pie_result_satisfactions",
            "catalog_requirements",
        )
        with self.connect() as connection:
            return {
                table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in tables
            }
