from __future__ import annotations

import sqlite3
from pathlib import Path

from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository


def test_create_and_list_persistent_design_groups(tmp_path: Path) -> None:
    repository = LaboratoryRepository(tmp_path / "laboratory.sqlite3")

    assert repository.list_design_groups() == []
    assert repository.create_design_group("Concretos estructurales") == "Concretos estructurales"
    assert repository.create_design_group("  Concretos   estructurales  ") == "Concretos estructurales"
    assert repository.create_design_group("Prefabricados") == "Prefabricados"

    assert repository.list_design_groups() == [
        "Concretos estructurales",
        "Prefabricados",
    ]


def test_existing_design_groups_are_migrated(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE mix_designs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_uid TEXT NOT NULL,
                revision INTEGER NOT NULL,
                name TEXT NOT NULL,
                group_name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                source_design_id INTEGER,
                design_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                UNIQUE(family_uid, revision)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO mix_designs (
                family_uid, revision, name, group_name, design_json, created_at
            ) VALUES ('family', 1, 'Diseño A', 'Grupo heredado', '{}', '2026-01-01T00:00:00')
            """
        )

    repository = LaboratoryRepository(database_path)
    assert repository.list_design_groups() == ["Grupo heredado"]
