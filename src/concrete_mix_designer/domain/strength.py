"""ACI PRC-211.1-22 §4.7.4, referencing ACI SPEC-301-20.

The inch-pound tables are converted exactly to MPa, not mixed with rounded
SI-edition thresholds. One observation is a complete same-batch/age sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from statistics import fmean, stdev

PSI_MPA = 0.006894757293168361
STANDARD = "ACI PRC-211.1-22 §4.7.4 / ACI SPEC-301-20 (psi convertido a MPa)"


@dataclass(frozen=True)
class StrengthTest:
    key: str
    production_id: int
    age_days: float
    tested_on: date
    specimen_ids: tuple[int, ...]
    strength_mpa: float


def modification_factor(n: int) -> float:
    if n < 15:
        raise ValueError("Se requieren al menos 15 ensayos de resistencia completos.")
    for low, high, a, b in ((15, 20, 1.16, 1.08), (20, 25, 1.08, 1.03), (25, 30, 1.03, 1.00)):
        if n <= high:
            return a + (b - a) * (n - low) / (high - low)
    return 1.0


def required_strength(
    fc_mpa: float,
    *,
    tests: list[StrengthTest] | None = None,
    series_id: int | None = None,
    age_days: float = 28,
    as_of: date | None = None,
    comparable: bool = False,
) -> dict:
    if not isfinite(fc_mpa) or fc_mpa <= 0:
        raise ValueError("f'c debe ser finito y positivo.")
    today = as_of or date.today()
    result = {
        "mode": "no_history",
        "fc_mpa": fc_mpa,
        "standard": STANDARD,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today.isoformat(),
        "series_id": series_id,
        "age_days": age_days,
        "n": 0,
        "mean_mpa": None,
        "s_mpa": None,
        "factor": None,
        "tests": [],
    }
    fc_psi = fc_mpa / PSI_MPA
    if tests is None:
        required = (
            fc_psi + 1000
            if fc_psi < 3000
            else fc_psi + 1200
            if fc_psi <= 5000
            else 1.1 * fc_psi + 700
        )
        result["fcr_mpa"] = required * PSI_MPA
        return result
    if not comparable or series_id is None:
        raise ValueError(
            "Selecciona una serie y confirma materiales, condiciones y resistencia comparables."
        )
    if len({test.key for test in tests}) != len(tests):
        raise ValueError("La serie contiene ensayos duplicados.")
    factor = modification_factor(len(tests))
    first, last = min(t.tested_on for t in tests), max(t.tested_on for t in tests)
    cutoff = (
        today.replace(year=today.year - 2, day=min(today.day, 28))
        if today.month == 2
        else today.replace(year=today.year - 2)
    )
    if first < cutoff or last > today or (last - first).days < 45:
        raise ValueError("La serie debe abarcar al menos 45 días dentro de los últimos 24 meses.")
    if any(
        t.age_days != age_days or not isfinite(t.strength_mpa) or t.strength_mpa <= 0 for t in tests
    ):
        raise ValueError("La serie debe tener una sola edad y resultados positivos finitos.")
    values = [t.strength_mpa for t in tests]
    deviation = stdev(values)
    adjusted = factor * deviation
    eq1 = fc_mpa + 1.34 * adjusted
    eq2 = (
        fc_mpa + 2.33 * adjusted - 500 * PSI_MPA
        if fc_psi <= 5000
        else 0.90 * fc_mpa + 2.33 * adjusted
    )
    result.update(
        mode="statistical",
        n=len(tests),
        mean_mpa=fmean(values),
        s_mpa=deviation,
        factor=factor,
        from_date=first.isoformat(),
        to_date=last.isoformat(),
        fcr_mpa=max(eq1, eq2),
        equations_mpa=[eq1, eq2],
        comparable=True,
        tests=[
            {
                "key": t.key,
                "specimen_ids": list(t.specimen_ids),
                "strength_mpa": t.strength_mpa,
                "tested_on": t.tested_on.isoformat(),
            }
            for t in tests
        ],
    )
    return result
