"""Production workspace and recoverable migration from the three legacy databases.

All conversion happens on SQLite backup snapshots in a sibling staging directory.
Only a fully validated database is published. Original legacy files are untouched.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from civillab_suite.sqlite_support import connect

CONCRETE_TABLES = (
    "materials",
    "material_characterizations",
    "material_gradations",
    "design_groups",
    "mix_designs",
    "design_specifications",
    "productions",
    "specimens",
    "fresh_tests",
    "compression_results",
    "flexural_results",
    "specimen_checklist",
    "pie_inspection_plans",
    "pie_inspection_steps",
    "pie_occurrence_checklist",
)
PREFAB_TABLES = (
    "products",
    "production_batches",
    "sample_sets",
    "specimens",
    "workflow_tasks",
    "import_batches",
    "historical_tests",
    "historical_specimens",
    "test_results",
    "material_types",
    "standard_references",
    "laboratory_tests",
    "test_applicabilities",
    "test_requirements",
    "inspection_plan_entries",
)
UNIFIED_VERSION = 1


def legacy_reader(path: Path, domain: str) -> sqlite3.Connection:
    """Read old and namespaced catalogs through temporary compatibility views."""
    db = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for name in CONCRETE_TABLES if domain == "concretos" else PREFAB_TABLES:
        if f"{domain}_{name}" in tables:
            db.execute(f'CREATE TEMP VIEW "{name}" AS SELECT * FROM main."{domain}_{name}"')
    return db


def validate_sqlite(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchall()
        foreign = db.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != [("ok",)] or foreign:
            raise ValueError(
                f"Integridad SQLite inválida en {path.name}: {integrity}; FK={foreign}"
            )
        return {
            name: db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
            for (name,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }


def snapshot(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")


def ensure_domain_namespace(path: Path, domain: str) -> None:
    """Support direct legacy repository callers, with a recoverable snapshot."""
    if not path.is_file():
        return
    names = CONCRETE_TABLES if domain == "concretos" else PREFAB_TABLES
    with closing(sqlite3.connect(path)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # Shared material_types exists in Core and is not a legacy Prefab indicator.
    indicators = set(names) - {"material_types"}
    if not tables.intersection(indicators):
        return
    snapshot(path, path.parent / "backups" / f"{path.stem}-{domain}-{uuid4().hex}.sqlite3")
    rename_domain_tables(path, domain)


def is_unified(path: Path) -> bool:
    if not path.is_file():
        return False
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
        return (
            db.execute("SELECT 1 FROM sqlite_master WHERE name='workspace_migrations'").fetchone()
            is not None
            and db.execute(
                "SELECT 1 FROM workspace_migrations WHERE version=?", (UNIFIED_VERSION,)
            ).fetchone()
            is not None
        )


def prepare_sqlite_replacement(path: Path) -> None:
    """Flush old WAL before replacing its main file; fail if another writer is active."""
    if not path.is_file():
        return
    with connect(path) as db:
        busy, _, _ = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if busy:
            raise ValueError("La base está en uso; cierra otras instancias antes de restaurar.")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("BEGIN EXCLUSIVE")


def rename_domain_tables(path: Path, domain: str) -> None:
    """Upgrade an isolated legacy snapshot before combining namespaces."""
    names = CONCRETE_TABLES if domain == "concretos" else PREFAB_TABLES
    with connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        db.execute("BEGIN IMMEDIATE")
        for name in names:
            if name not in tables:
                continue
            target = f"{domain}_{name}"
            if target in tables:
                raise ValueError(f"Colisión de tablas: {name} / {target}; se requiere revisión.")
            db.execute(f'ALTER TABLE "{name}" RENAME TO "{target}"')


def _copy_domain(source: Path, target: Path, domain: str) -> dict[str, int]:
    counts = validate_sqlite(source)
    with closing(sqlite3.connect(source)) as src, connect(target) as dst:
        dst.execute("PRAGMA foreign_keys=OFF")
        dst.execute("BEGIN IMMEDIATE")
        objects = src.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type DESC"
        ).fetchall()
        for kind, name, table, sql in objects:
            if not table.startswith(domain + "_"):
                # Unknown legacy tables cannot be silently dropped.
                raise ValueError(f"Tabla legacy no reconocida: {table}")
            if kind == "table":
                dst.execute(sql)
                rows = src.execute(f'SELECT * FROM "{name}"').fetchall()
                if rows:
                    placeholders = ",".join("?" for _ in rows[0])
                    dst.executemany(f'INSERT INTO "{name}" VALUES ({placeholders})', rows)
            elif kind == "index":
                # Index names are database-global too.
                import re

                dst.execute(
                    re.sub(
                        r"(?<=INDEX )(?:(?:IF NOT EXISTS) )?[^ ]+",
                        f'"{domain}_{name}"',
                        sql,
                        count=1,
                    )
                )
            else:
                raise ValueError(f"Objeto legacy no reconocido: {kind} {name}")
        actual = {
            name: dst.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] for name in counts
        }
        if actual != counts:
            raise ValueError("Los conteos de migración no coinciden.")
        if src.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone():
            for table, sequence in src.execute("SELECT name,seq FROM sqlite_sequence"):
                if table in counts:
                    dst.execute(
                        "UPDATE sqlite_sequence SET seq=max(seq,?) WHERE name=?", (sequence, table)
                    )
    return counts


def initialize_workspace(path: Path) -> None:
    """Create structural seeds only. No example materials, designs or production."""
    from civillab_suite.core.catalog import CatalogService
    from civillab_suite.core.database import CoreDatabase
    from civillab_suite.registry import create_default_registry
    from concrete_mix_designer.data.calendar_repository import CalendarRepository
    from concrete_mix_designer.data.database import MaterialRepository
    from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
    from precon_lab.database import initialize_at

    core = CoreDatabase(path)
    core.initialize()
    core.sync_modules(create_default_registry().all())
    MaterialRepository(path, seed=False)
    LaboratoryRepository(path)
    CalendarRepository(path)
    initialize_at(path, seed_products=False)
    core.sync_prefabricados_catalog(path)
    CatalogService(core).apply_builtin_seed()
    from civillab_suite.core.pie import PieService

    pie = PieService(core)
    pie.import_prefabricados_legacy(path)
    pie.import_concretos_legacy(path)
    with connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS workspace_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, sources_json TEXT NOT NULL)"
        )
        db.execute(
            "INSERT OR IGNORE INTO workspace_migrations VALUES (?, ?, '{}')",
            (UNIFIED_VERSION, datetime.now(timezone.utc).isoformat()),
        )


def migrate_workspace(
    target: Path, concrete: Path | None = None, prefabricados: Path | None = None
) -> Path | None:
    target = Path(target)
    if is_unified(target):
        validate_sqlite(target)
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    sources = {
        name: path
        for name, path in {
            "core": target,
            "concretos": concrete,
            "prefabricados": prefabricados,
        }.items()
        if path is not None and path.is_file()
    }
    for path in sources.values():
        validate_sqlite(path)
    backup = None
    if sources:
        backup = (
            target.parent
            / "backups"
            / ("migration-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8])
        )
        for name, source in sources.items():
            snapshot(source, backup / f"{name}.sqlite3")
    with tempfile.TemporaryDirectory(prefix=".migration-", dir=target.parent) as temporary:
        stage = Path(temporary)
        unified = stage / "core.sqlite3"
        if target.is_file():
            snapshot(target, unified)
        counts = {}
        for domain in ("concretos", "prefabricados"):
            if domain not in sources:
                continue
            local = stage / f"{domain}.sqlite3"
            snapshot(sources[domain], local)
            rename_domain_tables(local, domain)
            counts[domain] = _copy_domain(local, unified, domain)
        initialize_workspace(unified)
        with connect(unified) as db:
            db.execute(
                "UPDATE workspace_migrations SET sources_json=? WHERE version=?",
                (json.dumps(counts), UNIFIED_VERSION),
            )
        validate_sqlite(unified)
        # All handles are closed before publishing the complete file on Windows.
        prepare_sqlite_replacement(target)
        os.replace(unified, target)
    return backup
