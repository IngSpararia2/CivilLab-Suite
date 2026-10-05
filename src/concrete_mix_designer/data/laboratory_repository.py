from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from civillab_suite.sqlite_support import connect as sqlite_connect
from concrete_mix_designer.domain.laboratory_models import (
    CompressionResultRecord,
    DesignStatisticsRow,
    FlexuralResultRecord,
    FreshTestRecord,
    FreshTestType,
    ProductionRecord,
    SavedDesignRecord,
    SpecimenRecord,
    SpecimenStatus,
    SpecimenType,
)
from concrete_mix_designer.domain.metadata_models import DesignSpecification
from concrete_mix_designer.domain.models import MixDesign


def _now() -> datetime:
    return datetime.now().astimezone()


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.astimezone()
    return value.isoformat(timespec="seconds")


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _finite_float(value: object, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} debe ser un número finito.") from error
    if not math.isfinite(numeric):
        raise ValueError(f"{label} debe ser un número finito.")
    return numeric


def _positive_float(value: object, label: str) -> float:
    numeric = _finite_float(value, label)
    if numeric <= 0:
        raise ValueError(f"{label} debe ser mayor que cero.")
    return numeric


def _optional_finite_float(value: object | None, label: str) -> float | None:
    return None if value is None else _finite_float(value, label)


def _aware_datetime(value: datetime) -> datetime:
    return value.astimezone() if value.tzinfo is None else value


def _elapsed_seconds(later: datetime, earlier: datetime, label: str) -> float:
    seconds = (_aware_datetime(later) - _aware_datetime(earlier)).total_seconds()
    if seconds < 0:
        raise ValueError(f"{label} no puede ser anterior a la fecha de producción.")
    return seconds


