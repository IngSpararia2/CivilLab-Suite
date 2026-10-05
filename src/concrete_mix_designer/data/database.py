from __future__ import annotations

import json
import math
import sqlite3
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

from civillab_suite.sqlite_support import connect as sqlite_connect
from concrete_mix_designer.domain.metadata_models import (
    GradationPoint,
    MaterialCharacterization,
)
from concrete_mix_designer.domain.models import DosageMode, Material, MaterialCategory

SEED_MATERIALS = [
    ("Agua", MaterialCategory.WATER, 1.000, 0.0, 0.0, DosageMode.MANUAL_KG, 0.0),
    ("Cemento Portland Tipo I", MaterialCategory.CEMENTITIOUS, 3.150, 0.0, 0.0, DosageMode.MANUAL_KG, 0.0),
    ("Ceniza volante", MaterialCategory.CEMENTITIOUS, 2.200, 0.0, 0.0, DosageMode.MANUAL_KG, 0.0),
    ("Escoria granulada", MaterialCategory.CEMENTITIOUS, 2.900, 0.0, 0.0, DosageMode.MANUAL_KG, 0.0),
    ("Arena estándar", MaterialCategory.FINE_AGGREGATE, 2.600, 1.5, 3.0, DosageMode.MANUAL_KG, 0.0),
    ("Grava estándar", MaterialCategory.COARSE_AGGREGATE, 2.700, 0.8, 1.5, DosageMode.MANUAL_KG, 0.0),
    ("Superplastificante", MaterialCategory.ADMIXTURE, 1.080, 0.0, 0.0, DosageMode.PCT_CEMENTITIOUS, 0.8),
    ("Inclusor de aire", MaterialCategory.ADMIXTURE, 1.020, 0.0, 0.0, DosageMode.ML_PER_100KG, 120.0),
    ("Aire", MaterialCategory.AIR, 1.000, 0.0, 0.0, DosageMode.MANUAL_KG, 0.0),
]


def _finite_float(value: object, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} debe ser un número finito.") from error
    if not math.isfinite(numeric):
        raise ValueError(f"{label} debe ser un número finito.")
    return numeric


def _optional_finite_float(value: object | None, label: str) -> float | None:
    return None if value is None else _finite_float(value, label)


