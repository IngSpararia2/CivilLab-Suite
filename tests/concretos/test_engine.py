from __future__ import annotations

import pytest

from concrete_mix_designer.domain.aci_seed import suggest_initial_values
from concrete_mix_designer.domain.engine import MixCalculationEngine
from concrete_mix_designer.domain.models import (
    ConstraintMode,
    DosageMode,
    Material,
    MaterialCategory,
    MixComponent,
    MixDesign,
    MixParameters,
    RatioConstraint,
)


def material(name: str, category: MaterialCategory, sg: float, absorption=0.0, moisture=0.0):
    return Material(
        id=None,
        name=name,
        category=category,
        specific_gravity=sg,
        absorption_pct=absorption,
        moisture_pct=moisture,
    )


def build_design() -> MixDesign:
    water = MixComponent(material("Agua", MaterialCategory.WATER, 1.0), 180.0, locked=True)
    cement = MixComponent(material("Cemento", MaterialCategory.CEMENTITIOUS, 3.15), 288.0)
    fly_ash = MixComponent(material("Ceniza", MaterialCategory.CEMENTITIOUS, 2.2), 72.0)
    sand = MixComponent(material("Arena", MaterialCategory.FINE_AGGREGATE, 2.6, 1.5, 4.0), 700.0)
    gravel = MixComponent(material("Grava", MaterialCategory.COARSE_AGGREGATE, 2.7, 0.8, 1.2), 1000.0)
    admixture = MixComponent(material("SP", MaterialCategory.ADMIXTURE, 1.08), 0.0)
    air = MixComponent(material("Aire", MaterialCategory.AIR, 1.0), 20.0, locked=True)
    return MixDesign(
        parameters=MixParameters(target_w_cm=0.50, w_cm_locked=True),
        components=[water, cement, fly_ash, sand, gravel, admixture, air],
        ratio_constraints=[
            RatioConstraint(
                numerator_uid=cement.uid,
                denominator_uid=fly_ash.uid,
                target_ratio=80.0,
                mode=ConstraintMode.PERCENT_OF_PAIR,
            ),
            RatioConstraint(
                numerator_uid=admixture.uid,
                denominator_uid=None,
                target_ratio=1.0,
                mode=ConstraintMode.PERCENT_OF_CEMENTITIOUS,
            ),
        ],
    )


def test_solver_closes_to_one_cubic_metre_and_enforces_ratio():
    design = build_design()
    engine = MixCalculationEngine()
    result = engine.recalculate(design)

    assert result.converged
    assert abs(design.total_absolute_volume_l - 1000.0) <= engine.TOLERANCE_L
    assert abs(design.actual_w_cm - 0.50) < 1e-9
    assert abs(design.total_cementitious_kg - 360.0) < 1e-6


def test_cementitious_pair_percentage_replaces_hidden_blend_parameter():
    design = build_design()
    engine = MixCalculationEngine()
    engine.recalculate(design)
    cement, fly_ash = design.by_category(MaterialCategory.CEMENTITIOUS)

    assert abs(cement.quantity / (cement.quantity + fly_ash.quantity) - 0.80) < 1e-9


def test_changing_water_cascades_to_cementitious_and_aggregates():
    design = build_design()
    engine = MixCalculationEngine()
    engine.recalculate(design)

    water = design.by_category(MaterialCategory.WATER)[0]
    water.quantity = 160.0
    result = engine.recalculate(design, changed_uid=water.uid)

    assert result.converged
    assert abs(design.total_cementitious_kg - 320.0) < 1e-6
    assert abs(design.actual_w_cm - 0.50) < 1e-9
    assert abs(design.total_absolute_volume_l - 1000.0) <= engine.TOLERANCE_L