class LaboratoryRepository:
    """Persistence for saved designs, productions, specimens and lab results.

    Every production stores an immutable JSON snapshot of the design used at
    batching time. Therefore later edits to a saved design do not rewrite the
    historical production record.
    """

    def __init__(self, database_path: Path):
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = Path(database_path)
        from civillab_suite.storage import ensure_domain_namespace
        ensure_domain_namespace(self.database_path, "concretos")
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite_connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS concretos_design_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS concretos_mix_designs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_uid TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    group_name TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    source_design_id INTEGER REFERENCES concretos_mix_designs(id),
                    design_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(family_uid, revision)
                );

                CREATE TABLE IF NOT EXISTS concretos_design_specifications (
                    design_id INTEGER PRIMARY KEY
                        REFERENCES concretos_mix_designs(id) ON DELETE CASCADE,
                    specification_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS concretos_productions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    design_id INTEGER NOT NULL REFERENCES concretos_mix_designs(id) ON DELETE RESTRICT,
                    design_name TEXT NOT NULL,
                    design_revision INTEGER NOT NULL,
                    design_json_snapshot TEXT NOT NULL,
                    specification_json_snapshot TEXT NOT NULL DEFAULT '{}',
                    produced_at TEXT NOT NULL,
                    batch_code TEXT NOT NULL,
                    batch_volume_m3 REAL NOT NULL DEFAULT 1.0,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS concretos_specimens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    production_id INTEGER NOT NULL REFERENCES concretos_productions(id) ON DELETE CASCADE,
                    specimen_code TEXT NOT NULL,
                    specimen_type TEXT NOT NULL CHECK(specimen_type IN ('cylinder', 'beam')),
                    target_age_days REAL NOT NULL,
                    planned_test_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'planned'
                        CHECK(status IN ('planned', 'tested', 'cancelled')),
                    notes TEXT NOT NULL DEFAULT '',
                    UNIQUE(production_id, specimen_code)
                );

                CREATE TABLE IF NOT EXISTS concretos_fresh_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    production_id INTEGER NOT NULL REFERENCES concretos_productions(id) ON DELETE CASCADE,
                    test_type TEXT NOT NULL CHECK(test_type IN ('slump', 'spread')),
                    measured_at TEXT NOT NULL,
                    elapsed_minutes INTEGER NOT NULL,
                    slump_mm REAL,
                    spread_d1_mm REAL,
                    spread_d2_mm REAL,
                    concrete_temperature_c REAL,
                    air_content_pct REAL,
                    unit_weight_kg_m3 REAL,
                    notes TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS concretos_compression_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    specimen_id INTEGER NOT NULL UNIQUE REFERENCES concretos_specimens(id) ON DELETE CASCADE,
                    tested_at TEXT NOT NULL,
                    actual_age_days REAL NOT NULL,
                    diameter_mm REAL NOT NULL,
                    height_mm REAL,
                    mass_kg REAL,
                    max_load_kn REAL NOT NULL,
                    strength_mpa REAL NOT NULL,
                    failure_type TEXT NOT NULL DEFAULT '',
                    machine TEXT NOT NULL DEFAULT '',
                    technician TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS concretos_flexural_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    specimen_id INTEGER NOT NULL UNIQUE REFERENCES concretos_specimens(id) ON DELETE CASCADE,
                    tested_at TEXT NOT NULL,
                    actual_age_days REAL NOT NULL,
                    width_mm REAL NOT NULL,
                    depth_mm REAL NOT NULL,
                    span_mm REAL NOT NULL,
                    fracture_distance_mm REAL,
                    max_load_kn REAL NOT NULL,
                    modulus_of_rupture_mpa REAL NOT NULL,
                    failure_type TEXT NOT NULL DEFAULT '',
                    machine TEXT NOT NULL DEFAULT '',
                    technician TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_mix_designs_name
                    ON concretos_mix_designs(name, archived, created_at);
                CREATE INDEX IF NOT EXISTS idx_productions_design
                    ON concretos_productions(design_id, produced_at);
                CREATE INDEX IF NOT EXISTS idx_specimens_due
                    ON concretos_specimens(status, planned_test_at);
                CREATE INDEX IF NOT EXISTS idx_fresh_tests_production
                    ON concretos_fresh_tests(production_id, measured_at);
                """
            )
            design_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(concretos_mix_designs)").fetchall()
            }
            if "group_name" not in design_columns:
                connection.execute(
                    "ALTER TABLE concretos_mix_designs ADD COLUMN group_name TEXT NOT NULL DEFAULT ''"
                )
            production_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(concretos_productions)").fetchall()
            }
            if "specification_json_snapshot" not in production_columns:
                connection.execute(
                    "ALTER TABLE concretos_productions ADD COLUMN "
                    "specification_json_snapshot TEXT NOT NULL DEFAULT '{}'"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mix_designs_group "
                "ON concretos_mix_designs(group_name, archived, created_at)"
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO concretos_design_groups (name, created_at)
                SELECT DISTINCT TRIM(group_name), ?
                FROM concretos_mix_designs
                WHERE TRIM(group_name) <> ''
                """,
                (_serialize_datetime(_now()),),
            )

    # ------------------------------------------------------------------
    # Design groups
    # ------------------------------------------------------------------
    def list_design_groups(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM concretos_design_groups ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def create_design_group(self, name: str) -> str:
        clean_name = " ".join(str(name).split())
        if not clean_name:
            raise ValueError("El grupo debe tener un nombre.")
        if len(clean_name) > 80:
            raise ValueError("El nombre del grupo no puede superar 80 caracteres.")
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO concretos_design_groups (name, created_at) VALUES (?, ?)",
                (clean_name, _serialize_datetime(_now())),
            )
            row = connection.execute(
                "SELECT name FROM concretos_design_groups WHERE name = ? COLLATE NOCASE",
                (clean_name,),
            ).fetchone()
        if row is None:
            raise RuntimeError("No fue posible crear el grupo.")
        return str(row["name"])

    # ------------------------------------------------------------------
    # Saved designs
    # ------------------------------------------------------------------
    def create_design(
        self,
        *,
        name: str,
        design: MixDesign,
        description: str = "",
        group_name: str = "",
        source_design_id: int | None = None,
        specification: DesignSpecification | None = None,
    ) -> SavedDesignRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("El diseño debe tener un nombre.")

        try:
            validated_design = MixDesign.from_dict(design.to_dict())
        except ValueError as error:
            raise ValueError(f"El diseño contiene datos inválidos o no finitos: {error}") from error
        # Unusual/nonconvergent formulations are allowed; corrupt arithmetic is not.
        if not math.isfinite(validated_design.parameters.target_volume_l) or validated_design.parameters.target_volume_l <= 0:
            raise ValueError("El volumen objetivo debe ser finito y positivo.")
        if len({c.uid for c in validated_design.components}) != len(validated_design.components):
            raise ValueError("Los identificadores de componentes deben ser únicos.")
        for component in validated_design.components:
            if not math.isfinite(component.quantity) or component.quantity < 0 or not math.isfinite(component.material.specific_gravity) or component.material.specific_gravity <= 0:
                raise ValueError("Las cantidades deben ser finitas y no negativas; la gravedad debe ser positiva.")
        family_uid = uuid4().hex
        revision = 1
        if source_design_id is not None:
            source = self.get_design(source_design_id)
            if source is None:
                raise ValueError("El diseño de origen ya no existe.")
            family_uid = source.family_uid
            if not group_name.strip():
                group_name = source.group_name
            with self._connect() as connection:
                revision = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(revision), 0) + 1 FROM concretos_mix_designs WHERE family_uid = ?",
                        (family_uid,),
                    ).fetchone()[0]
                )

        clean_group = " ".join(str(group_name).split())
        try:
            payload = json.dumps(
                design.to_dict(),
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except ValueError as error:
            raise ValueError("El diseño contiene valores numéricos no finitos.") from error
        created_at = _now()
        with self._connect() as connection:
            if clean_group:
                connection.execute(
                    "INSERT OR IGNORE INTO concretos_design_groups (name, created_at) VALUES (?, ?)",
                    (clean_group, _serialize_datetime(created_at)),
                )
            cursor = connection.execute(
                """
                INSERT INTO concretos_mix_designs (
                    family_uid, revision, name, group_name, description, source_design_id,
                    design_json, created_at, archived
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    family_uid,
                    revision,
                    clean_name,
                    clean_group,
                    description.strip(),
                    source_design_id,
                    payload,
                    _serialize_datetime(created_at),
                ),
            )
            design_id = int(cursor.lastrowid)
            final_specification = specification or DesignSpecification.from_mix_design(design)
            final_specification.design_id = design_id
            connection.execute(
                """
                INSERT OR REPLACE INTO concretos_design_specifications (
                    design_id, specification_json
                ) VALUES (?, ?)
                """,
                (
                    design_id,
                    self._serialize_specification(final_specification),
                ),
            )
        record = self.get_design(design_id)
        if record is None:
            raise RuntimeError("No fue posible recuperar el diseño guardado.")
        return record

    def list_designs(self, include_archived: bool = False) -> list[SavedDesignRecord]:
        archived_filter = "" if include_archived else "WHERE d.archived = 0"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT d.*, COUNT(p.id) AS production_count
                FROM concretos_mix_designs d
                LEFT JOIN concretos_productions p ON p.design_id = d.id
                {archived_filter}
                GROUP BY d.id
                ORDER BY d.created_at DESC, d.id DESC
                """
            ).fetchall()
        return [self._row_to_design(row) for row in rows]

    def get_design(self, design_id: int) -> SavedDesignRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT d.*, COUNT(p.id) AS production_count
                FROM concretos_mix_designs d
                LEFT JOIN concretos_productions p ON p.design_id = d.id
                WHERE d.id = ?
                GROUP BY d.id
                """,
                (design_id,),
            ).fetchone()
        return self._row_to_design(row) if row else None

    def save_design_specification(
        self,
        design_id: int,
        specification: DesignSpecification,
    ) -> DesignSpecification:
        if self.get_design(design_id) is None:
            raise ValueError("El diseño seleccionado no existe.")
        specification.design_id = design_id
        payload = self._serialize_specification(specification)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO concretos_design_specifications (design_id, specification_json)
                VALUES (?, ?)
                ON CONFLICT(design_id) DO UPDATE SET
                    specification_json = excluded.specification_json
                """,
                (design_id, payload),
            )
        return self.get_design_specification(design_id)

    def get_design_specification(self, design_id: int) -> DesignSpecification:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT specification_json FROM concretos_design_specifications WHERE design_id = ?",
                (design_id,),
            ).fetchone()
        if row is not None:
            specification = DesignSpecification.from_dict(
                json.loads(str(row["specification_json"]))
            )
            specification.design_id = design_id
            return specification
        design = self.load_mix_design(design_id)
        specification = DesignSpecification.from_mix_design(design)
        specification.design_id = design_id
        return specification

    def list_design_specifications(self) -> dict[int, DesignSpecification]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT design_id, specification_json FROM concretos_design_specifications"
            ).fetchall()
        output: dict[int, DesignSpecification] = {}
        for row in rows:
            design_id = int(row["design_id"])
            specification = DesignSpecification.from_dict(
                json.loads(str(row["specification_json"]))
            )
            specification.design_id = design_id
            output[design_id] = specification
        return output

    def load_mix_design(self, design_id: int) -> MixDesign:
        record = self.get_design(design_id)
        if record is None:
            raise ValueError("El diseño seleccionado no existe.")
        return MixDesign.from_dict(json.loads(record.design_json))

    def archive_design(self, design_id: int, archived: bool = True) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE concretos_mix_designs SET archived = ? WHERE id = ?",
                (int(archived), design_id),
            )

    # ------------------------------------------------------------------
    # Productions and specimen scheduling
    # ------------------------------------------------------------------
    def create_production(
        self,
        *,
        design_id: int,
        produced_at: datetime,
        batch_code: str,
        batch_volume_m3: float,
        notes: str = "",
        schedules: list[tuple[SpecimenType, float, int]] | None = None,
        batch_moistures: dict[str, float] | None = None,
    ) -> ProductionRecord:
        design = self.get_design(design_id)
        if design is None:
            raise ValueError("Selecciona un diseño guardado válido.")
        clean_code = batch_code.strip()
        if not clean_code:
            clean_code = produced_at.strftime("PROD-%Y%m%d-%H%M")
        batch_volume = _positive_float(batch_volume_m3, "El volumen producido")

        snapshot = MixDesign.from_dict(json.loads(design.design_json))
        if batch_moistures is not None:
            snapshot.batch_moistures = dict(batch_moistures)
        from concrete_mix_designer.domain.engine import MixCalculationEngine
        MixCalculationEngine().moisture_correction(snapshot)
        created_at = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO concretos_productions (
                    design_id, design_name, design_revision, design_json_snapshot,
                    specification_json_snapshot, produced_at, batch_code,
                    batch_volume_m3, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    design.id,
                    design.name,
                    design.revision,
                    json.dumps(snapshot.to_dict(), ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                    self._serialize_specification(
                        self.get_design_specification(design.id)
                    ),
                    _serialize_datetime(produced_at),
                    clean_code,
                    batch_volume,
                    notes.strip(),
                    _serialize_datetime(created_at),
                ),
            )
            production_id = int(cursor.lastrowid)
            self._insert_schedules(connection, production_id, produced_at, schedules or [])

        production = self.get_production(production_id)
        if production is None:
            raise RuntimeError("No fue posible recuperar la producción creada.")
        return production

    def _insert_schedules(
        self,
        connection: sqlite3.Connection,
        production_id: int,
        produced_at: datetime,
        schedules: list[tuple[SpecimenType, float, int]],
    ) -> None:
        counters = {
            SpecimenType.CYLINDER: int(
                connection.execute(
                    "SELECT COUNT(*) FROM concretos_specimens WHERE production_id = ? AND specimen_type = ?",
                    (production_id, SpecimenType.CYLINDER.value),
                ).fetchone()[0]
            ),
            SpecimenType.BEAM: int(
                connection.execute(
                    "SELECT COUNT(*) FROM concretos_specimens WHERE production_id = ? AND specimen_type = ?",
                    (production_id, SpecimenType.BEAM.value),
                ).fetchone()[0]
            ),
        }
        prefixes = {SpecimenType.CYLINDER: "C", SpecimenType.BEAM: "V"}
        for specimen_type, target_age_days, count in schedules:
            specimen_type = SpecimenType(specimen_type)
            age = _finite_float(target_age_days, "La edad objetivo")
            if age < 0:
                raise ValueError("La edad objetivo no puede ser negativa.")
            numeric_count = _finite_float(count, "La cantidad de muestras")
            if numeric_count <= 0 or not numeric_count.is_integer():
                raise ValueError("La cantidad de muestras debe ser un entero mayor que cero.")
            quantity = int(numeric_count)
            planned_at = produced_at + timedelta(days=age)
            for _ in range(quantity):
                counters[specimen_type] += 1
                code = f"{prefixes[specimen_type]}-{age:g}D-{counters[specimen_type]:03d}"
                connection.execute(
                    """
                    INSERT INTO concretos_specimens (
                        production_id, specimen_code, specimen_type, target_age_days,
                        planned_test_at, status, notes
                    ) VALUES (?, ?, ?, ?, ?, 'planned', '')
                    """,
                    (
                        production_id,
                        code,
                        specimen_type.value,
                        age,
                        _serialize_datetime(planned_at),
                    ),
                )

    def add_specimen_schedule(
        self,
        *,
        production_id: int,
        specimen_type: SpecimenType,
        target_age_days: float,
        count: int,
    ) -> None:
        specimen_type = SpecimenType(specimen_type)
        production = self.get_production(production_id)
        if production is None:
            raise ValueError("La producción seleccionada no existe.")
        with self._connect() as connection:
            self._insert_schedules(
                connection,
                production_id,
                production.produced_at,
                [(specimen_type, target_age_days, count)],
            )

    def list_productions(self, design_id: int | None = None) -> list[ProductionRecord]:
        where = "WHERE p.design_id = ?" if design_id is not None else ""
        params: tuple[object, ...] = (design_id,) if design_id is not None else ()
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT p.*, COUNT(s.id) AS specimen_count,
                       SUM(CASE WHEN s.status = 'tested' THEN 1 ELSE 0 END) AS tested_specimen_count
                FROM concretos_productions p
                LEFT JOIN concretos_specimens s ON s.production_id = p.id
                {where}
                GROUP BY p.id
                ORDER BY p.produced_at DESC, p.id DESC
                """,
                params,
            ).fetchall()
        return [self._row_to_production(row) for row in rows]

    def get_production(self, production_id: int) -> ProductionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT p.*, COUNT(s.id) AS specimen_count,
                       SUM(CASE WHEN s.status = 'tested' THEN 1 ELSE 0 END) AS tested_specimen_count
                FROM concretos_productions p
                LEFT JOIN concretos_specimens s ON s.production_id = p.id
                WHERE p.id = ?
                GROUP BY p.id
                """,
                (production_id,),
            ).fetchone()
        return self._row_to_production(row) if row else None

    def get_production_specification(self, production_id: int) -> DesignSpecification:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT design_id, specification_json_snapshot
                FROM concretos_productions WHERE id = ?
                """,
                (production_id,),
            ).fetchone()
        if row is None:
            raise ValueError("La producción seleccionada no existe.")
        raw = str(row["specification_json_snapshot"] or "{}").strip()
        if raw and raw != "{}":
            specification = DesignSpecification.from_dict(json.loads(raw))
            specification.design_id = int(row["design_id"])
            return specification
        return self.get_design_specification(int(row["design_id"]))

    def list_specimens(self, production_id: int) -> list[SpecimenRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM concretos_specimens
                WHERE production_id = ?
                ORDER BY planned_test_at, specimen_type, specimen_code
                """,
                (production_id,),
            ).fetchall()
        return [self._row_to_specimen(row) for row in rows]

    def get_specimen(self, specimen_id: int) -> SpecimenRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM concretos_specimens WHERE id = ?", (specimen_id,)
            ).fetchone()
        return self._row_to_specimen(row) if row else None

    def set_specimen_status(self, specimen_id: int, status: SpecimenStatus) -> None:
        status = SpecimenStatus(status)
        if self.get_specimen(specimen_id) is None:
            raise ValueError("La muestra seleccionada no existe.")
        with self._connect() as connection:
            connection.execute(
                "UPDATE concretos_specimens SET status = ? WHERE id = ?",
                (status.value, specimen_id),
            )

    # ------------------------------------------------------------------
    # Fresh concrete observations
    # ------------------------------------------------------------------
    def add_fresh_test(
        self,
        *,
        production_id: int,
        test_type: FreshTestType,
        measured_at: datetime,
        slump_mm: float | None = None,
        spread_d1_mm: float | None = None,
        spread_d2_mm: float | None = None,
        concrete_temperature_c: float | None = None,
        air_content_pct: float | None = None,
        unit_weight_kg_m3: float | None = None,
        notes: str = "",
    ) -> FreshTestRecord:
        test_type = FreshTestType(test_type)
        production = self.get_production(production_id)
        if production is None:
            raise ValueError("La producción seleccionada no existe.")
        elapsed_minutes = int(
            round(
                _elapsed_seconds(
                    measured_at, production.produced_at, "La fecha de medición"
                )
                / 60.0
            )
        )
        slump_mm = _optional_finite_float(slump_mm, "El asentamiento")
        spread_d1_mm = _optional_finite_float(spread_d1_mm, "El primer diámetro")
        spread_d2_mm = _optional_finite_float(spread_d2_mm, "El segundo diámetro")
        concrete_temperature_c = _optional_finite_float(
            concrete_temperature_c, "La temperatura del concreto"
        )
        air_content_pct = _optional_finite_float(air_content_pct, "El contenido de aire")
        unit_weight_kg_m3 = _optional_finite_float(
            unit_weight_kg_m3, "La masa unitaria"
        )
        self._validate_fresh_measurements(
            slump_mm,
            spread_d1_mm,
            spread_d2_mm,
            air_content_pct,
            unit_weight_kg_m3,
        )
        if test_type == FreshTestType.SLUMP and slump_mm is None:
            raise ValueError("Registra el asentamiento.")
        if test_type == FreshTestType.SPREAD and spread_d1_mm is None:
            raise ValueError("Registra al menos un diámetro de esparcimiento.")
        if test_type == FreshTestType.SLUMP:
            spread_d1_mm = None
            spread_d2_mm = None
        else:
            slump_mm = None

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO concretos_fresh_tests (
                    production_id, test_type, measured_at, elapsed_minutes,
                    slump_mm, spread_d1_mm, spread_d2_mm,
                    concrete_temperature_c, air_content_pct, unit_weight_kg_m3, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    production_id,
                    test_type.value,
                    _serialize_datetime(measured_at),
                    elapsed_minutes,
                    slump_mm,
                    spread_d1_mm,
                    spread_d2_mm,
                    concrete_temperature_c,
                    air_content_pct,
                    unit_weight_kg_m3,
                    notes.strip(),
                ),
            )
            test_id = int(cursor.lastrowid)
        result = self.get_fresh_test(test_id)
        if result is None:
            raise RuntimeError("No fue posible recuperar el ensayo en estado fresco.")
        return result

    def update_fresh_test(
        self,
        *,
        test_id: int,
        test_type: FreshTestType,
        measured_at: datetime,
        slump_mm: float | None = None,
        spread_d1_mm: float | None = None,
        spread_d2_mm: float | None = None,
        concrete_temperature_c: float | None = None,
        air_content_pct: float | None = None,
        unit_weight_kg_m3: float | None = None,
        notes: str = "",
    ) -> FreshTestRecord:
        existing = self.get_fresh_test(test_id)
        if existing is None:
            raise ValueError("El dato de concreto fresco seleccionado no existe.")
        production = self.get_production(existing.production_id)
        if production is None:
            raise ValueError("La producción asociada ya no existe.")

        test_type = FreshTestType(test_type)
        if test_type == FreshTestType.SLUMP and slump_mm is None:
            raise ValueError("Registra el asentamiento.")
        if test_type == FreshTestType.SPREAD and spread_d1_mm is None:
            raise ValueError("Registra al menos un diámetro de esparcimiento.")
        if test_type == FreshTestType.SLUMP:
            spread_d1_mm = None
            spread_d2_mm = None
        else:
            slump_mm = None

        elapsed_minutes = int(
            round(
                _elapsed_seconds(
                    measured_at, production.produced_at, "La fecha de medición"
                )
                / 60.0
            )
        )
        slump_mm = _optional_finite_float(slump_mm, "El asentamiento")
        spread_d1_mm = _optional_finite_float(spread_d1_mm, "El primer diámetro")
        spread_d2_mm = _optional_finite_float(spread_d2_mm, "El segundo diámetro")
        concrete_temperature_c = _optional_finite_float(
            concrete_temperature_c, "La temperatura del concreto"
        )
        air_content_pct = _optional_finite_float(air_content_pct, "El contenido de aire")
        unit_weight_kg_m3 = _optional_finite_float(
            unit_weight_kg_m3, "La masa unitaria"
        )
        self._validate_fresh_measurements(
            slump_mm,
            spread_d1_mm,
            spread_d2_mm,
            air_content_pct,
            unit_weight_kg_m3,
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE concretos_fresh_tests SET
                    test_type = ?, measured_at = ?, elapsed_minutes = ?,
                    slump_mm = ?, spread_d1_mm = ?, spread_d2_mm = ?,
                    concrete_temperature_c = ?, air_content_pct = ?,
                    unit_weight_kg_m3 = ?, notes = ?
                WHERE id = ?
                """,
                (
                    test_type.value,
                    _serialize_datetime(measured_at),
                    elapsed_minutes,
                    slump_mm,
                    spread_d1_mm,
                    spread_d2_mm,
                    concrete_temperature_c,
                    air_content_pct,
                    unit_weight_kg_m3,
                    notes.strip(),
                    test_id,
                ),
            )
        result = self.get_fresh_test(test_id)
        if result is None:
            raise RuntimeError("No fue posible recuperar el dato de concreto fresco editado.")
        return result

    def delete_fresh_test(self, test_id: int) -> None:
        if self.get_fresh_test(test_id) is None:
            raise ValueError("El dato de concreto fresco seleccionado no existe.")
        with self._connect() as connection:
            connection.execute("DELETE FROM concretos_fresh_tests WHERE id = ?", (test_id,))

    def list_fresh_tests(self, production_id: int) -> list[FreshTestRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM concretos_fresh_tests WHERE production_id = ? ORDER BY measured_at",
                (production_id,),
            ).fetchall()
        return [self._row_to_fresh_test(row) for row in rows]

    def get_fresh_test(self, test_id: int) -> FreshTestRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM concretos_fresh_tests WHERE id = ?", (test_id,)
            ).fetchone()
        return self._row_to_fresh_test(row) if row else None

    # ------------------------------------------------------------------
    # Hardened concrete results
    # ------------------------------------------------------------------
    @staticmethod
    def calculate_compressive_strength(max_load_kn: float, diameter_mm: float) -> float:
        max_load_kn = _finite_float(max_load_kn, "La carga máxima")
        diameter_mm = _finite_float(diameter_mm, "El diámetro")
        if max_load_kn <= 0 or diameter_mm <= 0:
            return 0.0
        area_mm2 = math.pi * diameter_mm**2 / 4.0
        return max_load_kn * 1000.0 / area_mm2

    @staticmethod
    def calculate_modulus_of_rupture(
        max_load_kn: float,
        span_mm: float,
        width_mm: float,
        depth_mm: float,
        fracture_distance_mm: float | None = None,
    ) -> float:
        max_load_kn = _finite_float(max_load_kn, "La carga máxima")
        span_mm = _finite_float(span_mm, "La luz entre apoyos")
        width_mm = _finite_float(width_mm, "El ancho")
        depth_mm = _finite_float(depth_mm, "La profundidad")
        if min(max_load_kn, span_mm, width_mm, depth_mm) <= 0:
            return 0.0
        load_n = max_load_kn * 1000.0
        if fracture_distance_mm is None:
            return load_n * span_mm / (width_mm * depth_mm**2)

        distance = _finite_float(
            fracture_distance_mm, "La distancia de fractura al apoyo más cercano"
        )
        if distance <= 0 or distance > span_mm / 2.0:
            raise ValueError(
                "La distancia de fractura debe ser mayor que cero y no superar la mitad de la luz."
            )
        middle_third_limit = span_mm / 3.0
        if distance >= middle_third_limit:
            return load_n * span_mm / (width_mm * depth_mm**2)
        if distance >= middle_third_limit - 0.05 * span_mm:
            return 3.0 * load_n * distance / (width_mm * depth_mm**2)
        raise ValueError(
            "La fractura quedó más de 5 % de la luz fuera del tercio medio; "
            "el resultado debe descartarse."
        )

    def upsert_compression_result(
        self,
        *,
        specimen_id: int,
        tested_at: datetime,
        diameter_mm: float,
        height_mm: float | None,
        mass_kg: float | None,
        max_load_kn: float,
        strength_mpa: float | None = None,
        failure_type: str = "",
        machine: str = "",
        technician: str = "",
        notes: str = "",
    ) -> CompressionResultRecord:
        specimen, production = self._specimen_and_production(specimen_id)
        if specimen.specimen_type != SpecimenType.CYLINDER:
            raise ValueError("El resultado de compresión solo puede asignarse a un cilindro.")
        diameter_mm = _positive_float(diameter_mm, "El diámetro")
        max_load_kn = _positive_float(max_load_kn, "La carga máxima")
        height_mm = self._optional_positive_float(height_mm, "La altura")
        mass_kg = self._optional_positive_float(mass_kg, "La masa")
        strength_mpa = _optional_finite_float(strength_mpa, "La resistencia")
        if strength_mpa is not None and strength_mpa < 0:
            raise ValueError("La resistencia no puede ser negativa.")
        actual_age_days = (
            _elapsed_seconds(tested_at, production.produced_at, "La fecha de ensayo")
            / 86400.0
        )
        calculated_strength = self.calculate_compressive_strength(max_load_kn, diameter_mm)
        final_strength = calculated_strength if strength_mpa is None else float(strength_mpa)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO concretos_compression_results (
                    specimen_id, tested_at, actual_age_days, diameter_mm, height_mm,
                    mass_kg, max_load_kn, strength_mpa, failure_type, machine,
                    technician, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(specimen_id) DO UPDATE SET
                    tested_at = excluded.tested_at,
                    actual_age_days = excluded.actual_age_days,
                    diameter_mm = excluded.diameter_mm,
                    height_mm = excluded.height_mm,
                    mass_kg = excluded.mass_kg,
                    max_load_kn = excluded.max_load_kn,
                    strength_mpa = excluded.strength_mpa,
                    failure_type = excluded.failure_type,
                    machine = excluded.machine,
                    technician = excluded.technician,
                    notes = excluded.notes
                """,
                (
                    specimen_id,
                    _serialize_datetime(tested_at),
                    actual_age_days,
                    diameter_mm,
                    height_mm,
                    mass_kg,
                    max_load_kn,
                    final_strength,
                    failure_type.strip(),
                    machine.strip(),
                    technician.strip(),
                    notes.strip(),
                ),
            )
            connection.execute(
                "UPDATE concretos_specimens SET status = 'tested' WHERE id = ?", (specimen_id,)
            )
        result = self.get_compression_result(specimen_id)
        if result is None:
            raise RuntimeError("No fue posible recuperar el resultado de compresión.")
        return result

    def upsert_flexural_result(
        self,
        *,
        specimen_id: int,
        tested_at: datetime,
        width_mm: float,
        depth_mm: float,
        span_mm: float,
        fracture_distance_mm: float | None,
        max_load_kn: float,
        modulus_of_rupture_mpa: float | None = None,
        failure_type: str = "",
        machine: str = "",
        technician: str = "",
        notes: str = "",
    ) -> FlexuralResultRecord:
        specimen, production = self._specimen_and_production(specimen_id)
        if specimen.specimen_type != SpecimenType.BEAM:
            raise ValueError("El módulo de rotura solo puede asignarse a una vigueta.")
        width_mm = _positive_float(width_mm, "El ancho")
        depth_mm = _positive_float(depth_mm, "La profundidad")
        span_mm = _positive_float(span_mm, "La luz entre apoyos")
        max_load_kn = _positive_float(max_load_kn, "La carga máxima")
        fracture_distance_mm = _optional_finite_float(
            fracture_distance_mm, "La distancia de fractura"
        )
        if fracture_distance_mm is not None and fracture_distance_mm < 0:
            raise ValueError("La distancia de fractura no puede ser negativa.")
        modulus_of_rupture_mpa = _optional_finite_float(
            modulus_of_rupture_mpa, "El módulo de rotura"
        )
        if modulus_of_rupture_mpa is not None and modulus_of_rupture_mpa < 0:
            raise ValueError("El módulo de rotura no puede ser negativo.")
        actual_age_days = (
            _elapsed_seconds(tested_at, production.produced_at, "La fecha de ensayo")
            / 86400.0
        )
        calculated_mr = self.calculate_modulus_of_rupture(
            max_load_kn,
            span_mm,
            width_mm,
            depth_mm,
            fracture_distance_mm,
        )
        final_mr = calculated_mr if modulus_of_rupture_mpa is None else float(modulus_of_rupture_mpa)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO concretos_flexural_results (
                    specimen_id, tested_at, actual_age_days, width_mm, depth_mm,
                    span_mm, fracture_distance_mm, max_load_kn,
                    modulus_of_rupture_mpa, failure_type, machine, technician, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(specimen_id) DO UPDATE SET
                    tested_at = excluded.tested_at,
                    actual_age_days = excluded.actual_age_days,
                    width_mm = excluded.width_mm,
                    depth_mm = excluded.depth_mm,
                    span_mm = excluded.span_mm,
                    fracture_distance_mm = excluded.fracture_distance_mm,
                    max_load_kn = excluded.max_load_kn,
                    modulus_of_rupture_mpa = excluded.modulus_of_rupture_mpa,
                    failure_type = excluded.failure_type,
                    machine = excluded.machine,
                    technician = excluded.technician,
                    notes = excluded.notes
                """,
                (
                    specimen_id,
                    _serialize_datetime(tested_at),
                    actual_age_days,
                    width_mm,
                    depth_mm,
                    span_mm,
                    fracture_distance_mm,
                    max_load_kn,
                    final_mr,
                    failure_type.strip(),
                    machine.strip(),
                    technician.strip(),
                    notes.strip(),
                ),
            )
            connection.execute(
                "UPDATE concretos_specimens SET status = 'tested' WHERE id = ?", (specimen_id,)
            )
        result = self.get_flexural_result(specimen_id)
        if result is None:
            raise RuntimeError("No fue posible recuperar el resultado de flexión.")
        return result

    def get_compression_result(self, specimen_id: int) -> CompressionResultRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM concretos_compression_results WHERE specimen_id = ?", (specimen_id,)
            ).fetchone()
        return self._row_to_compression(row) if row else None

    def get_flexural_result(self, specimen_id: int) -> FlexuralResultRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM concretos_flexural_results WHERE specimen_id = ?", (specimen_id,)
            ).fetchone()
        return self._row_to_flexural(row) if row else None

    def delete_specimen_result(self, specimen_id: int) -> bool:
        specimen = self.get_specimen(specimen_id)
        if specimen is None:
            raise ValueError("La muestra seleccionada no existe.")

        table = (
            "concretos_compression_results"
            if specimen.specimen_type == SpecimenType.CYLINDER
            else "concretos_flexural_results"
        )
        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE specimen_id = ?", (specimen_id,)
            )
            deleted = cursor.rowcount > 0
            if deleted and specimen.status != SpecimenStatus.CANCELLED:
                connection.execute(
                    "UPDATE concretos_specimens SET status = 'planned' WHERE id = ?",
                    (specimen_id,),
                )
        return deleted

    def _specimen_and_production(
        self, specimen_id: int
    ) -> tuple[SpecimenRecord, ProductionRecord]:
        specimen = self.get_specimen(specimen_id)
        if specimen is None:
            raise ValueError("La muestra seleccionada no existe.")
        production = self.get_production(specimen.production_id)
        if production is None:
            raise ValueError("La producción asociada ya no existe.")
        return specimen, production

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
    def strength_tests(self, design_id: int, age_days: float | None = None):
        """One sample per production and target age; incomplete/cancelled samples excluded.

        Uses ACI 318-19/301-20: >=2 cylinders 150 mm or >=3 cylinders 100 mm.
        Nominal diameter tolerance 5 mm; actual age tolerance 2% (minimum 0.1 d).
        Historical series selection still requires operator comparability confirmation.
        """
        from concrete_mix_designer.domain.strength import StrengthTest
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT p.id AS production_id, s.id AS specimen_id, s.target_age_days,
                       s.status, cr.strength_mpa, cr.diameter_mm, cr.actual_age_days, cr.tested_at
                FROM concretos_productions p JOIN concretos_specimens s ON s.production_id=p.id
                LEFT JOIN concretos_compression_results cr ON cr.specimen_id=s.id
                WHERE p.design_id=? AND s.specimen_type='cylinder'
                ORDER BY p.id, s.target_age_days, s.id
            """, (design_id,)).fetchall()
        groups = {}
        for row in rows:
            if age_days is None or row['target_age_days'] == age_days:
                groups.setdefault((row['production_id'], row['target_age_days']), []).append(row)
        tests = []
        for (production_id, age), members in groups.items():
            if any(r['status'] != 'tested' or r['strength_mpa'] is None or r['strength_mpa'] <= 0
                   or abs(r['actual_age_days'] - age) > max(.1, age * .02) for r in members):
                continue
            large = all(abs(r['diameter_mm'] - 150) <= 5 for r in members)
            small = all(abs(r['diameter_mm'] - 100) <= 5 for r in members)
            if not ((large and len(members) >= 2) or (small and len(members) >= 3)):
                continue
            tests.append(StrengthTest(f"{production_id}:{age:g}", production_id, age,
                         max(datetime.fromisoformat(r['tested_at']).date() for r in members),
                         tuple(r['specimen_id'] for r in members),
                         statistics.fmean(r['strength_mpa'] for r in members)))
        return sorted(tests, key=lambda test: (test.tested_on, test.key))

    def design_statistics(self, design_id: int) -> list[DesignStatisticsRow]:
        grouped = {}
        for test in self.strength_tests(design_id):
            grouped.setdefault((SpecimenType.CYLINDER, test.age_days), []).append(test.strength_mpa)
        # Flexural results are descriptive specimen statistics, never inputs to f'cr.
        with self._connect() as connection:
            rows = connection.execute("""SELECT s.target_age_days, f.modulus_of_rupture_mpa
                FROM concretos_specimens s JOIN concretos_productions p ON p.id=s.production_id
                JOIN concretos_flexural_results f ON f.specimen_id=s.id
                WHERE p.design_id=? AND s.status='tested'""", (design_id,)).fetchall()
        for row in rows:
            grouped.setdefault((SpecimenType.BEAM, row[0]), []).append(row[1])
        return [DesignStatisticsRow(kind, age, len(values), statistics.fmean(values),
                    min(values), max(values), statistics.stdev(values) if len(values)>1 else None)
                for (kind, age), values in sorted(grouped.items(), key=lambda item: (item[0][0].value,item[0][1]))]

    @staticmethod
    def _serialize_specification(specification: DesignSpecification) -> str:
        try:
            return json.dumps(
                specification.to_dict(),
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except ValueError as error:
            raise ValueError(
                "La especificación contiene valores numéricos no finitos."
            ) from error

    @staticmethod
    def _optional_positive_float(value: object | None, label: str) -> float | None:
        if value is None:
            return None
        return _positive_float(value, label)

    @staticmethod
    def _validate_fresh_measurements(
        slump_mm: float | None,
        spread_d1_mm: float | None,
        spread_d2_mm: float | None,
        air_content_pct: float | None,
        unit_weight_kg_m3: float | None,
    ) -> None:
        for value, label in (
            (slump_mm, "El asentamiento"),
            (spread_d1_mm, "El primer diámetro"),
            (spread_d2_mm, "El segundo diámetro"),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{label} no puede ser negativo.")
        if air_content_pct is not None and not 0.0 <= air_content_pct <= 100.0:
            raise ValueError("El contenido de aire debe estar entre 0 y 100 %.")
        if unit_weight_kg_m3 is not None and unit_weight_kg_m3 <= 0:
            raise ValueError("La masa unitaria debe ser mayor que cero.")

    # ------------------------------------------------------------------
    # Row conversion helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_design(row: sqlite3.Row) -> SavedDesignRecord:
        return SavedDesignRecord(
            id=int(row["id"]),
            family_uid=str(row["family_uid"]),
            revision=int(row["revision"]),
            name=str(row["name"]),
            group_name=str(row["group_name"]) if "group_name" in row.keys() else "",
            description=str(row["description"]),
            source_design_id=int(row["source_design_id"]) if row["source_design_id"] is not None else None,
            design_json=str(row["design_json"]),
            created_at=_parse_datetime(str(row["created_at"])),
            production_count=int(row["production_count"] or 0),
            archived=bool(row["archived"]),
        )

    @staticmethod
    def _row_to_production(row: sqlite3.Row) -> ProductionRecord:
        return ProductionRecord(
            id=int(row["id"]),
            design_id=int(row["design_id"]),
            design_name=str(row["design_name"]),
            design_revision=int(row["design_revision"]),
            design_json_snapshot=str(row["design_json_snapshot"]),
            produced_at=_parse_datetime(str(row["produced_at"])),
            batch_code=str(row["batch_code"]),
            batch_volume_m3=float(row["batch_volume_m3"]),
            notes=str(row["notes"]),
            created_at=_parse_datetime(str(row["created_at"])),
            specimen_count=int(row["specimen_count"] or 0),
            tested_specimen_count=int(row["tested_specimen_count"] or 0),
        )

    @staticmethod
    def _row_to_specimen(row: sqlite3.Row) -> SpecimenRecord:
        return SpecimenRecord(
            id=int(row["id"]),
            production_id=int(row["production_id"]),
            specimen_code=str(row["specimen_code"]),
            specimen_type=SpecimenType(row["specimen_type"]),
            target_age_days=float(row["target_age_days"]),
            planned_test_at=_parse_datetime(str(row["planned_test_at"])),
            status=SpecimenStatus(row["status"]),
            notes=str(row["notes"]),
        )

    @staticmethod
    def _row_to_fresh_test(row: sqlite3.Row) -> FreshTestRecord:
        def optional_float(name: str) -> float | None:
            value = row[name]
            return float(value) if value is not None else None

        return FreshTestRecord(
            id=int(row["id"]),
            production_id=int(row["production_id"]),
            test_type=FreshTestType(row["test_type"]),
            measured_at=_parse_datetime(str(row["measured_at"])),
            elapsed_minutes=int(row["elapsed_minutes"]),
            slump_mm=optional_float("slump_mm"),
            spread_d1_mm=optional_float("spread_d1_mm"),
            spread_d2_mm=optional_float("spread_d2_mm"),
            concrete_temperature_c=optional_float("concrete_temperature_c"),
            air_content_pct=optional_float("air_content_pct"),
            unit_weight_kg_m3=optional_float("unit_weight_kg_m3"),
            notes=str(row["notes"]),
        )

    @staticmethod
    def _row_to_compression(row: sqlite3.Row) -> CompressionResultRecord:
        return CompressionResultRecord(
            id=int(row["id"]),
            specimen_id=int(row["specimen_id"]),
            tested_at=_parse_datetime(str(row["tested_at"])),
            actual_age_days=float(row["actual_age_days"]),
            diameter_mm=float(row["diameter_mm"]),
            height_mm=float(row["height_mm"]) if row["height_mm"] is not None else None,
            mass_kg=float(row["mass_kg"]) if row["mass_kg"] is not None else None,
            max_load_kn=float(row["max_load_kn"]),
            strength_mpa=float(row["strength_mpa"]),
            failure_type=str(row["failure_type"]),
            machine=str(row["machine"]),
            technician=str(row["technician"]),
            notes=str(row["notes"]),
        )

    @staticmethod
    def _row_to_flexural(row: sqlite3.Row) -> FlexuralResultRecord:
        return FlexuralResultRecord(
            id=int(row["id"]),
            specimen_id=int(row["specimen_id"]),
            tested_at=_parse_datetime(str(row["tested_at"])),
            actual_age_days=float(row["actual_age_days"]),
            width_mm=float(row["width_mm"]),
            depth_mm=float(row["depth_mm"]),
            span_mm=float(row["span_mm"]),
            fracture_distance_mm=(
                float(row["fracture_distance_mm"])
                if row["fracture_distance_mm"] is not None
                else None
            ),
            max_load_kn=float(row["max_load_kn"]),
            modulus_of_rupture_mpa=float(row["modulus_of_rupture_mpa"]),
            failure_type=str(row["failure_type"]),
            machine=str(row["machine"]),
            technician=str(row["technician"]),
            notes=str(row["notes"]),
        )
