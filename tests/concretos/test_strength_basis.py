import math
from datetime import date, datetime, timedelta, timezone

import pytest

from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
from concrete_mix_designer.domain.models import MixDesign
from concrete_mix_designer.domain.strength import (
    PSI_MPA,
    StrengthTest,
    modification_factor,
    required_strength,
)


@pytest.mark.parametrize("fc,expected", [(2000, 3000), (3000, 4200), (5000, 6200), (6000, 7300)])
def test_no_history_aci_table_in_psi_converted_to_mpa(fc, expected):
    assert required_strength(fc * PSI_MPA)["fcr_mpa"] == pytest.approx(expected * PSI_MPA)


@pytest.mark.parametrize(
    "n,k", [(15, 1.16), (18, 1.112), (20, 1.08), (25, 1.03), (29, 1.006), (30, 1), (50, 1)]
)
def test_factor_interpolation(n, k):
    assert modification_factor(n) == pytest.approx(k)


def series(n=30, age=28):
    # Alternating 26/30 MPa has a hand-verifiable sample variance 4*N/(N-1).
    return [
        StrengthTest(
            str(i),
            i,
            age,
            date(2026, 1, 1) + timedelta(days=i * 4),
            (i * 2, i * 2 + 1),
            26 + 4 * (i % 2),
        )
        for i in range(n)
    ]


@pytest.mark.parametrize("n", [1, 5, 14])
def test_insufficient_series_rejected(n):
    with pytest.raises(ValueError, match="15"):
        required_strength(
            28, tests=series(n), series_id=1, comparable=True, as_of=date(2026, 10, 4)
        )


@pytest.mark.parametrize("fc", [28, 42])
def test_statistical_equations_and_snapshot(fc):
    basis = required_strength(
        fc, tests=series(), series_id=7, comparable=True, as_of=date(2026, 10, 4)
    )
    expected_s = math.sqrt(120 / 29)
    assert basis["n"] == 30
    assert basis["mean_mpa"] == 28
    assert basis["s_mpa"] == pytest.approx(expected_s)
    second = (
        fc + 2.33 * expected_s - 3.4473786465841804 if fc == 28 else 0.9 * fc + 2.33 * expected_s
    )
    assert basis["fcr_mpa"] == pytest.approx(max(fc + 1.34 * expected_s, second))
    assert len(basis["tests"]) == 30
    mix = MixDesign()
    mix.parameters.fcr_mpa = basis["fcr_mpa"]
    mix.parameters.strength_basis_snapshot = basis
    restored = MixDesign.from_dict(mix.to_dict())
    assert restored.parameters.strength_basis_snapshot == basis


def test_large_variability_selects_second_equation():
    tests = [
        StrengthTest(
            str(i), i, 28, date(2026, 1, 1) + timedelta(days=3 * i), (i,), 20 + 20 * (i % 2)
        )
        for i in range(30)
    ]
    basis = required_strength(
        28, tests=tests, series_id=1, comparable=True, as_of=date(2026, 10, 4)
    )
    assert basis["fcr_mpa"] == pytest.approx(28 + 2.33 * math.sqrt(3000 / 29) - 500 * PSI_MPA)


@pytest.mark.parametrize("change", ["duplicate", "age", "period", "old", "unconfirmed"])
def test_series_validity(change):
    tests = series()
    comparable = True
    age = 28
    now = date(2026, 10, 4)
    if change == "duplicate":
        tests[-1] = tests[0]
    if change == "age":
        age = 7
    if change == "period":
        tests = [StrengthTest(str(i), i, 28, date(2026, 1, 1), (i,), 28) for i in range(30)]
    if change == "old":
        now = date(2029, 1, 1)
    if change == "unconfirmed":
        comparable = False
    with pytest.raises(ValueError):
        required_strength(
            28, tests=tests, series_id=1, age_days=age, comparable=comparable, as_of=now
        )


def test_strength_test_grouping_excludes_incomplete_cancelled_and_wrong_age(tmp_path):
    repo = LaboratoryRepository(tmp_path / "lab.sqlite3")
    saved = repo.create_design(name="Serie", design=MixDesign())
    produced = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index, (count, diameter, complete, actual_age) in enumerate(
        [(2, 150, 2, 28), (3, 100, 3, 28), (3, 100, 2, 28), (2, 100, 2, 28), (2, 150, 2, 7)]
    ):
        prod = repo.create_production(
            design_id=saved.id,
            produced_at=produced + timedelta(days=index * 3),
            batch_code=str(index),
            batch_volume_m3=1,
            schedules=[("cylinder", 28, count)],
        )
        for ordinal, spec in enumerate(repo.list_specimens(prod.id)[:complete]):
            repo.upsert_compression_result(
                specimen_id=spec.id,
                tested_at=prod.produced_at + timedelta(days=actual_age),
                diameter_mm=diameter,
                height_mm=diameter * 2,
                mass_kg=None,
                max_load_kn=100,
                strength_mpa=24 + ordinal * 4,
            )
    tests = repo.strength_tests(saved.id, 28)
    assert len(tests) == 2
    assert [t.strength_mpa for t in tests] == [26, 28]
    stats = repo.design_statistics(saved.id)[0]
    assert stats.result_count == 2
    assert stats.average_mpa == 27
    assert stats.standard_deviation_mpa == pytest.approx(math.sqrt(2))
    from concrete_mix_designer.domain.laboratory_models import SpecimenStatus

    repo.set_specimen_status(tests[0].specimen_ids[0], SpecimenStatus.CANCELLED)
    assert len(repo.strength_tests(saved.id, 28)) == 1
    assert repo.design_statistics(saved.id)[0].standard_deviation_mpa is None
    assert repo.strength_tests(saved.id, 7) == []
