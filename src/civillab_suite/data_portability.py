"""Versioned, validated transport of CivilLab Suite's functional data."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterator
from uuid import uuid4

from civillab_suite.config import APP_VERSION, core_database_path, suite_data_dir

FORMAT_ID = "civillab-suite-data"
FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
SQLITE_COMPONENTS = {
    "core": "data/core.sqlite3",
    "concretos": "data/concretos/materials.sqlite3",
    "prefabricados": "data/prefabricados/precon_lab.db",
}
REPORT_PREFERENCES_PATH = "data/concretos/report_preferences.json"
REPORT_LOGO_PREFIX = "data/concretos/report_logo"
REPORT_LOGO_SUFFIXES = {".png", ".jpg", ".jpeg"}


class DataPortabilityError(ValueError):
    """Raised when a package is invalid or cannot be safely restored."""


@dataclass(frozen=True, slots=True)
class DataLocations:
    suite_directory: Path
    core_database: Path
    concrete_database: Path
    prefabricados_database: Path
    concrete_directory: Path


@dataclass(frozen=True, slots=True)
class PackageSummary:
    created_at: str
    app_version: str
    components: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImportResult:
    backup_path: Path
    imported_components: tuple[str, ...]


def default_data_locations() -> DataLocations:
    from concrete_mix_designer.config import DATABASE_PATH, user_data_dir
    from precon_lab.config import database_path

    return DataLocations(
        suite_directory=suite_data_dir(),
        core_database=core_database_path(),
        concrete_database=Path(DATABASE_PATH),
        prefabricados_database=database_path(),
        concrete_directory=user_data_dir(),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_connection = sqlite3.connect(
            f"file:{source.resolve().as_posix()}?mode=ro", uri=True
        )
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
    except sqlite3.Error as error:
        raise DataPortabilityError(
            f"No se pudo crear una copia consistente de {source.name}: {error}"
        ) from error


def _check_sqlite(path: Path) -> None:
    try:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise DataPortabilityError(f"La base {path.name} no es SQLite válida: {error}") from error
    if not result or result[0] != "ok":
        raise DataPortabilityError(f"La verificación de integridad falló para {path.name}.")


def _is_safe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and "\\" not in name and not path.is_absolute() and ".." not in path.parts


class DataPortabilityService:
    def __init__(self, locations: DataLocations | None = None):
        self.locations = locations or default_data_locations()

    def _database_sources(self) -> dict[str, Path]:
        return {
            "core": self.locations.core_database,
            "concretos": self.locations.concrete_database,
            "prefabricados": self.locations.prefabricados_database,
        }

    def export_data(self, destination: Path) -> Path:
        destination = Path(destination)
        if destination.suffix.lower() != ".civillab":
            destination = destination.with_suffix(".civillab")
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="civillab-export-") as temporary:
            staging = Path(temporary)
            components: list[dict[str, object]] = []
            for logical_name, source in self._database_sources().items():
                if not source.is_file():
                    raise DataPortabilityError(f"No se encontró la base requerida: {source}")
                archive_path = SQLITE_COMPONENTS[logical_name]
                snapshot = staging / archive_path
                _sqlite_snapshot(source, snapshot)
                _check_sqlite(snapshot)
                components.append(self._manifest_component(logical_name, archive_path, snapshot, True))

            preferences = self.locations.concrete_directory / "report_preferences.json"
            if preferences.is_file():
                staged_preferences = staging / REPORT_PREFERENCES_PATH
                staged_preferences.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(preferences, staged_preferences)
                components.append(
                    self._manifest_component(
                        "report_preferences", REPORT_PREFERENCES_PATH, staged_preferences, False
                    )
                )

            for logo in sorted(self.locations.concrete_directory.glob("report_logo.*")):
                if logo.suffix.lower() not in REPORT_LOGO_SUFFIXES or not logo.is_file():
                    continue
                archive_path = f"{REPORT_LOGO_PREFIX}{logo.suffix.lower()}"
                staged_logo = staging / archive_path
                staged_logo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(logo, staged_logo)
                components.append(
                    self._manifest_component("report_logo", archive_path, staged_logo, False)
                )

            manifest = {
                "format": FORMAT_ID,
                "format_version": FORMAT_VERSION,
                "app_version": APP_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "components": components,
            }
            manifest_path = staging / MANIFEST_NAME
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            temporary_package = destination.with_name(
                f".{destination.name}.{uuid4().hex}.tmp"
            )
            try:
                with zipfile.ZipFile(
                    temporary_package, "w", compression=zipfile.ZIP_DEFLATED
                ) as archive:
                    archive.write(manifest_path, MANIFEST_NAME)
                    for component in components:
                        archive_path = str(component["path"])
                        archive.write(staging / archive_path, archive_path)
                os.replace(temporary_package, destination)
            finally:
                temporary_package.unlink(missing_ok=True)
        return destination

    @staticmethod
    def _manifest_component(
        logical_name: str, archive_path: str, staged_path: Path, sqlite: bool
    ) -> dict[str, object]:
        return {
            "name": logical_name,
            "path": archive_path,
            "sha256": _sha256(staged_path),
            "size": staged_path.stat().st_size,
            "kind": "sqlite" if sqlite else "file",
        }

    def inspect_package(self, package_path: Path) -> PackageSummary:
        with self._validated_staging(Path(package_path)) as (manifest, _staging):
            return PackageSummary(
                created_at=str(manifest["created_at"]),
                app_version=str(manifest["app_version"]),
                components=tuple(
                    str(component["name"]) for component in manifest["components"]
                ),
            )

    @contextmanager
    def _validated_staging(
        self, package_path: Path
    ) -> Iterator[tuple[dict[str, object], Path]]:
        if not package_path.is_file():
            raise DataPortabilityError("No se encontró el archivo .civillab seleccionado.")
        try:
            archive = zipfile.ZipFile(package_path, "r")
        except (OSError, zipfile.BadZipFile) as error:
            raise DataPortabilityError("El archivo no es un paquete .civillab válido.") from error

        with archive, tempfile.TemporaryDirectory(prefix="civillab-import-") as temporary:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or any(
                not _is_safe_archive_name(name) for name in names
            ):
                raise DataPortabilityError("El paquete contiene rutas inseguras o duplicadas.")
            if MANIFEST_NAME not in names:
                raise DataPortabilityError("El paquete no contiene manifest.json.")
            try:
                manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise DataPortabilityError("manifest.json no es válido.") from error
            self._validate_manifest(manifest, set(names))

            staging = Path(temporary)
            for component in manifest["components"]:
                archive_path = str(component["path"])
                destination = staging / PurePosixPath(archive_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(archive_path) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                if _sha256(destination) != component["sha256"]:
                    raise DataPortabilityError(
                        f"Checksum incorrecto para {component['name']}."
                    )
                if component["kind"] == "sqlite":
                    _check_sqlite(destination)
            yield manifest, staging

    @staticmethod
    def _validate_manifest(manifest: object, archive_names: set[str]) -> None:
        if not isinstance(manifest, dict):
            raise DataPortabilityError("El manifiesto debe ser un objeto JSON.")
        if manifest.get("format") != FORMAT_ID:
            raise DataPortabilityError("El archivo no pertenece a CivilLab Suite.")
        if manifest.get("format_version") != FORMAT_VERSION:
            raise DataPortabilityError("La versión del formato .civillab no es compatible.")
        if not isinstance(manifest.get("app_version"), str) or not isinstance(
            manifest.get("created_at"), str
        ):
            raise DataPortabilityError("El manifiesto no contiene metadatos válidos.")
        components = manifest.get("components")
        if not isinstance(components, list):
            raise DataPortabilityError("La lista de componentes del manifiesto no es válida.")

        paths: set[str] = set()
        names: set[str] = set()
        for component in components:
            if not isinstance(component, dict):
                raise DataPortabilityError("Existe un componente inválido en el manifiesto.")
            logical_name = component.get("name")
            path = component.get("path")
            checksum = component.get("sha256")
            kind = component.get("kind")
            if not all(isinstance(value, str) for value in (logical_name, path, checksum, kind)):
                raise DataPortabilityError("Un componente tiene campos incompletos.")
            expected_path = SQLITE_COMPONENTS.get(logical_name)
            valid_optional = path == REPORT_PREFERENCES_PATH and logical_name == "report_preferences"
            valid_logo = (
                logical_name == "report_logo"
                and path.startswith(REPORT_LOGO_PREFIX)
                and PurePosixPath(path).suffix.lower() in REPORT_LOGO_SUFFIXES
            )
            if path != expected_path and not valid_optional and not valid_logo:
                raise DataPortabilityError(f"Entrada no permitida en el paquete: {path}")
            if not _is_safe_archive_name(path) or path in paths:
                raise DataPortabilityError("El manifiesto contiene rutas inseguras o duplicadas.")
            if logical_name != "report_logo" and logical_name in names:
                raise DataPortabilityError("El manifiesto contiene componentes duplicados.")
            if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
                raise DataPortabilityError("El manifiesto contiene un checksum inválido.")
            if kind not in {"sqlite", "file"} or (expected_path and kind != "sqlite"):
                raise DataPortabilityError("El tipo de componente no coincide con su contenido.")
            paths.add(path)
            names.add(logical_name)

        if not set(SQLITE_COMPONENTS).issubset(names):
            raise DataPortabilityError("El paquete no contiene las tres bases requeridas.")
        if archive_names != paths | {MANIFEST_NAME}:
            raise DataPortabilityError("El ZIP contiene entradas no declaradas en el manifiesto.")

    def import_data(self, package_path: Path) -> ImportResult:
        with self._validated_staging(Path(package_path)) as (manifest, staging):
            backup_directory = self.locations.suite_directory / "backups"
            backup_directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = backup_directory / f"antes-de-importar-{stamp}.civillab"
            counter = 1
            while backup_path.exists():
                backup_path = backup_directory / f"antes-de-importar-{stamp}-{counter}.civillab"
                counter += 1
            self.export_data(backup_path)

            incoming = self._incoming_targets(manifest, staging)
            self._normalize_report_preferences(incoming)
            self._replace_all(incoming)
            return ImportResult(
                backup_path=backup_path,
                imported_components=tuple(
                    str(component["name"]) for component in manifest["components"]
                ),
            )

    def _incoming_targets(
        self, manifest: dict[str, object], staging: Path
    ) -> dict[Path, Path | None]:
        targets: dict[Path, Path | None] = {
            self.locations.core_database: None,
            self.locations.concrete_database: None,
            self.locations.prefabricados_database: None,
            self.locations.concrete_directory / "report_preferences.json": None,
        }
        for existing_logo in self.locations.concrete_directory.glob("report_logo.*"):
            if existing_logo.suffix.lower() in REPORT_LOGO_SUFFIXES:
                targets[existing_logo] = None

        database_targets = {
            "core": self.locations.core_database,
            "concretos": self.locations.concrete_database,
            "prefabricados": self.locations.prefabricados_database,
        }
        for component in manifest["components"]:
            logical_name = str(component["name"])
            archive_path = str(component["path"])
            if logical_name in database_targets:
                target = database_targets[logical_name]
            elif logical_name == "report_preferences":
                target = self.locations.concrete_directory / "report_preferences.json"
            else:
                target = self.locations.concrete_directory / PurePosixPath(archive_path).name
            targets[target] = staging / PurePosixPath(archive_path)
        return targets

    @staticmethod
    def _normalize_report_preferences(incoming: dict[Path, Path | None]) -> None:
        preferences_target = next(
            (path for path in incoming if path.name == "report_preferences.json"), None
        )
        if preferences_target is None or incoming[preferences_target] is None:
            return
        staged_preferences = incoming[preferences_target]
        try:
            payload = json.loads(staged_preferences.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError) as error:
            raise DataPortabilityError("report_preferences.json no es válido.") from error
        if not isinstance(payload, dict):
            raise DataPortabilityError("report_preferences.json no es válido.")
        imported_logo = next(
            (path for path, source in incoming.items() if source is not None and path.name.startswith("report_logo.")),
            None,
        )
        payload["logo_path"] = str(imported_logo) if imported_logo else ""
        staged_preferences.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _replace_all(incoming: dict[Path, Path | None]) -> None:
        token = uuid4().hex
        prepared: dict[Path, Path] = {}
        rollbacks: dict[Path, Path] = {}
        committed: list[Path] = []
        try:
            for target, source in incoming.items():
                target.parent.mkdir(parents=True, exist_ok=True)
                if source is not None:
                    prepared_path = target.with_name(f".{target.name}.{token}.incoming")
                    shutil.copy2(source, prepared_path)
                    prepared[target] = prepared_path

            for target in incoming:
                rollback_path = target.with_name(f".{target.name}.{token}.rollback")
                if target.exists():
                    os.replace(target, rollback_path)
                    rollbacks[target] = rollback_path
                if target in prepared:
                    os.replace(prepared[target], target)
                committed.append(target)
        except Exception as error:
            for target in reversed(committed):
                target.unlink(missing_ok=True)
                rollback = rollbacks.get(target)
                if rollback is not None and rollback.exists():
                    os.replace(rollback, target)
            for target, rollback in rollbacks.items():
                if target not in committed and rollback.exists():
                    os.replace(rollback, target)
            raise DataPortabilityError(
                f"No se completó la restauración; se conservaron los datos anteriores: {error}"
            ) from error
        finally:
            for path in (*prepared.values(), *rollbacks.values()):
                path.unlink(missing_ok=True)
