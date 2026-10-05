import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import date, datetime, timezone

import pytest

from civillab_suite.core.database import CoreDatabase
from civillab_suite.data_portability import DataLocations, DataPortabilityService
from civillab_suite.demo import generate, locations_for
from civillab_suite.diagnostics import diagnose
from civillab_suite.storage import initialize_workspace, migrate_workspace, validate_sqlite
from concrete_mix_designer.data.database import MaterialRepository
from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
from concrete_mix_designer.domain.engine import MixCalculationEngine
from concrete_mix_designer.domain.metadata_models import GradationPoint, MaterialCharacterization
from concrete_mix_designer.domain.models import (
    Material,
    MaterialCategory,
    MixComponent,
    MixDesign,
    MixParameters,
)


def legacy_sources(root):
    root.mkdir(parents=True, exist_ok=True)
    core, concrete, prefab = [
        root / name for name in ("core.sqlite3", "materials.sqlite3", "precon_lab.db")
    ]
    CoreDatabase(core).initialize()
    with closing(sqlite3.connect(concrete)) as db:
        db.executescript("""CREATE TABLE materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,specific_gravity REAL NOT NULL,
            absorption_pct REAL NOT NULL DEFAULT 0,moisture_pct REAL NOT NULL DEFAULT 0,
            dosage_mode TEXT NOT NULL DEFAULT 'manual_kg',dosage_value REAL NOT NULL DEFAULT 0,
            is_seed INTEGER NOT NULL DEFAULT 0);
            INSERT INTO materials(id,name,category,specific_gravity,absorption_pct) VALUES(42,'Grava heredada','coarse_aggregate',2.7,1.2);
            UPDATE sqlite_sequence SET seq=99 WHERE name='materials';
        """)
    with closing(sqlite3.connect(prefab)) as db:
        db.executescript("""CREATE TABLE products (
            id INTEGER PRIMARY KEY, name VARCHAR(160) NOT NULL, code VARCHAR(60) NOT NULL,
            category VARCHAR(30) NOT NULL,active BOOLEAN NOT NULL,created_at DATETIME NOT NULL,
            UNIQUE(name,code));
            INSERT INTO products VALUES(27,'Bloque heredado','BL-27','BLOCK',1,'2026-01-01 00:00:00');""")
    return core, concrete, prefab


def test_legacy_migration_is_lossless_backed_up_and_idempotent(tmp_path):
    core, concrete, prefab = legacy_sources(tmp_path / "legacy")
    original_concrete = concrete.read_bytes()
    original_prefab = prefab.read_bytes()
    backup = migrate_workspace(core, concrete, prefab)
    assert backup and len(list(backup.glob("*.sqlite3"))) == 3
    assert concrete.read_bytes() == original_concrete
    assert prefab.read_bytes() == original_prefab
    repo = MaterialRepository(core, seed=False)
    assert repo.get(42).name == "Grava heredada"
    assert repo.get(42).canonical_id is not None
    new = repo.save(Material(None, "Agua nueva", MaterialCategory.WATER, 1))
    assert new.id == 100
    with closing(sqlite3.connect(core)) as db:
        assert (
            db.execute("SELECT name FROM prefabricados_products WHERE id=27").fetchone()[0]
            == "Bloque heredado"
        )
    before = validate_sqlite(core)
    assert migrate_workspace(core, concrete, prefab) is None
    assert validate_sqlite(core) == before
    assert diagnose(core)["errors"] == []


def test_interrupted_migration_keeps_originals_and_retry_succeeds(tmp_path, monkeypatch):
    import civillab_suite.storage as storage

    core, concrete, prefab = legacy_sources(tmp_path / "legacy")
    original = [path.read_bytes() for path in (core, concrete, prefab)]
    real = storage.initialize_workspace

    def fail(path):
        real(path)
        raise RuntimeError("interrupción simulada antes de publicar")

    monkeypatch.setattr(storage, "initialize_workspace", fail)
    with pytest.raises(RuntimeError, match="interrupción"):
        storage.migrate_workspace(core, concrete, prefab)
    assert [path.read_bytes() for path in (core, concrete, prefab)] == original
    assert list((core.parent / "backups").glob("migration-*"))
    monkeypatch.setattr(storage, "initialize_workspace", real)
    storage.migrate_workspace(core, concrete, prefab)
    assert diagnose(core)["errors"] == []


