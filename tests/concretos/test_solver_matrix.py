import math

import pytest

from concrete_mix_designer.domain.engine import MixCalculationEngine
from concrete_mix_designer.domain.models import (
    ConstraintMode,
    Material,
    MaterialCategory,
    MixComponent,
    MixDesign,
    MixParameters,
    RatioConstraint,
)


def mixture(categories, ratio_locked):
    density = {
        "water": 1,
        "cementitious": 3.15,
        "fine_aggregate": 2.6,
        "coarse_aggregate": 2.7,
        "other": 2.2,
        "air": 1,
        "admixture": 1.08,
    }
    quantity = {
        "water": 180,
        "cementitious": 360,
        "fine_aggregate": 800,
        "coarse_aggregate": 1000,
        "other": 30,
        "air": 20,
        "admixture": 3,
    }
    return MixDesign(
        MixParameters(w_cm_locked=ratio_locked),
        [
            MixComponent(
                Material(None, f"{category}-{i}", MaterialCategory(category), density[category]),
                quantity[category],
                uid=str(i),
            )
            for i, category in enumerate(categories)
        ],
    )


@pytest.mark.parametrize(
    "categories",
    [
        ["water", "cementitious", "fine_aggregate", "coarse_aggregate"],
        ["water", "cementitious", "fine_aggregate"],
        ["water", "cementitious"],
        ["water", "cementitious", "admixture"],
        ["water", "cementitious", "cementitious"],
        ["water", "cementitious", "fine_aggregate", "fine_aggregate", "coarse_aggregate"],
        ["water", "cementitious", "other"],
        ["water", "cementitious", "air"],
    ],
)
@pytest.mark.parametrize("locked", [False, True])
def test_general_volume_matrix(categories, locked):
    mix = mixture(categories, locked)
    result = MixCalculationEngine().recalculate(mix)
    assert result.converged, result.warnings
    assert abs(result.residual_l) < 0.02
    assert all(math.isfinite(c.quantity) and c.quantity >= 0 for c in mix.components)
    if locked:
        assert mix.actual_w_cm == pytest.approx(0.5)


def test_manual_locks_relations_and_conflicts_are_atomic():
    mix = mixture(["water", "cementitious", "fine_aggregate", "other"], True)
    mix.components[0].locked = True
    mix.ratio_constraints = [RatioConstraint("3", "1", 5, ConstraintMode.PERCENT_OF_B)]
    assert MixCalculationEngine().recalculate(mix).converged
    assert mix.components[0].quantity == 180
    assert mix.components[1].quantity == pytest.approx(360)
    assert mix.components[3].quantity == pytest.approx(18)
    mix.components[1].quantity = 400
    mix.components[1].locked = True
    before = [c.quantity for c in mix.components]
    result = MixCalculationEngine().recalculate(mix)
    assert not result.converged
    assert before == [c.quantity for c in mix.components]
    assert result.warnings


def test_other_only_zero_start_and_no_degrees_of_freedom():
    mix = mixture(["other"], False)
    mix.components[0].quantity = 0
    assert MixCalculationEngine().recalculate(mix).converged
    assert mix.components[0].quantity == pytest.approx(2200)
    mix.components[0].quantity = 10
    mix.components[0].locked = True
    assert not MixCalculationEngine().recalculate(mix).converged
    assert mix.components[0].quantity == 10
