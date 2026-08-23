from __future__ import annotations

from math import isfinite, pi

MM_PER_INCH = 25.4
PSI_PER_MPA = 145.03773773020923
KGF_CM2_PER_MPA = 10.197162129779

PRESSURE_UNIT_LABELS: dict[str, str] = {
    "mpa": "MPa",
    "psi": "psi",
    "kgf_cm2": "kgf/cm²",
}


def _finite_value(value: float, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} debe ser un número finito.") from error
    if not isfinite(numeric):
        raise ValueError(f"{label} debe ser un número finito.")
    return numeric


def length_to_mm(value: float, unit: str) -> float:
    value = _finite_value(value, "La longitud")
    unit_key = str(unit).lower()
    if unit_key == "in":
        return value * MM_PER_INCH
    if unit_key == "mm":
        return value
    raise ValueError(f"Unidad de longitud no admitida: {unit}")


def mm_to_length(value_mm: float, unit: str) -> float:
    value_mm = _finite_value(value_mm, "La longitud")
    unit_key = str(unit).lower()
    if unit_key == "in":
        return value_mm / MM_PER_INCH
    if unit_key == "mm":
        return value_mm
    raise ValueError(f"Unidad de longitud no admitida: {unit}")


def pressure_to_mpa(value: float, unit: str) -> float:
    value = _finite_value(value, "La presión")
    unit_key = str(unit).lower()
    if unit_key == "mpa":
        return value
    if unit_key == "psi":
        return value / PSI_PER_MPA
    if unit_key == "kgf_cm2":
        return value / KGF_CM2_PER_MPA
    raise ValueError(f"Unidad de presión no admitida: {unit}")


def mpa_to_pressure(value_mpa: float, unit: str) -> float:
    value_mpa = _finite_value(value_mpa, "La presión")
    unit_key = str(unit).lower()
    if unit_key == "mpa":
        return value_mpa
    if unit_key == "psi":
        return value_mpa * PSI_PER_MPA
    if unit_key == "kgf_cm2":
        return value_mpa * KGF_CM2_PER_MPA
    raise ValueError(f"Unidad de presión no admitida: {unit}")


def cylinder_volume_l(diameter_mm: float, height_mm: float) -> float:
    diameter_mm = _finite_value(diameter_mm, "El diámetro")
    height_mm = _finite_value(height_mm, "La altura")
    if diameter_mm < 0 or height_mm < 0:
        raise ValueError("Las dimensiones no pueden ser negativas.")
    return pi * (diameter_mm / 1000.0) ** 2 / 4.0 * (height_mm / 1000.0) * 1000.0


def beam_volume_l(width_mm: float, depth_mm: float, length_mm: float) -> float:
    width_mm = _finite_value(width_mm, "El ancho")
    depth_mm = _finite_value(depth_mm, "La profundidad")
    length_mm = _finite_value(length_mm, "La longitud")
    if width_mm < 0 or depth_mm < 0 or length_mm < 0:
        raise ValueError("Las dimensiones no pueden ser negativas.")
    return width_mm * depth_mm * length_mm / 1_000_000.0
