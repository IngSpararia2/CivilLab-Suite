from datetime import date

import pytest
from sqlalchemy import func, select

from precon_lab.inspection_catalog import seed_inspection_catalog
from precon_lab.models import InspectionPlanEntry, LaboratoryTest, MaterialType
from precon_lab.models import TestApplicability as ApplicabilityModel
from precon_lab.services import (
    ValidationError,
    create_inspection_plan_entry,
    format_periodicity,
    get_test_requirements,
    list_applicable_tests,
    list_inspection_catalog,
    list_material_types,
)


def _material(session, code):
    return session.scalar(select(MaterialType).where(MaterialType.code == code))


def _test(session, code):
    return session.scalar(select(LaboratoryTest).where(LaboratoryTest.code == code))


def _requirements(session, material_code, test_code):
    return get_test_requirements(session, _material(session, material_code).id, _test(session, test_code).id)


def test_catalog_is_idempotent_and_has_one_visible_paver(session):
    seed_inspection_catalog(session)
    session.commit()
    seed_inspection_catalog(session)
    session.commit()

    visible = list_material_types(session)
    assert len(visible) == 11
    assert [item.code for item in visible].count("PAVER_CONCRETE") == 1
    assert not {"PAVER_PAVEMENT", "PAVER_FLOOR"} & {item.code for item in visible}
    assert session.scalar(select(func.count()).select_from(ApplicabilityModel)) == len(set(session.execute(select(ApplicabilityModel.material_type_id, ApplicabilityModel.laboratory_test_id)).all()))


def test_legacy_pavers_and_plan_entries_migrate_without_loss(session):
    seed_inspection_catalog(session)
    legacy_pavement = MaterialType(code="PAVER_PAVEMENT", name="Adoquines para pavimentos")
    legacy_floor = MaterialType(code="PAVER_FLOOR", name="Adoquines para pisos")
    session.add_all((legacy_pavement, legacy_floor))
    session.flush()
    flexure = _test(session, "FLEXURAL_MODULUS")
    for legacy in (legacy_pavement, legacy_floor):
        session.add(InspectionPlanEntry(
            material_type=legacy,
            laboratory_test=flexure,
            responsible="Laboratorista",
            frequency_type="WEEKLY",
            weekday=0,
        ))
    session.commit()

    seed_inspection_catalog(session)
    session.commit()

    entries = list(session.scalars(select(InspectionPlanEntry)))
    assert len(entries) == 2
    assert {entry.material_type.code for entry in entries} == {"PAVER_CONCRETE"}
    assert not _material(session, "PAVER_PAVEMENT").active
    assert not _material(session, "PAVER_FLOOR").active
    codes = {item.laboratory_test.code for item in list_applicable_tests(session, _material(session, "PAVER_CONCRETE").id)}
    assert {"FLEXURAL_MODULUS", "ABSORPTION", "PAVER_ABRASION_NTC_5147", "PAVER_DIMENSIONS_NTC_2017"} <= codes
    assert "COMPRESSION_DOCUMENTARY" not in codes


def test_paver_flexure_keeps_both_ntc_2017_branches(session):
    seed_inspection_catalog(session)
    flexure = _requirements(session, "PAVER_CONCRETE", "FLEXURAL_MODULUS")
    absorption = _requirements(session, "PAVER_CONCRETE", "ABSORPTION")
    abrasion = _requirements(session, "PAVER_CONCRETE", "PAVER_ABRASION_NTC_5147")

    assert {(item.minimum, item.aggregation, item.condition) for item in flexure} == {
        (4.2, "Promedio de 5 adoquines", "Cumple desgaste: longitud promedio de huella de abrasión ≤ 23 mm"),
        (3.8, "Individual", "Cumple desgaste: longitud promedio de huella de abrasión ≤ 23 mm"),
        (5.0, "Promedio de 5 adoquines", "Alternativa sin aplicar el criterio de desgaste asociado"),
        (4.2, "Individual", "Alternativa sin aplicar el criterio de desgaste asociado"),
    }
    assert {(item.maximum, item.aggregation) for item in absorption} == {(7.0, "Promedio de 5 especímenes"), (8.0, "Individual")}
    assert abrasion[0].maximum == 23
    assert "4.2 / 3.8" in abrasion[0].condition
    assert abrasion[0].laboratory_test.standard.code == "NTC-5147"
    slab = _material(session, "SLAB_FLOOR")
    assert {item.standard.code for item in list_applicable_tests(session, slab.id)} == {"NTC-4992"}


