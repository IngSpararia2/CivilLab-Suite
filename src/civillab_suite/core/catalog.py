from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .database import CoreDatabase, _normalized


CATALOG_SEED_KEY = "civillab_catalog"
CATALOG_SEED_VERSION = 2


@dataclass(frozen=True, slots=True)
class CatalogMaterialType:
    id: int
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class CatalogAssay:
    id: int
    name: str
    modules: tuple[str, ...]
    method_names: tuple[str, ...]
    standards: tuple[str, ...]
    materials: tuple[str, ...]
    requirements: tuple[str, ...] = ()
    equipment: str = ""
    procedure: str = ""
    normative_frequency: str = ""


@dataclass(frozen=True, slots=True)
class MaterialObject:
    id: int
    material_type_id: int
    code: str
    name: str
    supplier_source: str
    description: str
    active: bool


_SUITE_STANDARDS = (
    (
        "ACI", "ACI PRC-211.1", "2022",
        "Selección y ajuste de proporciones de concreto de densidad normal y alta",
    ),
    ("ASTM", "C33/C33M", "", "Especificación para agregados de concreto"),
    ("ASTM", "C150/C150M", "", "Especificación para cemento Portland"),
    ("ASTM", "C143/C143M", "", "Asentamiento del concreto hidráulico"),
    ("ASTM", "C494/C494M", "", "Especificación para aditivos químicos"),
)

_CONCRETE_ASSAYS = (
    (
        "Asentamiento del concreto hidráulico",
        "SLUMP_ASTMC143",
        "Ensayo de asentamiento",
        "ASTM",
        "C143/C143M",
    ),
)