class MaterialRepository:
    def __init__(self, database_path: Path, *, seed: bool = True):
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = Path(database_path)
        from civillab_suite.storage import ensure_domain_namespace
        ensure_domain_namespace(self.database_path, "concretos")
        self.seed = seed
        from civillab_suite.core.database import CoreDatabase
        CoreDatabase(database_path).initialize()
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
                CREATE TABLE IF NOT EXISTS concretos_materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    specific_gravity REAL NOT NULL,
                    absorption_pct REAL NOT NULL DEFAULT 0,
                    moisture_pct REAL NOT NULL DEFAULT 0,
                    dosage_mode TEXT NOT NULL DEFAULT 'manual_kg',
                    dosage_value REAL NOT NULL DEFAULT 0,
                    is_seed INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS concretos_material_characterizations (
                    material_id INTEGER PRIMARY KEY
                        REFERENCES concretos_materials(id) ON DELETE CASCADE,
                    supplier TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    lot_code TEXT NOT NULL DEFAULT '',
                    characterization_standard TEXT NOT NULL DEFAULT '',
                    cement_type TEXT NOT NULL DEFAULT '',
                    specific_gravity_dry REAL,
                    specific_gravity_ssd REAL,
                    compacted_unit_weight_kg_m3 REAL,
                    fineness_modulus REAL,
                    nominal_max_size_mm REAL,
                    aggregate_shape TEXT NOT NULL DEFAULT '',
                    aggregate_texture TEXT NOT NULL DEFAULT '',
                    admixture_density_kg_l REAL,
                    water_reduction_pct REAL,
                    recommended_dosage_pct REAL,
                    notes TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS concretos_material_gradations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_id INTEGER NOT NULL
                        REFERENCES concretos_materials(id) ON DELETE CASCADE,
                    sieve_label TEXT NOT NULL,
                    opening_mm REAL NOT NULL,
                    passing_pct REAL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(material_id, sieve_label)
                );

                CREATE INDEX IF NOT EXISTS idx_material_gradations_material
                    ON concretos_material_gradations(material_id, sort_order, opening_mm DESC);
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(concretos_materials)")}
            if "canonical_id" not in columns:
                connection.execute("ALTER TABLE concretos_materials ADD COLUMN canonical_id INTEGER REFERENCES material_objects(id) ON DELETE RESTRICT")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_concretos_material_canonical ON concretos_materials(canonical_id)")
            count = connection.execute("SELECT COUNT(*) FROM concretos_materials").fetchone()[0]
            if count == 0 and self.seed:
                connection.executemany(
                    """
                    INSERT INTO concretos_materials (
                        name, category, specific_gravity, absorption_pct,
                        moisture_pct, dosage_mode, dosage_value, is_seed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    [
                        (
                            name,
                            category.value,
                            sg,
                            absorption,
                            moisture,
                            mode.value,
                            dosage,
                        )
                        for name, category, sg, absorption, moisture, mode, dosage in SEED_MATERIALS
                    ],
                )

        with self._connect() as connection:
            for row in connection.execute("SELECT * FROM concretos_materials WHERE canonical_id IS NULL").fetchall():
                material = self._row_to_material(row)
                self._canonical(connection, material)
                connection.execute("UPDATE concretos_materials SET canonical_id=? WHERE id=?", (material.canonical_id, material.id))

    @staticmethod
    def _canonical(connection, material):
        from civillab_suite.core.database import _normalized
        from concrete_mix_designer.domain.models import CATEGORY_LABELS
        if material.canonical_id is None and material.id is not None:
            existing = connection.execute("SELECT canonical_id FROM concretos_materials WHERE id=?", (material.id,)).fetchone()
            if existing is not None:
                material.canonical_id = existing[0]
        code = "CEMENT" if material.category == MaterialCategory.CEMENTITIOUS else material.category.value.upper()
        connection.execute("INSERT OR IGNORE INTO material_types (code, canonical_name, normalized_name) VALUES (?, ?, ?)",
                           (code, CATEGORY_LABELS[material.category], _normalized(CATEGORY_LABELS[material.category])))
        type_id = connection.execute("SELECT id FROM material_types WHERE code=?", (code,)).fetchone()[0]
        now = datetime.now(timezone.utc).isoformat()
        canonical = None
        if material.canonical_id is not None:
            canonical = connection.execute("SELECT * FROM material_objects WHERE id=?", (material.canonical_id,)).fetchone()
            if canonical is None:
                raise ValueError("La identidad canónica no existe.")
            if canonical["material_type_id"] != type_id:
                referenced = connection.execute("SELECT 1 FROM pie_plans WHERE material_object_id=? UNION ALL SELECT 1 FROM shared_results WHERE material_object_id=?", (material.canonical_id,material.canonical_id)).fetchone()
                if referenced:
                    raise ValueError("No se puede cambiar la categoría de un material con PIE o resultados compartidos.")
                connection.execute("UPDATE material_objects SET material_type_id=? WHERE id=?", (type_id,material.canonical_id))
        elif material.code.strip():
            canonical = connection.execute("SELECT * FROM material_objects WHERE material_type_id=? AND code=?", (type_id, material.code.strip())).fetchone()
        if canonical is not None:
            material.canonical_id = canonical["id"]
            material.code = canonical["code"]
            connection.execute("UPDATE material_objects SET canonical_name=?, updated_at=? WHERE id=?", (material.name, now, material.canonical_id))
        else:
            material.code = material.code.strip() or f"CON-{material.id:06d}"
            cursor = connection.execute("INSERT INTO material_objects (material_type_id, code, canonical_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                                        (type_id, material.code, material.name, now, now))
            material.canonical_id = cursor.lastrowid

    @staticmethod
    def _scope(connection, repository):
        return nullcontext(connection) if connection is not None else repository._connect()

    def list_all(self) -> list[Material]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT m.*, o.canonical_name AS shared_name, o.code AS shared_code FROM concretos_materials m JOIN material_objects o ON o.id=m.canonical_id ORDER BY m.category, o.canonical_name"
            ).fetchall()
        return [self._row_to_material(row) for row in rows]

    def get(self, material_id: int, *, _connection=None) -> Material | None:
        with self._scope(_connection, self) as connection:
            row = connection.execute(
                "SELECT m.*, o.canonical_name AS shared_name, o.code AS shared_code FROM concretos_materials m JOIN material_objects o ON o.id=m.canonical_id WHERE m.id = ?", (material_id,)
            ).fetchone()
        return self._row_to_material(row) if row else None

    def save(self, material: Material, *, _connection=None) -> Material:
        category = MaterialCategory(material.category)
        dosage_mode = DosageMode(material.dosage_mode)
        clean_name = material.name.strip()
        if not clean_name:
            raise ValueError("El material debe tener un nombre.")
        specific_gravity = _finite_float(
            material.specific_gravity, "La gravedad específica"
        )
        absorption_pct = _finite_float(material.absorption_pct, "La absorción")
        moisture_pct = _finite_float(material.moisture_pct, "La humedad")
        dosage_value = _finite_float(material.dosage_value, "La dosificación")
        if specific_gravity <= 0:
            raise ValueError("La gravedad específica debe ser mayor que cero.")
        if absorption_pct < 0:
            raise ValueError("La absorción no puede ser negativa.")
        if moisture_pct < 0:
            raise ValueError("La humedad no puede ser negativa.")
        if dosage_value < 0:
            raise ValueError("La dosificación no puede ser negativa.")

        material.name = clean_name
        material.category = category
        material.dosage_mode = dosage_mode
        material.specific_gravity = specific_gravity
        material.absorption_pct = absorption_pct
        material.moisture_pct = moisture_pct
        material.dosage_value = dosage_value

        values = (
            clean_name,
            category.value,
            specific_gravity,
            absorption_pct,
            moisture_pct,
            dosage_mode.value,
            dosage_value,
            int(material.is_seed),
        )
        with self._scope(_connection, self) as connection:
            if material.id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO concretos_materials (
                        name, category, specific_gravity, absorption_pct,
                        moisture_pct, dosage_mode, dosage_value, is_seed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                material.id = int(cursor.lastrowid)
            else:
                cursor = connection.execute(
                    """
                    UPDATE concretos_materials SET
                        name = ?, category = ?, specific_gravity = ?,
                        absorption_pct = ?, moisture_pct = ?, dosage_mode = ?,
                        dosage_value = ?, is_seed = ?
                    WHERE id = ?
                    """,
                    values + (material.id,),
                )
                if cursor.rowcount == 0:
                    raise ValueError("El material que se intentó actualizar no existe.")
            self._canonical(connection, material)
            connection.execute("UPDATE concretos_materials SET canonical_id=? WHERE id=?", (material.canonical_id, material.id))
        return material

    def get_characterization(self, material_id: int, *, _connection=None) -> MaterialCharacterization:
        with self._scope(_connection, self) as connection:
            row = connection.execute(
                "SELECT * FROM concretos_material_characterizations WHERE material_id = ?",
                (material_id,),
            ).fetchone()
            gradation_rows = connection.execute(
                """
                SELECT sieve_label, opening_mm, passing_pct, sort_order
                FROM concretos_material_gradations
                WHERE material_id = ?
                ORDER BY sort_order, opening_mm DESC
                """,
                (material_id,),
            ).fetchall()

        characterization = (
            self._row_to_characterization(row)
            if row is not None
            else MaterialCharacterization(material_id=material_id)
        )
        characterization.gradation = [
            GradationPoint(
                sieve_label=str(item["sieve_label"]),
                opening_mm=float(item["opening_mm"]),
                passing_pct=(
                    float(item["passing_pct"])
                    if item["passing_pct"] is not None
                    else None
                ),
                sort_order=int(item["sort_order"]),
            )
            for item in gradation_rows
        ]
        return characterization

    def list_characterizations(self) -> dict[int, MaterialCharacterization]:
        """Two bounded catalog queries, independent of the number of visible rows."""
        with self._connect() as connection:
            records = {row['material_id']: self._row_to_characterization(row)
                       for row in connection.execute("SELECT * FROM concretos_material_characterizations")}
            for row in connection.execute("SELECT * FROM concretos_material_gradations ORDER BY material_id, sort_order, opening_mm DESC"):
                item = records.setdefault(row['material_id'], MaterialCharacterization(material_id=row['material_id']))
                item.gradation.append(GradationPoint(row['sieve_label'],row['opening_mm'],row['passing_pct'],row['sort_order']))
        return records

    def save_characterization(
        self,
        material_id: int,
        characterization: MaterialCharacterization,
        *, _connection=None,
    ) -> MaterialCharacterization:
        if self.get(material_id, _connection=_connection) is None:
            raise ValueError("El material seleccionado no existe.")
        characterization.material_id = material_id
        positive_fields = (
            ("specific_gravity_dry", "La gravedad específica seca"),
            ("specific_gravity_ssd", "La gravedad específica SSS"),
            ("compacted_unit_weight_kg_m3", "La masa unitaria compactada"),
            ("nominal_max_size_mm", "El tamaño máximo nominal"),
            ("admixture_density_kg_l", "La densidad del aditivo"),
        )
        for field_name, label in positive_fields:
            value = _optional_finite_float(getattr(characterization, field_name), label)
            if value is not None and value <= 0:
                raise ValueError(f"{label} debe ser mayor que cero.")
            setattr(characterization, field_name, value)
        nonnegative_fields = (
            ("fineness_modulus", "El módulo de finura"),
            ("water_reduction_pct", "La reducción de agua"),
            ("recommended_dosage_pct", "La dosificación recomendada"),
        )
        for field_name, label in nonnegative_fields:
            value = _optional_finite_float(getattr(characterization, field_name), label)
            if value is not None and value < 0:
                raise ValueError(f"{label} no puede ser negativa.")
            setattr(characterization, field_name, value)
        if (
            characterization.water_reduction_pct is not None
            and characterization.water_reduction_pct > 100
        ):
            raise ValueError("La reducción de agua debe estar entre 0 y 100 %.")
        with self._scope(_connection, self) as connection:
            connection.execute(
                """
                INSERT INTO concretos_material_characterizations (
                    material_id, supplier, source, lot_code,
                    characterization_standard, cement_type,
                    specific_gravity_dry, specific_gravity_ssd,
                    compacted_unit_weight_kg_m3, fineness_modulus,
                    nominal_max_size_mm, aggregate_shape, aggregate_texture,
                    admixture_density_kg_l, water_reduction_pct,
                    recommended_dosage_pct, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(material_id) DO UPDATE SET
                    supplier = excluded.supplier,
                    source = excluded.source,
                    lot_code = excluded.lot_code,
                    characterization_standard = excluded.characterization_standard,
                    cement_type = excluded.cement_type,
                    specific_gravity_dry = excluded.specific_gravity_dry,
                    specific_gravity_ssd = excluded.specific_gravity_ssd,
                    compacted_unit_weight_kg_m3 = excluded.compacted_unit_weight_kg_m3,
                    fineness_modulus = excluded.fineness_modulus,
                    nominal_max_size_mm = excluded.nominal_max_size_mm,
                    aggregate_shape = excluded.aggregate_shape,
                    aggregate_texture = excluded.aggregate_texture,
                    admixture_density_kg_l = excluded.admixture_density_kg_l,
                    water_reduction_pct = excluded.water_reduction_pct,
                    recommended_dosage_pct = excluded.recommended_dosage_pct,
                    notes = excluded.notes
                """,
                (
                    material_id,
                    characterization.supplier.strip(),
                    characterization.source.strip(),
                    characterization.lot_code.strip(),
                    characterization.characterization_standard.strip(),
                    characterization.cement_type.strip(),
                    characterization.specific_gravity_dry,
                    characterization.specific_gravity_ssd,
                    characterization.compacted_unit_weight_kg_m3,
                    characterization.fineness_modulus,
                    characterization.nominal_max_size_mm,
                    characterization.aggregate_shape.strip(),
                    characterization.aggregate_texture.strip(),
                    characterization.admixture_density_kg_l,
                    characterization.water_reduction_pct,
                    characterization.recommended_dosage_pct,
                    characterization.notes.strip(),
                ),
            )
            connection.execute(
                "DELETE FROM concretos_material_gradations WHERE material_id = ?", (material_id,)
            )
            for position, point in enumerate(characterization.gradation):
                label = point.sieve_label.strip()
                if not label:
                    continue
                passing = point.passing_pct
                opening_mm = _finite_float(point.opening_mm, "La abertura del tamiz")
                if opening_mm <= 0:
                    raise ValueError("La abertura del tamiz debe ser mayor que cero.")
                passing = _optional_finite_float(passing, "El porcentaje pasante")
                if passing is not None and not 0.0 <= passing <= 100.0:
                    raise ValueError("Los porcentajes pasantes deben estar entre 0 y 100.")
                connection.execute(
                    """
                    INSERT INTO concretos_material_gradations (
                        material_id, sieve_label, opening_mm, passing_pct, sort_order
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        material_id,
                        label,
                        opening_mm,
                        passing,
                        int(point.sort_order if point.sort_order else position),
                    ),
                )
        return self.get_characterization(material_id, _connection=_connection)

    def save_with_characterization(
        self,
        material: Material,
        characterization: MaterialCharacterization,
    ) -> tuple[Material, MaterialCharacterization]:
        original_id, original_canonical = material.id, material.canonical_id
        # A measured SSD gravity (or liquid density) is the calculation basis;
        # the generic column is its compatibility cache, not another measurement.
        if material.category in (MaterialCategory.FINE_AGGREGATE, MaterialCategory.COARSE_AGGREGATE):
            if characterization.specific_gravity_ssd is not None:
                material.specific_gravity = characterization.specific_gravity_ssd
        elif material.category == MaterialCategory.ADMIXTURE and characterization.admixture_density_kg_l is not None:
            material.specific_gravity = characterization.admixture_density_kg_l
        try:
            with self._connect() as connection:
                saved = self.save(material, _connection=connection)
                saved_characterization = self.save_characterization(saved.id, characterization, _connection=connection)
        except Exception:
            material.id, material.canonical_id = original_id, original_canonical
            raise
        return saved, saved_characterization

    def delete(self, material_id: int) -> None:
        material = self.get(material_id)
        if material is None:
            raise ValueError("El material seleccionado no existe.")
        if material.is_seed:
            raise ValueError("Los materiales iniciales no se pueden eliminar.")
        with self._connect() as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, column in (("concretos_mix_designs", "design_json"), ("concretos_productions", "design_json_snapshot")):
                if table in tables:
                    for row in connection.execute(f"SELECT {column} FROM {table}"):
                        if any(item["material"].get("id") == material_id for item in json.loads(row[0]).get("components", [])):
                            raise ValueError("El material está referenciado por diseños o producción; conserve su identidad histórica.")
            if connection.execute("SELECT 1 FROM pie_plans WHERE material_object_id=? UNION SELECT 1 FROM shared_results WHERE material_object_id=?", (material.canonical_id, material.canonical_id)).fetchone():
                raise ValueError("El material está referenciado por PIE o resultados compartidos.")
            connection.execute(
                "DELETE FROM concretos_material_gradations WHERE material_id = ?", (material_id,)
            )
            connection.execute(
                "DELETE FROM concretos_material_characterizations WHERE material_id = ?",
                (material_id,),
            )
            connection.execute("DELETE FROM concretos_materials WHERE id = ?", (material_id,))
            connection.execute("DELETE FROM material_objects WHERE id=?", (material.canonical_id,))

    @staticmethod
    def _row_to_material(row: sqlite3.Row) -> Material:
        return Material(
            id=int(row["id"]),
            name=str(row["shared_name"] if "shared_name" in row.keys() else row["name"]),
            category=MaterialCategory(row["category"]),
            specific_gravity=float(row["specific_gravity"]),
            absorption_pct=float(row["absorption_pct"]),
            moisture_pct=float(row["moisture_pct"]),
            dosage_mode=DosageMode(row["dosage_mode"]),
            dosage_value=float(row["dosage_value"]),
            is_seed=bool(row["is_seed"]),
            canonical_id=row["canonical_id"] if "canonical_id" in row.keys() else None,
            code=str(row["shared_code"]) if "shared_code" in row.keys() else "",
        )

    @staticmethod
    def _row_to_characterization(row: sqlite3.Row) -> MaterialCharacterization:
        def optional_float(name: str) -> float | None:
            value = row[name]
            return float(value) if value is not None else None

        return MaterialCharacterization(
            material_id=int(row["material_id"]),
            supplier=str(row["supplier"]),
            source=str(row["source"]),
            lot_code=str(row["lot_code"]),
            characterization_standard=str(row["characterization_standard"]),
            cement_type=str(row["cement_type"]),
            specific_gravity_dry=optional_float("specific_gravity_dry"),
            specific_gravity_ssd=optional_float("specific_gravity_ssd"),
            compacted_unit_weight_kg_m3=optional_float(
                "compacted_unit_weight_kg_m3"
            ),
            fineness_modulus=optional_float("fineness_modulus"),
            nominal_max_size_mm=optional_float("nominal_max_size_mm"),
            aggregate_shape=str(row["aggregate_shape"]),
            aggregate_texture=str(row["aggregate_texture"]),
            admixture_density_kg_l=optional_float("admixture_density_kg_l"),
            water_reduction_pct=optional_float("water_reduction_pct"),
            recommended_dosage_pct=optional_float("recommended_dosage_pct"),
            notes=str(row["notes"]),
        )
