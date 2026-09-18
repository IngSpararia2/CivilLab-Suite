from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

PERCENT_TOLERANCE = 0.01


@dataclass(frozen=True, slots=True)
class RecipeEntry:
    key: str
    quantity: float
    specific_gravity: float
    is_air: bool = False


@dataclass(frozen=True, slots=True)
class PercentageEntry:
    key: str
    percentage: float
    specific_gravity: float


@dataclass(frozen=True, slots=True)
class NormalizedRecipe:
    quantities: dict[str, float]
    observed_volumes_l: dict[str, float]
    observed_volume_l: float
    scale_factor: float
    normalized_volume_l: float


def _finite(value: float, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} debe ser un número finito.") from error
    if not isfinite(numeric):
        raise ValueError(f"{label} debe ser un número finito.")
    return numeric


def _unique_keys(entries: list[RecipeEntry] | list[PercentageEntry]) -> None:
    keys = [entry.key for entry in entries]
    if len(keys) != len(set(keys)):
        raise ValueError("No se puede incluir el mismo material más de una vez.")


def absolute_volume_l(quantity: float, specific_gravity: float, *, is_air: bool = False) -> float:
    """Return absolute volume in litres using CivilLab's kg/SG convention."""

    quantity = _finite(quantity, "La cantidad")
    if quantity < 0:
        raise ValueError("La cantidad no puede ser negativa.")
    if is_air:
        return quantity
    specific_gravity = _finite(specific_gravity, "La gravedad específica")
    if specific_gravity <= 0:
        raise ValueError("La gravedad específica debe ser mayor que cero.")
    return quantity / specific_gravity


def normalize_observed_recipe(
    entries: list[RecipeEntry], target_volume_l: float = 1000.0
) -> NormalizedRecipe:
    """Scale an observed recipe to the requested absolute volume."""

    if not entries:
        raise ValueError("Agrega al menos un material a la receta observada.")
    _unique_keys(entries)
    target_volume_l = _finite(target_volume_l, "El volumen objetivo")
    if target_volume_l <= 0:
        raise ValueError("El volumen objetivo debe ser mayor que cero.")

    volumes = {
        entry.key: absolute_volume_l(
            entry.quantity, entry.specific_gravity, is_air=entry.is_air
        )
        for entry in entries
    }
    observed = sum(volumes.values())
    if not isfinite(observed) or observed <= 0:
        raise ValueError("El volumen observado debe ser mayor que cero.")
    factor = target_volume_l / observed
    quantities = {
        entry.key: _finite(entry.quantity, "La cantidad") * factor for entry in entries
    }
    normalized_volume = sum(
        absolute_volume_l(
            quantities[entry.key], entry.specific_gravity, is_air=entry.is_air
        )
        for entry in entries
    )
    if not all(isfinite(value) for value in (*quantities.values(), factor, normalized_volume)):
        raise ValueError("La receta produce resultados no finitos.")
    return NormalizedRecipe(
        quantities=quantities,
        observed_volumes_l=volumes,
        observed_volume_l=observed,
        scale_factor=factor,
        normalized_volume_l=normalized_volume,
    )


def quantities_from_mass_percentages(
    entries: list[PercentageEntry],
    *,
    air_volume_l: float = 0.0,
    target_volume_l: float = 1000.0,
    tolerance: float = PERCENT_TOLERANCE,
) -> dict[str, float]:
    """Convert mass percentages to quantities that close by absolute volume."""

    if not entries:
        raise ValueError("No hay componentes en kg para calcular porcentajes.")
    _unique_keys(entries)
    target_volume_l = _finite(target_volume_l, "El volumen objetivo")
    air_volume_l = _finite(air_volume_l, "El volumen de aire")
    if target_volume_l <= 0:
        raise ValueError("El volumen objetivo debe ser mayor que cero.")
    if air_volume_l < 0:
        raise ValueError("El volumen de aire no puede ser negativo.")
    if air_volume_l >= target_volume_l:
        raise ValueError("El volumen de aire debe ser menor que el volumen objetivo.")

    total = 0.0
    denominator = 0.0
    for entry in entries:
        percentage = _finite(entry.percentage, "El porcentaje")
        sg = _finite(entry.specific_gravity, "La gravedad específica")
        if percentage < 0:
            raise ValueError("Los porcentajes no pueden ser negativos.")
        if sg <= 0:
            raise ValueError("La gravedad específica debe ser mayor que cero.")
        total += percentage
        denominator += (percentage / 100.0) / sg
    if abs(total - 100.0) > tolerance:
        raise ValueError(f"Los porcentajes deben sumar 100 %; actualmente suman {total:.3f} %.")
    if denominator <= 0 or not isfinite(denominator):
        raise ValueError("Los porcentajes no definen una masa válida.")

    total_mass = (target_volume_l - air_volume_l) / denominator
    quantities = {
        entry.key: total_mass * entry.percentage / 100.0 for entry in entries
    }
    if not all(isfinite(value) and value >= 0 for value in quantities.values()):
        raise ValueError("Los porcentajes producen cantidades no válidas.")
    return quantities