class CatalogService:
    """Read-only operational catalog plus controlled, versioned application seeds."""

    def __init__(self, database: CoreDatabase):
        self.database = database

    def apply_builtin_seed(self) -> bool:
        payload = {
            "version": CATALOG_SEED_VERSION,
            "standards": _SUITE_STANDARDS,
            "assays": _CONCRETE_ASSAYS,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            applied = connection.execute(
                "SELECT version, fingerprint FROM catalog_seed_versions WHERE seed_key = ?",
                (CATALOG_SEED_KEY,),
            ).fetchone()
            if (
                applied is not None
                and int(applied["version"]) >= CATALOG_SEED_VERSION
                and str(applied["fingerprint"]) == fingerprint
            ):
                return False

            standard_ids: dict[tuple[str, str], int] = {}
            for issuer, code, edition, title in _SUITE_STANDARDS:
                identity = (_normalized(issuer), _normalized(code), _normalized(edition))
                connection.execute(
                    """
                    INSERT INTO standards (
                        issuer, code, edition, title, source_reference,
                        location_reference, verification_status,
                        issuer_key, code_key, edition_key
                    ) VALUES (?, ?, ?, ?, '', '', 'REFERENCE_ONLY', ?, ?, ?)
                    ON CONFLICT(issuer_key, code_key, edition_key) DO UPDATE SET
                        title = excluded.title
                    """,
                    (issuer, code, edition, title, *identity),
                )
                row = connection.execute(
                    """
                    SELECT id FROM standards
                    WHERE issuer_key = ? AND code_key = ? AND edition_key = ?
                    """,
                    identity,
                ).fetchone()
                assert row is not None
                standard_id = int(row["id"])
                standard_ids[(issuer, code)] = standard_id
                connection.execute(
                    """
                    INSERT INTO standard_modules (standard_id, module_id, source)
                    VALUES (?, 'concretos', ?)
                    ON CONFLICT(standard_id, module_id) DO UPDATE SET source = excluded.source
                    """,
                    (standard_id, f"{CATALOG_SEED_KEY}_v{CATALOG_SEED_VERSION}"),
                )

            for assay_name, source_key, display_name, issuer, standard_code in _CONCRETE_ASSAYS:
                assay_id = self.database._upsert_assay(connection, assay_name)
                connection.execute(
                    """
                    INSERT INTO assay_modules (assay_id, module_id, source)
                    VALUES (?, 'concretos', ?)
                    ON CONFLICT(assay_id, module_id) DO UPDATE SET source = excluded.source
                    """,
                    (assay_id, f"{CATALOG_SEED_KEY}_v{CATALOG_SEED_VERSION}"),
                )
                connection.execute(
                    """
                    INSERT INTO assay_methods (
                        assay_id, module_id, source_key, display_name, active
                    ) VALUES (?, 'concretos', ?, ?, 1)
                    ON CONFLICT(module_id, source_key) DO UPDATE SET
                        assay_id = excluded.assay_id,
                        display_name = excluded.display_name,
                        active = 1
                    """,
                    (assay_id, source_key, display_name),
                )
                method = connection.execute(
                    """
                    SELECT id FROM assay_methods
                    WHERE module_id = 'concretos' AND source_key = ?
                    """,
                    (source_key,),
                ).fetchone()
                assert method is not None
                standard_id = standard_ids[(issuer, standard_code)]
                connection.execute(
                    """
                    INSERT OR IGNORE INTO method_standards (method_id, standard_id)
                    VALUES (?, ?)
                    """,
                    (int(method["id"]), standard_id),
                )
                connection.execute(
                    """
                    INSERT INTO standard_assays (standard_id, assay_id, source)
                    VALUES (?, ?, ?)
                    ON CONFLICT(standard_id, assay_id) DO UPDATE SET source = excluded.source
                    """,
                    (
                        standard_id,
                        assay_id,
                        f"{CATALOG_SEED_KEY}_v{CATALOG_SEED_VERSION}",
                    ),
                )

            # Aggregate/cement controls already supplied by the initial catalog are
            # genuinely shared with Concretos. The application seed owns this mapping;
            # the compatibility importer itself remains a faithful Prefabricados import.
            concrete_material_codes = ("COARSE_AGGREGATE", "FINE_AGGREGATE", "CEMENT")
            placeholders = ",".join("?" for _ in concrete_material_codes)
            shared_rows = connection.execute(
                f"""
                SELECT amt.*, mt.id AS target_material_id
                FROM assay_material_types amt
                JOIN material_types mt ON mt.id = amt.material_type_id
                WHERE amt.module_id = 'prefabricados'
                  AND mt.code IN ({placeholders})
                """,
                concrete_material_codes,
            ).fetchall()
            for item in shared_rows:
                connection.execute(
                    """
                    INSERT INTO assay_modules (assay_id, module_id, source)
                    VALUES (?, 'concretos', ?)
                    ON CONFLICT(assay_id, module_id) DO UPDATE SET source = excluded.source
                    """,
                    (item["assay_id"], f"{CATALOG_SEED_KEY}_v{CATALOG_SEED_VERSION}"),
                )
                connection.execute(
                    """
                    INSERT INTO material_type_modules (material_type_id, module_id, source)
                    VALUES (?, 'concretos', ?)
                    ON CONFLICT(material_type_id, module_id) DO UPDATE SET source = excluded.source
                    """,
                    (
                        item["target_material_id"],
                        f"{CATALOG_SEED_KEY}_v{CATALOG_SEED_VERSION}",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO assay_material_types (
                        assay_id, material_type_id, module_id, standard_id,
                        normative_frequency, procedure_detail, preferred, source
                    ) VALUES (?, ?, 'concretos', ?, ?, ?, ?, ?)
                    ON CONFLICT(assay_id, material_type_id, module_id) DO UPDATE SET
                        standard_id = excluded.standard_id,
                        normative_frequency = excluded.normative_frequency,
                        procedure_detail = excluded.procedure_detail,
                        preferred = excluded.preferred,
                        source = excluded.source
                    """,
                    (
                        item["assay_id"], item["target_material_id"], item["standard_id"],
                        item["normative_frequency"], item["procedure_detail"], item["preferred"],
                        f"{CATALOG_SEED_KEY}_v{CATALOG_SEED_VERSION}",
                    ),
                )

            shared_requirement_rows = connection.execute(
                f"""
                SELECT cr.*
                FROM catalog_requirements cr
                JOIN material_types mt ON mt.id = cr.material_type_id
                WHERE cr.module_id = 'prefabricados'
                  AND mt.code IN ({placeholders})
                """,
                concrete_material_codes,
            ).fetchall()
            for item in shared_requirement_rows:
                connection.execute(
                    """
                    INSERT INTO catalog_requirements (
                        source_key, material_type_id, assay_id, standard_id, module_id,
                        minimum, maximum, unit, comparison_operator, requirement_text,
                        condition_text, aggregation, age_days, grading, source_detail,
                        verification_status
                    ) VALUES (?, ?, ?, ?, 'concretos', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(module_id, source_key) DO UPDATE SET
                        material_type_id = excluded.material_type_id,
                        assay_id = excluded.assay_id,
                        standard_id = excluded.standard_id,
                        minimum = excluded.minimum,
                        maximum = excluded.maximum,
                        unit = excluded.unit,
                        comparison_operator = excluded.comparison_operator,
                        requirement_text = excluded.requirement_text,
                        condition_text = excluded.condition_text,
                        aggregation = excluded.aggregation,
                        age_days = excluded.age_days,
                        grading = excluded.grading,
                        source_detail = excluded.source_detail,
                        verification_status = excluded.verification_status
                    """,
                    (
                        item["source_key"], item["material_type_id"], item["assay_id"],
                        item["standard_id"], item["minimum"], item["maximum"], item["unit"],
                        item["comparison_operator"], item["requirement_text"],
                        item["condition_text"], item["aggregation"], item["age_days"],
                        item["grading"], item["source_detail"], item["verification_status"],
                    ),
                )
            connection.execute(
                """
                INSERT INTO catalog_seed_versions (seed_key, version, fingerprint, applied_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(seed_key) DO UPDATE SET
                    version = excluded.version,
                    fingerprint = excluded.fingerprint,
                    applied_at = excluded.applied_at
                """,
                (CATALOG_SEED_KEY, CATALOG_SEED_VERSION, fingerprint, now),
            )
        return True

    def list_material_types(
        self, module_ids: str | Iterable[str] | None = None
    ) -> list[CatalogMaterialType]:
        modules = self._module_tuple(module_ids)
        query = """
            SELECT DISTINCT mt.id, mt.code, mt.canonical_name
            FROM material_types mt
        """
        parameters: tuple[object, ...] = ()
        if modules:
            placeholders = ",".join("?" for _ in modules)
            query += (
                " JOIN material_type_modules mtm ON mtm.material_type_id = mt.id"
                f" WHERE mt.active = 1 AND mtm.module_id IN ({placeholders})"
            )
            parameters = modules
        else:
            query += " WHERE mt.active = 1"
        query += " ORDER BY mt.canonical_name COLLATE NOCASE"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            CatalogMaterialType(int(row["id"]), str(row["code"]), str(row["canonical_name"]))
            for row in rows
        ]

    def list_assays(
        self, module_ids: str | Iterable[str] | None = None
    ) -> list[CatalogAssay]:
        modules = self._module_tuple(module_ids)
        where = ""
        parameters: tuple[object, ...] = ()
        if modules:
            placeholders = ",".join("?" for _ in modules)
            where = f"WHERE am.module_id IN ({placeholders})"
            parameters = modules
        with self.database.connect() as connection:
            assay_rows = connection.execute(
                f"""
                SELECT DISTINCT a.id, a.canonical_name
                FROM assays a
                JOIN assay_modules am ON am.assay_id = a.id
                {where}
                ORDER BY a.canonical_name COLLATE NOCASE
                """,
                parameters,
            ).fetchall()
            output: list[CatalogAssay] = []
            for row in assay_rows:
                assay_id = int(row["id"])
                module_filter = ""
                detail_parameters: list[object] = [assay_id]
                if modules:
                    placeholders = ",".join("?" for _ in modules)
                    module_filter = f" AND module_id IN ({placeholders})"
                    detail_parameters.extend(modules)
                linked_modules = tuple(
                    str(item[0])
                    for item in connection.execute(
                        "SELECT module_id FROM assay_modules WHERE assay_id = ?"
                        + module_filter + " ORDER BY module_id",
                        detail_parameters,
                    )
                )
                method_rows = connection.execute(
                    """
                    SELECT DISTINCT m.display_name, m.equipment, m.procedure_summary
                    FROM assay_methods m
                    WHERE m.assay_id = ? AND m.active = 1
                    ORDER BY m.display_name COLLATE NOCASE
                    """,
                    (assay_id,),
                ).fetchall()
                standard_rows = connection.execute(
                    """
                    SELECT DISTINCT s.issuer, s.code, s.edition
                    FROM standards s
                    JOIN standard_assays sa ON sa.standard_id = s.id
                    WHERE sa.assay_id = ?
                    ORDER BY s.issuer, s.code, s.edition
                    """,
                    (assay_id,),
                ).fetchall()
                material_query = """
                    SELECT DISTINCT mt.canonical_name, amt.normative_frequency,
                           amt.procedure_detail
                    FROM assay_material_types amt
                    JOIN material_types mt ON mt.id = amt.material_type_id
                    WHERE amt.assay_id = ?
                """
                material_parameters: list[object] = [assay_id]
                if modules:
                    placeholders = ",".join("?" for _ in modules)
                    material_query += f" AND amt.module_id IN ({placeholders})"
                    material_parameters.extend(modules)
                material_query += " ORDER BY mt.canonical_name COLLATE NOCASE"
                material_rows = connection.execute(
                    material_query, material_parameters
                ).fetchall()
                requirement_query = """
                    SELECT mt.canonical_name AS material_name, cr.*
                    FROM catalog_requirements cr
                    JOIN material_types mt ON mt.id = cr.material_type_id
                    WHERE cr.assay_id = ?
                """
                requirement_parameters: list[object] = [assay_id]
                if modules:
                    placeholders = ",".join("?" for _ in modules)
                    requirement_query += f" AND cr.module_id IN ({placeholders})"
                    requirement_parameters.extend(modules)
                requirement_query += " ORDER BY mt.canonical_name, cr.source_key"
                requirement_rows = connection.execute(
                    requirement_query, requirement_parameters
                ).fetchall()
                output.append(
                    CatalogAssay(
                        id=assay_id,
                        name=str(row["canonical_name"]),
                        modules=linked_modules,
                        method_names=tuple(str(item["display_name"]) for item in method_rows),
                        standards=tuple(
                            " ".join(
                                part for part in (
                                    str(item["issuer"]), str(item["code"]),
                                    str(item["edition"]),
                                ) if part
                            )
                            for item in standard_rows
                        ),
                        materials=tuple(str(item["canonical_name"]) for item in material_rows),
                        requirements=tuple(
                            self._requirement_label(item) for item in requirement_rows
                        ),
                        equipment=next(
                            (str(item["equipment"]) for item in method_rows if item["equipment"]),
                            "",
                        ),
                        procedure=next(
                            (
                                str(item["procedure_detail"])
                                for item in material_rows if item["procedure_detail"]
                            ),
                            next(
                                (
                                    str(item["procedure_summary"])
                                    for item in method_rows if item["procedure_summary"]
                                ),
                                "",
                            ),
                        ),
                        normative_frequency=next(
                            (
                                str(item["normative_frequency"])
                                for item in material_rows if item["normative_frequency"]
                            ),
                            "",
                        ),
                    )
                )
        return output

    def create_material_object(
        self,
        *,
        material_type_id: int,
        code: str,
        name: str,
        supplier_source: str = "",
        description: str = "",
    ) -> MaterialObject:
        code = code.strip()
        name = name.strip()
        if not code or not name:
            raise ValueError("El código y el nombre del material son obligatorios.")
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO material_objects (
                    material_type_id, code, canonical_name, supplier_source,
                    description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(material_type_id, code) DO UPDATE SET
                    canonical_name = excluded.canonical_name,
                    supplier_source = excluded.supplier_source,
                    description = excluded.description,
                    active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    material_type_id, code, name, supplier_source.strip(),
                    description.strip(), now, now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM material_objects
                WHERE material_type_id = ? AND code = ?
                """,
                (material_type_id, code),
            ).fetchone()
        assert row is not None
        return self._material_object(row)

    def list_material_objects(self, material_type_id: int | None = None) -> list[MaterialObject]:
        query = "SELECT * FROM material_objects WHERE active = 1"
        parameters: tuple[object, ...] = ()
        if material_type_id is not None:
            query += " AND material_type_id = ?"
            parameters = (material_type_id,)
        query += " ORDER BY canonical_name COLLATE NOCASE, code"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._material_object(row) for row in rows]

    @staticmethod
    def _module_tuple(module_ids: str | Iterable[str] | None) -> tuple[str, ...]:
        if module_ids is None:
            return ()
        if isinstance(module_ids, str):
            return (module_ids,)
        return tuple(dict.fromkeys(module_ids))

    @staticmethod
    def _material_object(row: sqlite3.Row) -> MaterialObject:
        return MaterialObject(
            id=int(row["id"]),
            material_type_id=int(row["material_type_id"]),
            code=str(row["code"]),
            name=str(row["canonical_name"]),
            supplier_source=str(row["supplier_source"]),
            description=str(row["description"]),
            active=bool(row["active"]),
        )

    @staticmethod
    def _requirement_label(row: sqlite3.Row) -> str:
        minimum = row["minimum"]
        maximum = row["maximum"]
        unit = str(row["unit"])
        operator = str(row["comparison_operator"])
        if row["requirement_text"]:
            requirement = str(row["requirement_text"])
        elif minimum is not None and maximum is not None:
            requirement = f"{minimum:g} a {maximum:g} {unit}".strip()
        elif minimum is not None:
            requirement = f"{operator or '≥'} {minimum:g} {unit}".strip()
        elif maximum is not None:
            requirement = f"{operator or '≤'} {maximum:g} {unit}".strip()
        else:
            requirement = "Requisito documental"
        context = " · ".join(
            value for value in (
                str(row["material_name"]), str(row["grading"]),
                str(row["condition_text"]), str(row["aggregation"]),
                f"{row['age_days']} días" if row["age_days"] is not None else "",
            ) if value
        )
        source = " · ".join(
            value for value in (
                str(row["source_detail"]), str(row["verification_status"]),
            ) if value
        )
        return " — ".join(value for value in (context, requirement, source) if value)