def test_import_v1_converts_before_replacing_unified_workspace(tmp_path):
    core, concrete, prefab = legacy_sources(tmp_path / "legacy")
    service = DataPortabilityService(
        DataLocations(core.parent, core, concrete, prefab, concrete.parent)
    )
    archive = service.export_data(tmp_path / "legacy.civillab")
    target = tmp_path / "new/core.sqlite3"
    initialize_workspace(target)
    new = DataPortabilityService(locations_for(target))
    result = new.import_data(archive)
    assert result.backup_path.is_file()
    assert diagnose(target)["errors"] == []
    assert MaterialRepository(target, seed=False).get(42).name == "Grava heredada"
    exported = new.export_data(tmp_path / "v2.civillab")
    with zipfile.ZipFile(exported) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["format_version"] == 2
        assert [c["name"] for c in manifest["components"]] == ["core"]


def test_material_atomic_crud_snapshots_and_safe_delete(tmp_path):
    path = tmp_path / "core.sqlite3"
    initialize_workspace(path)
    repo = MaterialRepository(path, seed=False)
    material = Material(None, "Arena", MaterialCategory.FINE_AGGREGATE, 2.6, 2, code="AG-003")
    invalid = MaterialCharacterization(gradation=[GradationPoint("N4", 4.75, 120)])
    with pytest.raises(ValueError):
        repo.save_with_characterization(material, invalid)
    assert repo.list_all() == []
    assert material.id is None
    with CoreDatabase(path).connect() as db:
        assert db.execute("SELECT count(*) FROM material_objects").fetchone()[0] == 0
    repo.save_with_characterization(material, MaterialCharacterization(specific_gravity_ssd=2.65))
    assert MaterialRepository(path, seed=False).get(material.id).specific_gravity == 2.65
    lab = LaboratoryRepository(path)
    design = MixDesign(MixParameters(w_cm_locked=False), [MixComponent(material, 102, uid="sand")])
    saved = lab.create_design(name="Experimental", design=design)
    production = lab.create_production(
        design_id=saved.id,
        produced_at=datetime.now(timezone.utc),
        batch_code="A",
        batch_volume_m3=1,
        batch_moistures={"sand": 5},
    )
    original = production.design_json_snapshot
    material.name = "Arena editada"
    material.moisture_pct = 12
    repo.save(material)
    assert lab.get_production(production.id).design_json_snapshot == original
    assert lab.load_mix_design(saved.id).components[0].material.name == "Arena"
    assert json.loads(original)["batch_moistures"] == {"sand": 5}
    with pytest.raises(ValueError, match="referenciad"):
        repo.delete(material.id)
    disposable = repo.save(Material(None, "Material descartable", MaterialCategory.OTHER, 2))
    repo.delete(disposable.id)
    assert repo.get(disposable.id) is None


@pytest.mark.parametrize(
    "moisture,wet,free", [(5, 105, 3), (2, 102, 0), (1, 101, -1), (0, 100, -2)]
)
def test_batch_moisture_on_od_base_overrides_legacy(moisture, wet, free):
    sand = Material(None, "Arena", MaterialCategory.FINE_AGGREGATE, 2.65, 2, 99)
    water = Material(None, "Agua", MaterialCategory.WATER, 1)
    mix = MixDesign(
        components=[MixComponent(sand, 102, uid="sand"), MixComponent(water, 20, uid="water")],
        batch_moistures={"sand": moisture},
    )
    rows = {r["uid"]: r for r in MixCalculationEngine().moisture_correction(mix)}
    assert rows["sand"]["corrected_quantity"] == pytest.approx(wet)
    assert rows["sand"]["water_contribution"] == pytest.approx(free)
    assert rows["water"]["corrected_quantity"] == pytest.approx(20 - free)
    assert wet + (20 - free) == pytest.approx(122)


