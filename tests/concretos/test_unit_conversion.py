from __future__ import annotations

import pytest

from concrete_mix_designer.services.unit_conversion import (
    beam_volume_l,
    cylinder_volume_l,
    length_to_mm,
    mm_to_length,
    mpa_to_pressure,
    pressure_to_mpa,
)


def test_slump_inch_millimetre_round_trip():
    assert length_to_mm(4.0, "in") == pytest.approx(101.6)
    assert mm_to_length(101.6, "in") == pytest.approx(4.0)


def test_pressure_round_trips():
    for unit in ("mpa", "psi", "kgf_cm2"):
        displayed = mpa_to_pressure(28.0, unit)
        assert pressure_to_mpa(displayed, unit) == pytest.approx(28.0)


def test_sampling_volumes_include_cylinders_and_beams():
    cylinder_l = cylinder_volume_l(100.0, 200.0)
    beam_l = beam_volume_l(150.0, 150.0, 500.0)
    assert cylinder_l == pytest.approx(1.570796, rel=1e-6)
    assert beam_l == pytest.approx(11.25)
    assert 6 * cylinder_l + 2 * beam_l > 30.0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_conversion_inputs_are_rejected(value):
    with pytest.raises(ValueError, match="número finito"):
        length_to_mm(value, "mm")
    with pytest.raises(ValueError, match="número finito"):
        pressure_to_mpa(value, "mpa")
    with pytest.raises(ValueError, match="número finito"):
        cylinder_volume_l(value, 200.0)
