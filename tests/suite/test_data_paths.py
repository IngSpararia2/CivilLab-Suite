from __future__ import annotations

import sqlite3

from civillab_suite import data_paths


def test_prefabricados_legacy_database_is_copied_once(monkeypatch, tmp_path):
    legacy_root = tmp_path / "legacy"
    legacy_database = legacy_root / "prefabricados" / "precon_lab.db"
    legacy_database.parent.mkdir(parents=True)
    with sqlite3.connect(legacy_database) as connection:
        connection.execute("CREATE TABLE inspection_plan_entries (id INTEGER PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO inspection_plan_entries (id) VALUES (?)", ((1,), (2,))
        )

    monkeypatch.setattr(data_paths, "LEGACY_DATA_DIR", legacy_root)
    monkeypatch.delenv("PRECON_LAB_DATA_DIR", raising=False)
    monkeypatch.setenv("CIVILLAB_SUITE_DATA_DIR", str(tmp_path / "suite-data"))

    target = data_paths.prepare_prefabricados_data()
    assert target.is_file()
    with sqlite3.connect(target) as connection:
        plans = connection.execute("SELECT COUNT(*) FROM inspection_plan_entries").fetchone()[0]
        connection.execute("CREATE TABLE migration_sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO migration_sentinel VALUES ('preserved')")

    monkeypatch.delenv("PRECON_LAB_DATA_DIR", raising=False)
    assert data_paths.prepare_prefabricados_data() == target
    with sqlite3.connect(target) as connection:
        sentinel = connection.execute("SELECT value FROM migration_sentinel").fetchone()[0]

    assert plans == 2
    assert sentinel == "preserved"