@pytest.fixture(scope="module")
def demo_workspace(tmp_path_factory):
    output = tmp_path_factory.mktemp("integral-demo")
    report = generate(output, date(2026, 10, 4), 2026)
    return output, report


def test_demo_e2e_new_environment_restore_and_calendar(demo_workspace, tmp_path):
    output, report = demo_workspace
    assert list(report["strength_series"].values()) == [32, 18, 5]
    source = output / "core.sqlite3"
    target = tmp_path / "restored/core.sqlite3"
    initialize_workspace(target)
    service = DataPortabilityService(locations_for(target))
    service.import_data(output / "CivilLab-Demo-Integral.civillab")
    assert validate_sqlite(source) == validate_sqlite(target)
    before = target.read_bytes()
    backup = service.new_environment()
    blank = diagnose(target)
    assert blank["errors"] == []
    for table in (
        "concretos_materials",
        "concretos_mix_designs",
        "prefabricados_products",
        "pie_plans",
    ):
        assert blank["counts"][table] == 0
    service.import_data(backup)
    assert target.read_bytes() == before
    assert diagnose(target)["errors"] == []
    from civillab_suite.app import bootstrap_shared_data
    from civillab_suite.context import build_suite_context
    from civillab_suite.registry import create_default_registry

    registry = create_default_registry()
    core = CoreDatabase(target)
    bootstrap_shared_data(registry, core)
    context = build_suite_context(core, registry, lambda target: None)
    activities = context.scheduling.activities_between(date(2026, 10, 3), date(2026, 10, 12))
    assert activities
    assert {"concretos", "prefabricados"}.issubset({a.module_id for a in activities})
    from precon_lab.database import dispose_database_connections

    dispose_database_connections()


def test_demo_qt_modules_and_critical_wiring(demo_workspace, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from civillab_suite.app import bootstrap_shared_data, create_application
    from civillab_suite.context import build_suite_context
    from civillab_suite.modules.concretos.adapter import create_window as concrete_window
    from civillab_suite.modules.prefabricados.adapter import create_window as prefab_window
    from civillab_suite.registry import create_default_registry

    app = create_application([])
    output, _ = demo_workspace
    core = CoreDatabase(output / "core.sqlite3")
    registry = create_default_registry()
    bootstrap_shared_data(registry, core)
    context = build_suite_context(core, registry, lambda target: None)
    windows = [concrete_window(suite_context=context), prefab_window(suite_context=context)]
    from concrete_mix_designer.ui.pages.dashboard_page import DashboardPage
    from concrete_mix_designer.ui.pages.results_page import ResultsPage

    dashboard = windows[0].findChild(DashboardPage)
    dashboard.strength_mode.setCurrentIndex(1)
    dashboard.strength_series.setCurrentIndex(dashboard.strength_series.findData(1))
    dashboard.comparable.setChecked(True)
    dashboard._calculate_suggestion()
    assert dashboard.apply_button.isEnabled()
    assert "N=32" in dashboard.strength_summary.text()
    dosage = windows[0].findChild(ResultsPage)
    dosage.design_combo.setCurrentIndex(dosage.design_combo.findData(1))
    assert dosage.moistures.inputs
    control = next(iter(dosage.moistures.inputs.values()))
    control.setValue(7.25)
    assert 7.25 in dosage._selected_design.batch_moistures.values()
    for window in windows:
        window.close()
    app.processEvents()
    from precon_lab.database import dispose_database_connections

    dispose_database_connections()


def test_diagnostics_rejects_corrupt_json_and_wrong_states(tmp_path):
    path = tmp_path / "core.sqlite3"
    initialize_workspace(path)
    repo = LaboratoryRepository(path)
    saved = repo.create_design(name="Audit", design=MixDesign())
    with closing(sqlite3.connect(path)) as db:
        db.execute(
            "UPDATE concretos_mix_designs SET design_json=? WHERE id=?", ("{broken", saved.id)
        )
        db.commit()
    assert any("design_json" in error for error in diagnose(path)["errors"])
