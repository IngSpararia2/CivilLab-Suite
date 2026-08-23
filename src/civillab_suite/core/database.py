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


SCHEMA_VERSION = 1


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

                CREATE INDEX IF NOT EXISTS idx_assay_methods_assay
                    ON assay_methods(assay_id);
                CREATE INDEX IF NOT EXISTS idx_standard_assays_assay
                    ON standard_assays(assay_id);
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
                SELECT laboratory_test_id, standard_id
                FROM test_applicabilities ORDER BY laboratory_test_id, standard_id
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
            required = {"standard_references", "laboratory_tests", "test_applicabilities"}
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

            assay_ids: set[int] = set()
            method_ids: set[int] = set()
            for item in test_rows:
                assay_id = self._upsert_assay(target, item["name"])
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

            target.execute(
                """
                INSERT INTO migration_runs (source_key, fingerprint, applied_at)
                VALUES ('prefabricados_catalog_v1', ?, ?)
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

    def counts(self) -> dict[str, int]:
        tables = (
            "suite_modules", "laboratories", "assays", "assay_methods", "standards",
            "assay_modules", "standard_modules", "standard_assays", "method_standards",
        )
        with self.connect() as connection:
            return {
                table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in tables
            }