def test_masonry_blocks_use_ntc_4024_methods_and_density_conditions(session):
    seed_inspection_catalog(session)
    structural = _material(session, "BLOCK_STRUCTURAL")
    nonstructural = _material(session, "BLOCK_NON_STRUCTURAL")
    for material, specification in ((structural, "NTC-4026"), (nonstructural, "NTC-4076")):
        applicable = list_applicable_tests(session, material.id)
        assert {item.laboratory_test.code for item in applicable} == {
            "MASONRY_COMPRESSION_NTC_4024", "MASONRY_ABSORPTION_NTC_4024"
        }
        assert all(item.standard.code == specification for item in applicable)
        assert all(item.laboratory_test.standard.code == "NTC-4024" for item in applicable)

    structural_compression = _requirements(session, "BLOCK_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024")
    assert {(item.minimum, item.aggregation) for item in structural_compression} == {
        (13.0, "Promedio de 3 unidades"), (11.0, "Individual"),
        (8.0, "Promedio de 3 unidades"), (7.0, "Individual"),
    }
    structural_absorption = _requirements(session, "BLOCK_STRUCTURAL", "MASONRY_ABSORPTION_NTC_4024")
    assert {(item.maximum, item.condition) for item in structural_absorption if "Clase Alta" in item.condition} == {
        (15.0, "Clase Alta; Peso liviano; densidad < 1680 kg/m³"),
        (12.0, "Clase Alta; Peso mediano; densidad 1680 a < 2000 kg/m³"),
        (9.0, "Clase Alta; Peso normal; densidad ≥ 2000 kg/m³"),
    }
    nonstructural_compression = _requirements(session, "BLOCK_NON_STRUCTURAL", "MASONRY_COMPRESSION_NTC_4024")
    assert {(item.minimum, item.aggregation) for item in nonstructural_compression} == {
        (6.0, "Promedio de 3 unidades"), (5.0, "Individual")
    }
    nonstructural_absorption = _requirements(session, "BLOCK_NON_STRUCTURAL", "MASONRY_ABSORPTION_NTC_4024")
    assert {item.maximum for item in nonstructural_absorption} == {18.0, 15.0, 12.0}


def test_legacy_block_plan_migrates_to_ntc_4024_without_losing_schedule(session):
    seed_inspection_catalog(session)
    block = _material(session, "BLOCK_STRUCTURAL")
    legacy_test = _test(session, "COMPRESSION_DOCUMENTARY")
    entry = InspectionPlanEntry(
        material_type=block,
        laboratory_test=legacy_test,
        responsible="Laboratorista",
        frequency_type="EVERY_X_MONTHS",
        weekday=2,
        week_ordinal=3,
        month_interval=4,
        reference_date=date(2026, 1, 1),
        observations="Conservar programación",
    )
    session.add(entry)
    session.commit()

    seed_inspection_catalog(session)
    session.commit()

    migrated = session.scalar(select(InspectionPlanEntry))
    assert migrated.laboratory_test.code == "MASONRY_COMPRESSION_NTC_4024"
    assert (migrated.responsible, migrated.month_interval, migrated.observations) == (
        "Laboratorista", 4, "Conservar programación"
    )
    seed_inspection_catalog(session)
    session.commit()
    assert session.scalar(select(func.count()).select_from(InspectionPlanEntry)) == 1


def test_base_and_subbase_cover_required_tests_and_methods(session):
    seed_inspection_catalog(session)
    expected_base = {"GRADATION", "LOS_ANGELES", "MICRO_DEVAL", "TEN_PERCENT_FINES", "SULFATE_SOUNDNESS", "LIQUID_LIMIT", "PLASTICITY_INDEX", "SAND_EQUIVALENT", "METHYLENE_BLUE", "CLAY_LUMPS_INV", "FLAKINESS_ELONGATION", "FRACTURED_FACES", "FINE_ANGULARITY", "MODIFIED_COMPACTION", "CBR"}
    expected_subbase = {"GRADATION", "LOS_ANGELES", "MICRO_DEVAL", "SULFATE_SOUNDNESS", "LIQUID_LIMIT", "PLASTICITY_INDEX", "SAND_EQUIVALENT", "CLAY_LUMPS_INV", "MODIFIED_COMPACTION", "CBR"}
    for material, expected in (("GRANULAR_BASE", expected_base), ("GRANULAR_SUBBASE", expected_subbase)):
        applicable = list_applicable_tests(session, _material(session, material).id)
        assert expected <= {item.laboratory_test.code for item in applicable}
        assert next(item for item in applicable if item.laboratory_test.code == "GRADATION").laboratory_test.standard.code == "INV-E-213"


