from __future__ import annotations

import sqlite3

from civillab_suite.core.database import CoreDatabase
from civillab_suite.registry import create_default_registry


def _ready_database(path):
    database = CoreDatabase(path)
    database.initialize()
    database.sync_modules(create_default_registry().all())
    return database


def test_assay_can_belong_to_multiple_modules_without_duplication(tmp_path):
    database = _ready_database(tmp_path / "core.sqlite3")

    first_id = database.link_assay_to_module("Granulometría", "concretos")
    assert database.link_assay_to_module("Granulometría", "prefabricados") == first_id
    assert database.link_assay_to_module("Granulometría", "suelos") == first_id
    database.link_assay_to_module("  GRANULOMETRIA  ", "concretos")

    counts = database.counts()
    assert counts["assays"] == 1
    assert counts["assay_modules"] == 3


def test_prefabricados_catalog_sync_is_idempotent_and_preserves_relations(
    monkeypatch, tmp_path
):
    from precon_lab import database as prefabricados_database

    source_directory = tmp_path / "prefabricados-source"
    monkeypatch.setenv("PRECON_LAB_DATA_DIR", str(source_directory))
    prefabricados_database._engine = None
    prefabricados_database._SessionFactory = None
    prefabricados_database.initialize_database()

    database = _ready_database(tmp_path / "core.sqlite3")
    source = source_directory / "precon_lab.db"
    with sqlite3.connect(source) as connection:
        expected_standards = connection.execute(
            "SELECT COUNT(*) FROM prefabricados_standard_references"
        ).fetchone()[0]
        expected_methods = connection.execute(
            "SELECT COUNT(*) FROM prefabricados_laboratory_tests"
        ).fetchone()[0]

    first = database.sync_prefabricados_catalog(source)
    first_counts = database.counts()
    second = database.sync_prefabricados_catalog(source)

    assert first.standards == expected_standards
    assert first.methods == expected_methods
    assert first.fingerprint == second.fingerprint
    assert database.counts() == first_counts
    assert first_counts["standard_modules"] == 41
    assert first_counts["assay_modules"] == first.assays
    assert first_counts["standard_assays"] > 0
    assert first_counts["method_standards"] >= first_counts["standard_assays"]

    with database.connect() as connection:
        duplicate_natural_keys = connection.execute(
            """
            SELECT issuer_key, code_key, edition_key, COUNT(*) AS total
            FROM standards
            GROUP BY issuer_key, code_key, edition_key
            HAVING total > 1
            """
        ).fetchall()
    assert duplicate_natural_keys == []