def test_volume_closure_accounts_for_locked_water_in_partially_adjustable_pool():
    locked_water = MixComponent(
        material("Agua fija", MaterialCategory.WATER, 1.0), 50.0, locked=True
    )
    free_water = MixComponent(material("Agua libre", MaterialCategory.WATER, 1.0), 50.0)
    cement = MixComponent(material("Cemento", MaterialCategory.CEMENTITIOUS, 3.15), 200.0)
    design = MixDesign(
        parameters=MixParameters(target_w_cm=0.50, w_cm_locked=True),
        components=[locked_water, free_water, cement],
    )

    engine = MixCalculationEngine()
    result = engine.recalculate(design)

    assert result.converged
    assert design.total_absolute_volume_l == pytest.approx(1000.0, abs=engine.TOLERANCE_L)
    assert design.actual_w_cm == pytest.approx(0.50)
    assert locked_water.quantity == pytest.approx(50.0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_calculation_inputs_are_rejected(value):
    design = build_design()
    design.parameters.target_volume_l = value

    with pytest.raises(ValueError, match="número finito"):
        MixCalculationEngine().recalculate(design)


def test_constraint_with_inactive_component_is_ignored():
    design = build_design()
    constraint = design.ratio_constraints[0]
    numerator = design.component(constraint.numerator_uid)
    assert numerator is not None
    numerator.enabled = False
    original_quantity = numerator.quantity

    result = MixCalculationEngine().recalculate(design)

    assert numerator.quantity == pytest.approx(original_quantity)
    assert any("componente inactivo" in warning for warning in result.warnings)


def test_design_deserialization_rejects_non_finite_values():
    payload = build_design().to_dict()
    payload["components"][0]["quantity"] = float("nan")

    with pytest.raises(ValueError, match="número finito"):
        MixDesign.from_dict(payload)


def test_changing_sand_keeps_custom_sand_gravel_ratio_after_closure():
    design = build_design()
    engine = MixCalculationEngine()
    sand = design.by_category(MaterialCategory.FINE_AGGREGATE)[0]
    gravel = design.by_category(MaterialCategory.COARSE_AGGREGATE)[0]
    design.ratio_constraints.append(
        RatioConstraint(
            numerator_uid=sand.uid,
            denominator_uid=gravel.uid,
            target_ratio=0.60,
            mode=ConstraintMode.MASS_RATIO,
        )
    )
    engine.recalculate(design)
    sand.quantity += 100.0
    result = engine.recalculate(design, changed_uid=sand.uid)

    assert result.converged
    assert abs(sand.quantity / gravel.quantity - 0.60) < 1e-6
    assert abs(design.total_absolute_volume_l - 1000.0) <= engine.TOLERANCE_L


def test_admixture_percent_of_total_cementitious():
    design = build_design()
    engine = MixCalculationEngine()
    engine.recalculate(design)
    admixture = design.by_category(MaterialCategory.ADMIXTURE)[0]

    assert abs(admixture.quantity - 3.6) < 1e-6


def test_admixture_ml_per_100kg_total_cementitious():
    design = build_design()
    admixture = design.by_category(MaterialCategory.ADMIXTURE)[0]
    design.ratio_constraints[-1] = RatioConstraint(
        numerator_uid=admixture.uid,
        denominator_uid=None,
        target_ratio=120.0,
        mode=ConstraintMode.ML_PER_100KG_CEMENTITIOUS,
    )
    engine = MixCalculationEngine()
    engine.recalculate(design)

    expected_l = 120.0 * design.total_cementitious_kg / 100.0 / 1000.0
    assert abs(admixture.quantity - expected_l * admixture.material.density_kg_l) < 1e-6


def test_percent_of_b_constraint():
    design = build_design()
    sand = design.by_category(MaterialCategory.FINE_AGGREGATE)[0]
    gravel = design.by_category(MaterialCategory.COARSE_AGGREGATE)[0]
    design.ratio_constraints.append(
        RatioConstraint(
            numerator_uid=sand.uid,
            denominator_uid=gravel.uid,
            target_ratio=60.0,
            mode=ConstraintMode.PERCENT_OF_B,
        )
    )
    engine = MixCalculationEngine()
    engine.recalculate(design)

    assert abs(sand.quantity / gravel.quantity - 0.60) < 1e-6


def test_ml_per_100kg_of_selected_component():
    design = build_design()
    admixture = design.by_category(MaterialCategory.ADMIXTURE)[0]
    cement = design.by_category(MaterialCategory.CEMENTITIOUS)[0]
    design.ratio_constraints[-1] = RatioConstraint(
        numerator_uid=admixture.uid,
        denominator_uid=cement.uid,
        target_ratio=150.0,
        mode=ConstraintMode.ML_PER_100KG_B,
    )
    engine = MixCalculationEngine()
    engine.recalculate(design)

    actual = engine.constraint_actual_value(design, design.ratio_constraints[-1])
    assert abs(actual - 150.0) < 1e-6


def test_moisture_correction_reduces_batch_water_for_wet_aggregates():
    design = build_design()
    engine = MixCalculationEngine()
    engine.recalculate(design)
    rows = engine.moisture_correction(design)

    water_row = next(row for row in rows if row["name"] == "Agua")
    assert float(water_row["corrected_quantity"]) < float(water_row["design_quantity"])


def test_moisture_correction_reports_uncompensated_excess_free_water():
    water = MixComponent(material("Agua", MaterialCategory.WATER, 1.0), 100.0)
    saturated_sand = MixComponent(
        material(
            "Arena saturada",
            MaterialCategory.FINE_AGGREGATE,
            2.6,
            absorption=0.0,
            moisture=20.0,
        ),
        1000.0,
    )
    design = MixDesign(components=[water, saturated_sand])

    rows = MixCalculationEngine().moisture_correction(design)
    water_row = next(row for row in rows if row["uid"] == water.uid)

    assert float(water_row["corrected_quantity"]) == pytest.approx(0.0)
    assert float(water_row["water_contribution"]) == pytest.approx(-100.0)
    assert float(water_row["excess_free_water_kg"]) == pytest.approx(100.0)
    assert water_row["water_balance_warning"]
    assert float(water_row["corrected_quantity"]) == pytest.approx(
        float(water_row["design_quantity"]) + float(water_row["water_contribution"])
    )

    saturated_sand.material.moisture_pct = 0.0
    refreshed_rows = MixCalculationEngine().moisture_correction(design)
    assert all(not row["water_balance_warning"] for row in refreshed_rows)
    assert all(float(row["excess_free_water_kg"]) == 0.0 for row in refreshed_rows)


@pytest.mark.parametrize(
    ("absorption", "moisture", "message"),
    [(-1.0, 2.0, "absorción"), (1.0, -2.0, "humedad")],
)
def test_moisture_correction_rejects_negative_legacy_properties(
    absorption, moisture, message
):
    aggregate = MixComponent(
        material(
            "Agregado heredado",
            MaterialCategory.FINE_AGGREGATE,
            2.6,
            absorption=absorption,
            moisture=moisture,
        ),
        800.0,
    )

    with pytest.raises(ValueError, match=message):
        MixCalculationEngine().moisture_correction(MixDesign(components=[aggregate]))


def test_academic_suggestion_is_finite_and_plausible():
    suggestion = suggest_initial_values(28.0, 100.0, 19.0, False)
    assert 125.0 <= suggestion.water_kg_m3 <= 240.0
    assert 0.20 <= suggestion.w_cm <= 0.80
    assert suggestion.air_pct > 0.0


def test_material_repository_seeds_database(tmp_path):
    from concrete_mix_designer.data.database import MaterialRepository

    repository = MaterialRepository(tmp_path / "materials.sqlite3")
    materials = repository.list_all()
    names = {item.name for item in materials}
    assert "Agua" in names
    assert "Cemento Portland Tipo I" in names
    assert "Arena estándar" in names


def test_constraints_survive_json_roundtrip():
    design = build_design()
    restored = MixDesign.from_dict(design.to_dict())

    assert len(restored.ratio_constraints) == 2
    assert restored.ratio_constraints[0].mode == ConstraintMode.PERCENT_OF_PAIR
    assert restored.ratio_constraints[1].target_ratio == 1.0


def test_relation_controlled_uids_are_derived_only_from_active_numerators():
    design = build_design()
    first, second = design.ratio_constraints
    second.enabled = False

    assert design.relation_controlled_uids == {first.numerator_uid}
    assert first.denominator_uid not in design.relation_controlled_uids

    first.enabled = False
    assert design.relation_controlled_uids == set()


def test_legacy_unused_batch_volume_is_ignored_when_loading_design_json():
    payload = build_design().to_dict()
    payload["parameters"]["batch_volume_m3"] = 6.5

    restored = MixDesign.from_dict(payload)

    assert "batch_volume_m3" not in restored.to_dict()["parameters"]


def test_legacy_hidden_parameters_are_migrated_to_visible_constraints():
    legacy_cement = MixComponent(
        material("Cemento", MaterialCategory.CEMENTITIOUS, 3.15), 288.0, blend_pct=80.0
    )
    legacy_ash = MixComponent(
        material("Ceniza", MaterialCategory.CEMENTITIOUS, 2.2), 72.0, blend_pct=20.0
    )
    legacy_sp_material = Material(
        id=None,
        name="SP",
        category=MaterialCategory.ADMIXTURE,
        specific_gravity=1.08,
        dosage_mode=DosageMode.PCT_CEMENTITIOUS,
        dosage_value=0.8,
    )
    legacy = MixDesign(components=[legacy_cement, legacy_ash, MixComponent(legacy_sp_material, 0.0)])
    payload = legacy.to_dict()
    payload["ratio_constraints"] = []
    payload.pop("format_version", None)  # Emulate the unversioned legacy JSON.
    restored = MixDesign.from_dict(payload)

    modes = {constraint.mode for constraint in restored.ratio_constraints}
    assert ConstraintMode.PERCENT_OF_PAIR in modes
    assert ConstraintMode.PERCENT_OF_CEMENTITIOUS in modes