@pytest.mark.parametrize(
    ("grading", "sieve", "minimum", "maximum"),
    (("BG-40", '37.5 mm / 1½"', 100, 100), ("BG-27", '9.5 mm / 3/8"', 52, 78), ("BG-38", "0.075 mm / No.200", 5, 15), ("BG-25", "4.75 mm / No.4", 35, 65), ("SBG-50", "0.075 mm / No.200", 2, 15), ("SBG-38", "25.0 mm / 1\"", 75, 95)),
)
def test_grading_bands_are_stored_per_sieve(session, grading, sieve, minimum, maximum):
    seed_inspection_catalog(session)
    material = "GRANULAR_SUBBASE" if grading.startswith("SBG") else "GRANULAR_BASE"
    requirement = next(item for item in _requirements(session, material, "GRADATION") if item.grading == grading and item.condition == f"Tamiz {sieve}")
    assert (requirement.minimum, requirement.maximum) == (minimum, maximum)


def test_ntc174_is_explicit_and_pending_without_a_licensed_copy(session):
    seed_inspection_catalog(session)
    for material in ("FINE_AGGREGATE", "COARSE_AGGREGATE"):
        applicable = list_applicable_tests(session, _material(session, material).id)
        assert all(item.standard.code == "NTC-174" for item in applicable)
        assert any(item.laboratory_test.code == "AGGREGATE_GRADATION_NTC_77" for item in applicable)
    requirement = _requirements(session, "FINE_AGGREGATE", "AGGREGATE_GRADATION_NTC_77")[0]
    assert requirement.verification_status == "PENDING_VERIFICATION"


def test_catalog_service_does_not_depend_on_plan_entries(session):
    seed_inspection_catalog(session)
    assert session.scalar(select(func.count()).select_from(InspectionPlanEntry)) == 0
    rows = list_inspection_catalog(session)
    assert rows
    requirement = next(
        requirement
        for app, requirement in rows
        if app.material_type.code == "GRANULAR_BASE" and requirement and requirement.grading == "BG-40"
    )
    assert requirement.source_detail
    assert requirement.verification_status


def test_active_catalog_entries_have_operational_procedures_and_test_summaries(session):
    seed_inspection_catalog(session)
    active_tests = list(session.scalars(select(LaboratoryTest).where(LaboratoryTest.active.is_(True))))
    active_applicabilities = list(
        session.scalars(
            select(ApplicabilityModel)
            .join(ApplicabilityModel.laboratory_test)
            .where(LaboratoryTest.active.is_(True))
        )
    )

    assert active_tests
    assert active_applicabilities
    assert all(item.equipment.strip() and item.procedure_summary.strip() for item in active_tests)
    assert all(
        item.procedure_detail.strip()
        and "Preparación previa" in item.procedure_detail
        and "Cálculo y registro final" in item.procedure_detail
        for item in active_applicabilities
    )


def test_create_plan_entry_validates_duplicate_and_formats_periodicity(session):
    seed_inspection_catalog(session)
    paver = _material(session, "PAVER_CONCRETE")
    flexure = _test(session, "FLEXURAL_MODULUS")
    create_inspection_plan_entry(session, material_type_id=paver.id, laboratory_test_id=flexure.id, responsible="Laboratorista", frequency_type="EVERY_X_MONTHS", weekday=0, week_ordinal=1, month_interval=3, reference_date=date(2026, 1, 1))
    assert format_periodicity("MONTHLY", weekday=2, week_ordinal=2) == "Segundo miércoles de cada mes"
    with pytest.raises(ValidationError, match="idéntica"):
        create_inspection_plan_entry(session, material_type_id=paver.id, laboratory_test_id=flexure.id, responsible="Laboratorista", frequency_type="EVERY_X_MONTHS", weekday=0, week_ordinal=1, month_interval=3, reference_date=date(2026, 1, 1))
