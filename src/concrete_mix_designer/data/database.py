from __future__ import annotations

import math
import sqlite3
from pathlib import Path

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
    def __init__(self, database_path: Path):
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS materials (
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

                CREATE TABLE IF NOT EXISTS material_characterizations (
                    material_id INTEGER PRIMARY KEY
                        REFERENCES materials(id) ON DELETE CASCADE,
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

                CREATE TABLE IF NOT EXISTS material_gradations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_id INTEGER NOT NULL
                        REFERENCES materials(id) ON DELETE CASCADE,
                    sieve_label TEXT NOT NULL,
                    opening_mm REAL NOT NULL,
                    passing_pct REAL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(material_id, sieve_label)
                );

                CREATE INDEX IF NOT EXISTS idx_material_gradations_material
                    ON material_gradations(material_id, sort_order, opening_mm DESC);
                """
            )
            count = connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
            if count == 0:
                connection.executemany(
                    """
                    INSERT INTO materials (
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

    def list_all(self) -> list[Material]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM materials ORDER BY category, name"
            ).fetchall()
        return [self._row_to_material(row) for row in rows]

    def get(self, material_id: int) -> Material | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM materials WHERE id = ?", (material_id,)
            ).fetchone()
        return self._row_to_material(row) if row else None

    def save(self, material: Material) -> Material:
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
        with self._connect() as connection:
            if material.id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO materials (
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
                    UPDATE materials SET
                        name = ?, category = ?, specific_gravity = ?,
                        absorption_pct = ?, moisture_pct = ?, dosage_mode = ?,
                        dosage_value = ?, is_seed = ?
                    WHERE id = ?
                    """,
                    values + (material.id,),
                )
                if cursor.rowcount == 0:
                    raise ValueError("El material que se intentó actualizar no existe.")
        return material

    def get_characterization(self, material_id: int) -> MaterialCharacterization:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM material_characterizations WHERE material_id = ?",
                (material_id,),
            ).fetchone()
            gradation_rows = connection.execute(
                """
                SELECT sieve_label, opening_mm, passing_pct, sort_order
                FROM material_gradations
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

    def save_characterization(
        self,
        material_id: int,
        characterization: MaterialCharacterization,
    ) -> MaterialCharacterization:
        if self.get(material_id) is None:
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
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO material_characterizations (
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
                "DELETE FROM material_gradations WHERE material_id = ?", (material_id,)
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
                    INSERT INTO material_gradations (
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
        return self.get_characterization(material_id)

    def save_with_characterization(
        self,
        material: Material,
        characterization: MaterialCharacterization,
    ) -> tuple[Material, MaterialCharacterization]:
        saved = self.save(material)
        if saved.id is None:
            raise RuntimeError("No fue posible identificar el material guardado.")
        saved_characterization = self.save_characterization(saved.id, characterization)
        return saved, saved_characterization

    def delete(self, material_id: int) -> None:
        material = self.get(material_id)
        if material is None:
            raise ValueError("El material seleccionado no existe.")
        if material.is_seed:
            raise ValueError("Los materiales iniciales no se pueden eliminar.")
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM material_gradations WHERE material_id = ?", (material_id,)
            )
            connection.execute(
                "DELETE FROM material_characterizations WHERE material_id = ?",
                (material_id,),
            )
            connection.execute("DELETE FROM materials WHERE id = ?", (material_id,))

    @staticmethod
    def _row_to_material(row: sqlite3.Row) -> Material:
        return Material(
            id=int(row["id"]),
            name=str(row["name"]),
            category=MaterialCategory(row["category"]),
            specific_gravity=float(row["specific_gravity"]),
            absorption_pct=float(row["absorption_pct"]),
            moisture_pct=float(row["moisture_pct"]),
            dosage_mode=DosageMode(row["dosage_mode"]),
            dosage_value=float(row["dosage_value"]),
            is_seed=bool(row["is_seed"]),
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
