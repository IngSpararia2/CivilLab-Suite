from __future__ import annotations

from math import inf

import pytest

from concrete_mix_designer.domain.mix_normalization import (
    PercentageEntry,
    RecipeEntry,
    absolute_volume_l,
    normalize_observed_recipe,
    quantities_from_mass_percentages,
)


def test_inverse_normalization_closes_one_cubic_metre():
    entries = [
        RecipeEntry("water", 3.85, 1.0),
        RecipeEntry("cement", 4.50, 3.15),
        RecipeEntry("sand", 9.0, 2.65),
    ]

    result = normalize_observed_recipe(entries)

    assert result.observed_volume_l == pytest.approx(3.85 + 4.50 / 3.15 + 9.0 / 2.65)
    assert sum(
        absolute_volume_l(result.quantities[row.key], row.specific_gravity)
        for row in entries
    ) == pytest.approx(1000.0)


def test_mass_percentages_preserve_mass_ratios_and_close_volume():
    entries = [
        PercentageEntry("water", 10.0, 1.0),
        PercentageEntry("cement", 20.0, 3.15),
        PercentageEntry("sand", 70.0, 2.65),
    ]

    quantities = quantities_from_mass_percentages(entries)
    total_mass = sum(quantities.values())

    assert quantities["water"] / total_mass == pytest.approx(0.10)
    assert quantities["cement"] / total_mass == pytest.approx(0.20)
    assert sum(
        absolute_volume_l(quantities[row.key], row.specific_gravity) for row in entries
    ) == pytest.approx(1000.0)


def test_air_is_excluded_from_mass_percentages_but_reserves_volume():
    entries = [
        PercentageEntry("water", 20.0, 1.0),
        PercentageEntry("cement", 30.0, 3.0),
        PercentageEntry("sand", 50.0, 2.5),
    ]

    quantities = quantities_from_mass_percentages(entries, air_volume_l=20.0)

    mass_volume = sum(
        absolute_volume_l(quantities[row.key], row.specific_gravity) for row in entries
    )
    assert mass_volume == pytest.approx(980.0)
    assert mass_volume + 20.0 == pytest.approx(1000.0)


@pytest.mark.parametrize(
    "call",
    [
        lambda: quantities_from_mass_percentages(
            [PercentageEntry("a", 40.0, 1.0), PercentageEntry("b", 20.0, 2.0)]
        ),
        lambda: quantities_from_mass_percentages([PercentageEntry("a", 100.0, 0.0)]),
        lambda: quantities_from_mass_percentages(
            [PercentageEntry("a", 100.0, 1.0)], air_volume_l=1000.0
        ),
        lambda: quantities_from_mass_percentages([PercentageEntry("a", inf, 1.0)]),
        lambda: normalize_observed_recipe([RecipeEntry("a", 0.0, 1.0)]),
        lambda: normalize_observed_recipe(
            [RecipeEntry("a", 1.0, 1.0), RecipeEntry("a", 2.0, 2.0)]
        ),
    ],
)
def test_normalization_validation(call):
    with pytest.raises(ValueError):
        call()
