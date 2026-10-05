"""Generate a synthetic integral workspace through production repositories/services.

Usage: python -m civillab_suite.demo --output artifacts/demo --anchor 2026-10-04
Never targets the installed workspace and refuses to overwrite an existing DB.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from civillab_suite.core.catalog import CatalogService
from civillab_suite.core.database import CoreDatabase
from civillab_suite.core.pie import PieFrequency, PieService
from civillab_suite.core.results import SharedResultService
from civillab_suite.data_portability import DataLocations, DataPortabilityService
from civillab_suite.diagnostics import diagnose
from civillab_suite.storage import initialize_workspace
from concrete_mix_designer.data.database import MaterialRepository
from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
from concrete_mix_designer.domain.engine import MixCalculationEngine
from concrete_mix_designer.domain.laboratory_models import SpecimenStatus, SpecimenType
from concrete_mix_designer.domain.metadata_models import GradationPoint, MaterialCharacterization
from concrete_mix_designer.domain.models import (
    Material,
    MaterialCategory,
    MixComponent,
    MixDesign,
    MixParameters,
)
from concrete_mix_designer.domain.strength import required_strength


def locations_for(path: Path) -> DataLocations:
    return DataLocations(path.parent, path, path, path, path.parent / "preferences")


def generate(output: Path, anchor: date | None = None, seed: int = 2026) -> dict:
    anchor = anchor or date.today()
    output = Path(output).resolve()
    path = output / "core.sqlite3"
    if path.exists():
        raise ValueError("El directorio ya contiene una base; usa un directorio nuevo.")
    output.mkdir(parents=True, exist_ok=True)
    initialize_workspace(path)
    rng = random.Random(seed)
    materials = MaterialRepository(path, seed=False)
    lab = LaboratoryRepository(path)
    engine = MixCalculationEngine()
    definitions = [
        ("Agua de mezcla", "water", 1, 0),
        ("Cemento UG", "cementitious", 3.15, 0),
        ("Ceniza fuente sintética", "cementitious", 2.30, 0),
        ("Arena río A", "fine_aggregate", 2.62, 1.8),
        ("Arena triturada B", "fine_aggregate", 2.67, 2.4),
        ("Grava 3/4", "coarse_aggregate", 2.70, 0.9),
        ("Gravilla 3/8", "coarse_aggregate", 2.65, 1.2),
        ("Superplastificante PCE", "admixture", 1.08, 0),
        ("Aire", "air", 1, 0),
        ("Filler experimental", "other", 2.71, 0),
    ]
    saved_materials = []
    for index, (name, category, sg, absorption) in enumerate(definitions):
        material = Material(
            None,
            name,
            MaterialCategory(category),
            sg,
            absorption,
            code="AG-003" if index == 5 else f"DEMO-{index + 1:03}",
        )
        characterization = MaterialCharacterization(
            supplier="Proveedor sintético", source="Fuente de demostración"
        )
        if "aggregate" in category:
            characterization.specific_gravity_ssd = sg
            characterization.specific_gravity_dry = sg / (1 + absorption / 100)
            characterization.gradation = [
                GradationPoint(label, opening, passing, order)
                for order, (label, opening, passing) in enumerate(
                    [
                        ('3/4"', 19, 100),
                        ('3/8"', 9.5, 85),
                        ("N°4", 4.75, 65),
                        ("N°16", 1.18, 35),
                        ("N°50", 0.30, 12),
                        ("N°200", 0.075, 3),
                    ]
                )
            ]
            characterization.fineness_modulus = 2.7 if category == "fine_aggregate" else None
            characterization.compacted_unit_weight_kg_m3 = 1580
        materials.save_with_characterization(material, characterization)
        saved_materials.append(material)
    designs = []
    for index, (name, constituents, fc) in enumerate(
        [
            (
                "Concreto 28 · serie completa",
                [(0, 180), (1, 360), (3, 750), (5, 1050), (8, 20)],
                28,
            ),
            (
                "Concreto 35 · serie intermedia",
                [(0, 170), (1, 380), (4, 730), (6, 1080), (7, 3)],
                35,
            ),
            ("Concreto 21 · serie insuficiente", [(0, 190), (1, 330), (3, 800), (5, 1000)], 21),
            ("Mortero de reparación", [(0, 200), (1, 400), (3, 1200)], 28),
            ("Pasta cementicia", [(0, 200), (1, 400)], 28),
            ("Pasta con filler experimental", [(0, 220), (1, 380), (2, 50), (7, 3), (9, 90)], 28),
        ]
    ):
        mix = MixDesign(
            MixParameters(fc_mpa=fc, w_cm_locked=True),
            [MixComponent(saved_materials[m], q, uid=f"demo-{index}-{m}") for m, q in constituents],
        )
        basis = required_strength(fc, as_of=anchor)
        mix.parameters.fcr_mpa = basis["fcr_mpa"]
        mix.parameters.strength_basis_snapshot = basis
        if not engine.recalculate(mix).converged:
            raise RuntimeError(f"No se pudo cerrar {name}")
        designs.append(
            lab.create_design(
                name=name, design=mix, group_name="Producción" if index < 3 else "Investigación"
            )
        )
    lab.create_design(
        name="Concreto 28 · revisión conservada",
        design=lab.load_mix_design(designs[0].id),
        source_design_id=designs[0].id,
    )
    for index, record in enumerate(designs):
        count = [32, 18, 5, 4, 3, 3][index]
        for ordinal in range(count + 7):
            completed = ordinal < count
            test_day = (
                anchor - timedelta(days=3 * (count - ordinal))
                if completed
                else anchor + timedelta(days=ordinal - count - 1)
            )
            produced = datetime.combine(test_day - timedelta(days=28), time(8), timezone.utc)
            mix = lab.load_mix_design(record.id)
            moistures = {
                c.uid: round(rng.uniform(0, 6), 2)
                for c in mix.components
                if "aggregate" in c.category.value
            }
            production = lab.create_production(
                design_id=record.id,
                produced_at=produced,
                batch_code=f"C{index + 1}-{ordinal + 1:03}",
                batch_volume_m3=round(rng.uniform(0.15, 2), 3),
                batch_moistures=moistures,
                schedules=[
                    (SpecimenType.CYLINDER, 28, 3),
                    (SpecimenType.CYLINDER, 7, 3),
                    (SpecimenType.BEAM, 28, 2),
                ],
            )
            lab.add_fresh_test(
                production_id=production.id,
                test_type="slump" if index < 3 else "spread",
                measured_at=produced + timedelta(minutes=10),
                slump_mm=90 + ordinal % 5 * 10 if index < 3 else None,
                spread_d1_mm=230 if index >= 3 else None,
                spread_d2_mm=240 if index >= 3 else None,
                concrete_temperature_c=23 + ordinal % 6,
                air_content_pct=2 + ordinal % 3 * 0.5,
                unit_weight_kg_m3=2320,
            )
            for specimen in lab.list_specimens(production.id):
                if not completed:
                    if ordinal == count + 6:
                        lab.set_specimen_status(specimen.id, SpecimenStatus.CANCELLED)
                    continue
                tested = produced + timedelta(days=specimen.target_age_days)
                if specimen.specimen_type == SpecimenType.CYLINDER:
                    strength = round(mix.parameters.fc_mpa + 7 + rng.gauss(0, 3), 3)
                    if ordinal % 13 == 0:
                        strength -= 10  # Include low results in the unfiltered series.
                    if specimen.target_age_days == 7:
                        strength *= 0.72
                    lab.upsert_compression_result(
                        specimen_id=specimen.id,
                        tested_at=tested,
                        diameter_mm=100,
                        height_mm=200,
                        mass_kg=3.7,
                        max_load_kn=strength * 7.853981633974483,
                    )
                else:
                    lab.upsert_flexural_result(
                        specimen_id=specimen.id,
                        tested_at=tested,
                        width_mm=150,
                        depth_mm=150,
                        span_mm=450,
                        max_load_kn=32 + rng.uniform(-5, 5),
                        fracture_distance_mm=None,
                    )
    for record in designs[:2]:
        mix = lab.load_mix_design(record.id)
        basis = required_strength(
            mix.parameters.fc_mpa,
            tests=lab.strength_tests(record.id, 28),
            series_id=record.id,
            comparable=True,
            as_of=anchor,
        )
        mix.parameters.fcr_mpa = basis["fcr_mpa"]
        mix.parameters.strength_basis_snapshot = basis
        lab.create_design(
            name=record.name + " · base estadística", design=mix, source_design_id=record.id
        )
    _prefabricados(path, output, anchor, rng)
    _shared(path, saved_materials[5], anchor)
    _stable_demo_metadata(path, anchor, seed)
    report = diagnose(path)
    if report["errors"]:
        raise RuntimeError(report["errors"])
    package = DataPortabilityService(locations_for(path)).export_data(
        output / "CivilLab-Demo-Integral.civillab"
    )
    report.update(
        anchor=anchor.isoformat(),
        seed=seed,
        package=str(package),
        strength_series={
            record.name: len(lab.strength_tests(record.id, 28)) for record in designs[:3]
        },
    )
    (output / "diagnostics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def _stable_demo_metadata(path, anchor, seed):
    """Normalize only generated audit metadata after exercising real services.

    Operational rows, tests, quantities and states are created by the public
    services above. Stable timestamps/UUIDs make their DB snapshots reproducible.
    Export-package creation time intentionally records the actual export time.
    """
    from uuid import NAMESPACE_URL, uuid5

    from civillab_suite.sqlite_support import connect

    stamp = datetime.combine(anchor, time(8), timezone.utc).isoformat()

    def stable_json(value):
        if isinstance(value, dict):
            return {
                key: stamp if key == "calculated_at" else stable_json(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [stable_json(item) for item in value]
        return value

    with connect(path) as db:
        tables = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            columns = [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]
            for column in (
                "created_at",
                "updated_at",
                "applied_at",
                "matched_at",
                "completed_at",
                "deactivated_at",
                "imported_at",
            ):
                if column in columns:
                    db.execute(
                        f'UPDATE "{table}" SET "{column}"=? WHERE "{column}" IS NOT NULL', (stamp,)
                    )
            for column in (c for c in columns if "json" in c):
                for row in db.execute(
                    f'SELECT rowid,"{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
                ).fetchall():
                    if row[1]:
                        payload = json.dumps(
                            stable_json(json.loads(row[1])),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        db.execute(
                            f'UPDATE "{table}" SET "{column}"=? WHERE rowid=?', (payload, row[0])
                        )
        families = db.execute(
            "SELECT family_uid,min(id) FROM concretos_mix_designs GROUP BY family_uid"
        ).fetchall()
        for family, first in families:
            db.execute(
                "UPDATE concretos_mix_designs SET family_uid=? WHERE family_uid=?",
                (uuid5(NAMESPACE_URL, f"civillab-demo:{anchor}:{seed}:{first}").hex, family),
            )
        db.execute("UPDATE prefabricados_import_batches SET file_path='Resumen-Demo.xlsx'")


def _prefabricados(path, output, anchor, rng):
    import pandas as pd

    from precon_lab.database import dispose_database_connections, session_scope, use_database
    from precon_lab.importers import import_summary_file
    from precon_lab.models import ProductionBatch
    from precon_lab.services import (
        complete_task,
        create_product,
        create_production,
        reopen_task,
        reprogram_sample_set,
        save_provisional_result,
    )

    use_database(path)
    try:
        with session_scope() as session:
            products = [
                create_product(session, name, code, category)
                for name, code, category in (
                    ("Bloque estructural demo", "BE-12", "BLOCK"),
                    ("Bloque divisorio demo", "BD-10", "BLOCK"),
                    ("Adoquín flexotracción demo", "AF-20", "FLEXURE"),
                )
            ]
            for index in range(36):
                product = products[index % 3]
                day = anchor - timedelta(days=42 - index * 2)
                summary = create_production(
                    session,
                    product_id=product.id,
                    production_date=day,
                    lot_code=f"PF-{index + 1:03}",
                    ages=[7, 28],
                    quantity_produced=400 + index * 20,
                )
                batch = session.get(ProductionBatch, summary.batch_id)
                for sample in batch.sample_sets:
                    for task in sample.tasks:
                        if task.scheduled_date < anchor - timedelta(days=7):
                            complete_task(session, task.id, "Registro sintético")
                    if index == 20 and sample.tasks:
                        complete_task(session, sample.tasks[0].id)
                        reopen_task(session, sample.tasks[0].id)
                    target = sample.planned_test_date or day + timedelta(days=2)
                    if target < anchor - timedelta(days=7):
                        values = {
                            "ABSORPTION": {"absorption_avg": 6 + rng.random()},
                            "COMPRESSION": {"strength_avg": 12 + rng.random() * 5},
                            "FLEXURE": {"flexural_avg": 4 + rng.random() * 2},
                        }[sample.purpose]
                        save_provisional_result(
                            session, sample_set_id=sample.id, test_date=target, **values
                        )
                    elif index % 5 == 0 and sample.planned_test_date:
                        reprogram_sample_set(session, sample.id, target + timedelta(days=2))
            rows = []
            for index in range(6):
                tested = anchor - timedelta(days=100 + index * 7)
                rows.append(
                    {
                        "Nombre del Archivo": f"sintetico-{index}.xlsx",
                        "fecha de ensayo": tested,
                        "material": "Bloque estructural demo",
                        "Numero de Informe": f"DEMO-{index}",
                        "bloque 1 fecha de elaboracion": tested - timedelta(days=28),
                        "bloque 1 edad": 28,
                        "Bloque 1 Id. Muestra": f"H-{index}",
                        "Bloque 1 Material": "Bloque estructural demo",
                        "Bloque 1 f'c Neta": 14.5,
                        "f'c Promedio": 14.5,
                        "Estado de lectura": "OK",
                    }
                )
            source = output / "Resumen-Demo.xlsx"
            pd.DataFrame(rows).to_excel(source, sheet_name="Resumen", index=False)
            _stable_xlsx(source, anchor)
            import_summary_file(session, source)
    finally:
        dispose_database_connections()


def _stable_xlsx(path, anchor):
    """Reproducible synthetic importer fixture (including ZIP/core metadata)."""
    import re
    import zipfile

    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    if "docProps/core.xml" in entries:
        text = entries["docProps/core.xml"].decode("utf-8")
        text = re.sub(r"(?<=>)\d{4}-\d{2}-\d{2}T[^<]+", anchor.isoformat() + "T08:00:00Z", text)
        entries["docProps/core.xml"] = text.encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def _shared(path, material, anchor):
    core = CoreDatabase(path)
    catalog = CatalogService(core)
    pie = PieService(core)
    result_service = SharedResultService(core, pie)
    assay_id = core.link_assay_to_module("Granulometría demo", "concretos")
    core.link_assay_to_module("Granulometría demo", "prefabricados")
    shared = next(m for m in catalog.list_material_objects() if m.id == material.canonical_id)
    plans = []
    for frequency in PieFrequency:
        plan = pie.create_plan(
            assay_id=assay_id,
            module_ids=["concretos", "prefabricados"],
            responsible="Técnico demo",
            frequency=frequency,
            start_date=anchor - timedelta(days=35),
            interval=3 if frequency.value.startswith("custom") else 1,
            material_type_id=shared.material_type_id,
            material_object_id=shared.id,
        )
        plans.append(plan)
        occurrences = pie.list_occurrences(anchor - timedelta(days=7), anchor + timedelta(days=7))
        selected = next((o for o in occurrences if o.plan_id == plan.id), None)
        if selected:
            pie.set_occurrence_completed(plan.id, selected.occurrence_start, 1, True)
            if frequency == PieFrequency.DAILY:
                pie.reschedule_occurrence(plan.id, anchor, 1, anchor + timedelta(days=2))
    pie.deactivate_plan(plans[-1].id)
    for index, status in enumerate(("VALID", "PROVISIONAL", "REJECTED")):
        result = result_service.register(
            assay_id=assay_id,
            material_object_id=shared.id,
            tested_on=anchor,
            origin_module_id="concretos",
            source_type="demo_report",
            source_id=str(index),
            status=status,
            report_reference=f"DEMO-{index}",
        )
        result_service.satisfy_compatible_obligations(result.id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/demo"))
    parser.add_argument("--anchor", type=date.fromisoformat, default=date.today())
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    print(json.dumps(generate(args.output, args.anchor, args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
