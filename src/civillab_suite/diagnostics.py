"""Read-only workspace diagnostics. Exit 1 means data/schema errors."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from civillab_suite.storage import CONCRETE_TABLES, PREFAB_TABLES, is_unified, validate_sqlite


def diagnose(path: Path) -> dict:
    path = Path(path)
    report = {"path": str(path), "errors": [], "warnings": [], "counts": {}}
    errors = report["errors"]
    if not path.is_file():
        errors.append("No existe la base de datos.")
        return report
    try:
        report["counts"] = validate_sqlite(path)
        if not is_unified(path):
            errors.append("Falta la migración de workspace unificado v1.")
        counts = report["counts"]
        required = {
            "material_objects",
            "material_types",
            "assays",
            "assay_methods",
            "standards",
            "pie_plans",
            "shared_results",
            "schema_migrations",
        }
        required.update("concretos_" + name for name in CONCRETE_TABLES)
        required.update("prefabricados_" + name for name in PREFAB_TABLES)
        errors.extend(f"Falta tabla {name}" for name in sorted(required - counts.keys()))
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            from concrete_mix_designer.domain.models import MixDesign

            for table in counts:
                columns = [row[1] for row in db.execute(f'PRAGMA table_info("{table}")')]
                json_columns = [name for name in columns if "json" in name]
                date_columns = [
                    name
                    for name in columns
                    if name.endswith(("_at", "_date", "_on", "_until"))
                    or name == "occurrence_start"
                ]
                for row in db.execute(f'SELECT * FROM "{table}"'):
                    identity = row["id"] if "id" in columns else "—"
                    for column in json_columns:
                        if not row[column]:
                            continue
                        try:
                            value = json.loads(
                                row[column],
                                parse_constant=lambda token: (_ for _ in ()).throw(
                                    ValueError(token)
                                ),
                            )
                            if column in {"design_json", "design_json_snapshot"}:
                                design = MixDesign.from_dict(value)
                                if design.parameters.target_volume_l <= 0:
                                    raise ValueError("volumen no positivo")
                                if len({c.uid for c in design.components}) != len(
                                    design.components
                                ):
                                    raise ValueError("componentes duplicados")
                                for c in design.components:
                                    if (
                                        not math.isfinite(c.quantity)
                                        or c.quantity < 0
                                        or c.material.specific_gravity <= 0
                                    ):
                                        raise ValueError("cantidad/gravedad inválida")
                        except (ValueError, TypeError, KeyError, AttributeError) as exc:
                            errors.append(f"{table}[{identity}].{column}: {exc}")
                    for column in date_columns:
                        if row[column]:
                            try:
                                datetime.fromisoformat(str(row[column]))
                            except ValueError:
                                errors.append(f"{table}[{identity}].{column}: fecha inválida")
            for table, keys in (
                ("material_objects", "material_type_id,code"),
                ("assays", "normalized_name"),
                ("concretos_materials", "canonical_id"),
                ("shared_results", "origin_module_id,source_type,source_id"),
            ):
                if table in counts:
                    if db.execute(
                        f'SELECT 1 FROM "{table}" GROUP BY {keys} HAVING count(*)>1'
                    ).fetchone():
                        errors.append(f"Identidad duplicada en {table} ({keys})")
            allowed = {
                "concretos_specimens": {"planned", "tested", "cancelled"},
                "prefabricados_sample_sets": {"PLANNED", "IN_PROGRESS", "READY", "TESTED"},
                "prefabricados_workflow_tasks": {"PENDING", "DONE"},
            }
            for table, values in allowed.items():
                if table in counts:
                    actual = {
                        row[0] for row in db.execute(f'SELECT DISTINCT status FROM "{table}"')
                    }
                    if actual - values:
                        errors.append(f"Estados inválidos en {table}: {actual - values}")
            if "concretos_specimens" in counts:
                for row in db.execute("""SELECT s.id FROM concretos_specimens s
                    LEFT JOIN concretos_compression_results c ON c.specimen_id=s.id
                    LEFT JOIN concretos_flexural_results f ON f.specimen_id=s.id
                    WHERE s.status='tested' AND c.id IS NULL AND f.id IS NULL"""):
                    errors.append(f"Probeta ensayada sin resultado: {row[0]}")
            checks = [
                (
                    "Material sin identidad canónica",
                    """SELECT m.id FROM concretos_materials m
                    LEFT JOIN material_objects o ON o.id=m.canonical_id WHERE o.id IS NULL""",
                ),
                (
                    "Probeta programada antes de producir",
                    """SELECT s.id FROM concretos_specimens s
                    JOIN concretos_productions p ON p.id=s.production_id
                    WHERE julianday(s.planned_test_at)<julianday(p.produced_at)""",
                ),
                (
                    "Muestra/resultados Prefabricados incoherentes",
                    """SELECT s.id FROM prefabricados_sample_sets s
                    LEFT JOIN prefabricados_test_results r ON r.sample_set_id=s.id
                    WHERE (s.status='TESTED' AND r.id IS NULL) OR (r.id IS NOT NULL AND s.status<>'TESTED')""",
                ),
                (
                    "Actividad anterior a producción",
                    """SELECT t.id FROM prefabricados_workflow_tasks t
                    JOIN prefabricados_sample_sets s ON s.id=t.sample_set_id
                    JOIN prefabricados_production_batches p ON p.id=s.batch_id
                    WHERE t.scheduled_date<p.production_date""",
                ),
                (
                    "Satisfacción PIE por resultado no válido",
                    """SELECT x.result_id FROM pie_result_satisfactions x
                    JOIN shared_results r ON r.id=x.result_id
                    WHERE r.status NOT IN ('VALID','APPROVED','ACCEPTED','FINAL')""",
                ),
                (
                    "Paso PIE fuera de duración",
                    """SELECT s.plan_id FROM pie_occurrence_status s
                    JOIN pie_plans p ON p.id=s.plan_id WHERE s.day_number<1 OR s.day_number>p.duration_days""",
                ),
                (
                    "Método incompatible con ensayo",
                    """SELECT r.id FROM shared_results r
                    JOIN assay_methods m ON m.id=r.method_id WHERE m.assay_id<>r.assay_id""",
                ),
            ]
            if not required - counts.keys():
                for message, query in checks:
                    for row in db.execute(query):
                        errors.append(f"{message}: {row[0]}")
            if "workspace_migrations" in counts:
                report["workspace_version"] = db.execute(
                    "SELECT max(version) FROM workspace_migrations"
                ).fetchone()[0]
            if "schema_migrations" in counts:
                report["core_version"] = db.execute(
                    "SELECT max(version) FROM schema_migrations"
                ).fetchone()[0]
                if report["core_version"] != 3:
                    errors.append("Versión de Core no compatible (se requiere v3).")
    except (sqlite3.Error, ValueError) as exc:
        errors.append(str(exc))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", nargs="?", type=Path)
    args = parser.parse_args()
    from civillab_suite.core.database import core_database_path

    report = diagnose(args.database or core_database_path())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
