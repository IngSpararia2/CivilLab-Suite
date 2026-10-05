from __future__ import annotations

from dataclasses import dataclass
from math import log2


@dataclass(slots=True)
class AciSuggestion:
    water_kg_m3: float
    w_cm: float
    air_pct: float
    note: str


# The initial values are isolated in this module so the source can be replaced
# or calibrated without coupling the user interface to the calculation logic.


def suggest_initial_values(
    fc_mpa: float,
    slump_mm: float,
    nominal_max_size_mm: float,
    air_entrained: bool,
) -> AciSuggestion:
    fc = max(14.0, min(float(fc_mpa), 55.0))
    slump = max(25.0, min(float(slump_mm), 200.0))
    nms = max(9.5, min(float(nominal_max_size_mm), 75.0))

    # More slump increases the initial water estimate; larger aggregate reduces it.
    water = 190.0 + 0.16 * (slump - 75.0) - 11.0 * log2(nms / 19.0)
    if air_entrained:
        water -= 14.0
    water = max(125.0, min(water, 240.0))

    anchor_points = [
        (17.5, 0.67),
        (21.0, 0.58),
        (28.0, 0.49),
        (35.0, 0.42),
        (42.0, 0.37),
        (50.0, 0.33),
        (55.0, 0.30),
    ]
    w_cm = _linear_interpolation(fc, anchor_points)
    air_pct = _suggest_air(nms, air_entrained)
    return AciSuggestion(
        water_kg_m3=round(water, 1),
        w_cm=round(w_cm, 3),
        air_pct=round(air_pct, 1),
        note=(
            "Valores iniciales calculados con los parámetros seleccionados. "
            "Ajusta la dosificación con los resultados de la mezcla de prueba."
        ),
    )


def _linear_interpolation(x: float, points: list[tuple[float, float]]) -> float:
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if x0 <= x <= x1:
            factor = (x - x0) / (x1 - x0)
            return y0 + factor * (y1 - y0)
    return points[-1][1]


def _suggest_air(nms: float, air_entrained: bool) -> float:
    if not air_entrained:
        return 2.0 if nms <= 19 else 1.5
    if nms <= 12.5:
        return 6.0
    if nms <= 19:
        return 5.5
    if nms <= 25:
        return 5.0
    if nms <= 37.5:
        return 4.5
    return 4.0
