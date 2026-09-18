from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from civillab_suite.data_portability import (
    DataLocations,
    DataPortabilityError,
    DataPortabilityService,
)


def _database(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS marker (value TEXT NOT NULL)")
        connection.execute("DELETE FROM marker")
        connection.execute("INSERT INTO marker VALUES (?)", (value,))
        connection.commit()


def _value(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT value FROM marker").fetchone()[0]


@pytest.fixture
def portability(tmp_path: Path) -> tuple[DataPortabilityService, DataLocations]:
    locations = DataLocations(
        suite_directory=tmp_path / "suite",
        core_database=tmp_path / "suite" / "core.sqlite3",
        concrete_database=tmp_path / "concrete" / "materials.sqlite3",
        prefabricados_database=tmp_path / "suite" / "prefabricados" / "precon_lab.db",
        concrete_directory=tmp_path / "concrete",
    )
    for name, path in (
        ("core", locations.core_database),
        ("concrete", locations.concrete_database),
        ("precon", locations.prefabricados_database),
    ):
        _database(path, name)
    return DataPortabilityService(locations), locations


def _rewrite_package(package: Path, transform) -> None:
    with zipfile.ZipFile(package) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    transform(entries)
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, payload in entries.items():
            target.writestr(name, payload)


def test_export_and_import_round_trip_with_functional_preferences(
    portability: tuple[DataPortabilityService, DataLocations], tmp_path: Path
):
    service, locations = portability
    logo = locations.concrete_directory / "report_logo.png"
    logo.write_bytes(b"small-logo")
    preferences = locations.concrete_directory / "report_preferences.json"
    preferences.write_text(
        json.dumps({"logo_path": r"C:\\old-pc\\report_logo.png", "footer_text": "Pie"}),
        encoding="utf-8",
    )

    package = service.export_data(tmp_path / "transfer")
    summary = service.inspect_package(package)
    assert package.suffix == ".civillab"
    assert {"core", "concretos", "prefabricados"}.issubset(summary.components)

    _database(locations.core_database, "changed-core")
    _database(locations.concrete_database, "changed-concrete")
    _database(locations.prefabricados_database, "changed-precon")
    logo.write_bytes(b"changed")

    result = service.import_data(package)

    assert _value(locations.core_database) == "core"
    assert _value(locations.concrete_database) == "concrete"
    assert _value(locations.prefabricados_database) == "precon"
    assert logo.read_bytes() == b"small-logo"
    restored_preferences = json.loads(preferences.read_text(encoding="utf-8"))
    assert restored_preferences["logo_path"] == str(logo)
    assert result.backup_path.is_file()
    assert service.inspect_package(result.backup_path).components


def test_import_rejects_checksum_mismatch_before_touching_local_data(
    portability: tuple[DataPortabilityService, DataLocations], tmp_path: Path
):
    service, locations = portability
    package = service.export_data(tmp_path / "bad-checksum.civillab")

    def corrupt(entries: dict[str, bytes]) -> None:
        entries["data/core.sqlite3"] += b"corruption"

    _rewrite_package(package, corrupt)
    with pytest.raises(DataPortabilityError, match="Checksum"):
        service.import_data(package)
    assert _value(locations.core_database) == "core"
    assert not (locations.suite_directory / "backups").exists()


def test_import_rejects_unsafe_or_undeclared_zip_entry(
    portability: tuple[DataPortabilityService, DataLocations], tmp_path: Path
):
    service, _locations = portability
    package = service.export_data(tmp_path / "unsafe.civillab")

    def add_unsafe(entries: dict[str, bytes]) -> None:
        entries["../outside.txt"] = b"no"

    _rewrite_package(package, add_unsafe)
    with pytest.raises(DataPortabilityError, match="rutas inseguras"):
        service.inspect_package(package)


def test_import_rejects_invalid_sqlite_even_with_matching_checksum(
    portability: tuple[DataPortabilityService, DataLocations], tmp_path: Path
):
    service, _locations = portability
    package = service.export_data(tmp_path / "invalid-db.civillab")

    def replace_database(entries: dict[str, bytes]) -> None:
        payload = b"not sqlite"
        entries["data/core.sqlite3"] = payload
        manifest = json.loads(entries["manifest.json"])
        component = next(item for item in manifest["components"] if item["name"] == "core")
        component["sha256"] = hashlib.sha256(payload).hexdigest()
        component["size"] = len(payload)
        entries["manifest.json"] = json.dumps(manifest).encode()

    _rewrite_package(package, replace_database)
    with pytest.raises(DataPortabilityError, match="SQLite"):
        service.inspect_package(package)


def test_failed_commit_rolls_back_every_database(
    portability: tuple[DataPortabilityService, DataLocations],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    service, locations = portability
    package = service.export_data(tmp_path / "new.civillab")
    _database(locations.core_database, "old-core")
    _database(locations.concrete_database, "old-concrete")
    _database(locations.prefabricados_database, "old-precon")

    import civillab_suite.data_portability as module

    original_replace = module.os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(destination) == locations.concrete_database and not failed:
            failed = True
            raise OSError("simulated failure")
        return original_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_once)
    with pytest.raises(DataPortabilityError, match="datos anteriores"):
        service.import_data(package)

    assert _value(locations.core_database) == "old-core"
    assert _value(locations.concrete_database) == "old-concrete"
    assert _value(locations.prefabricados_database) == "old-precon"
