from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from concrete_mix_designer.domain.models import (
    ConstraintMode,
    MaterialCategory,
    MixDesign,
    RatioConstraint,
)


@dataclass(slots=True)
class SolveResult:
    converged: bool
    residual_l: float
    warnings: list[str]


class MixCalculationEngine:
    """Simultaneous linear physical constraints, nonnegative masses and manual locks.

    Free quantities use a deterministic weighted projection. Edited quantities and
    independent non-aggregate masses are preferences, relaxed only if necessary.
    Infeasible systems leave every input quantity unchanged.
    """

    TOLERANCE_L = 0.02
    VALUE_TOLERANCE = 1e-6

    def recalculate(self, design: MixDesign, changed_uid: str | None = None) -> SolveResult:
        from concrete_mix_designer.domain.linear_solver import closest_solution

        design.warnings.clear()
        components = design.enabled_components()
        n = len(components)
        index = {c.uid: i for i, c in enumerate(components)}
        if len(index) != n:
            raise ValueError("Los componentes deben tener identificadores únicos.")
        target = self._finite_value(design.parameters.target_volume_l, "El volumen objetivo")
        ratio = self._finite_value(design.parameters.target_w_cm, "La relación a/mc")
        if target <= 0 or (design.parameters.w_cm_locked and ratio <= 0):
            raise ValueError("Volumen y relación bloqueada deben ser positivos.")
        quantities = []
        volumes = []
        for c in components:
            q = self._finite_value(c.quantity, f"La cantidad de {c.material.name}")
            sg = self._finite_value(c.material.specific_gravity, "La gravedad específica")
            if q < 0 or sg <= 0:
                raise ValueError(
                    "Las masas no pueden ser negativas y la gravedad debe ser positiva."
                )
            quantities.append(q)
            volumes.append(1.0 if c.category == MaterialCategory.AIR else 1.0 / sg)
        rows, rhs = [volumes], [target]

        def fixed(i, value):
            row = [0.0] * n
            row[i] = 1.0
            return row, value

        for i, c in enumerate(components):
            if c.locked:
                row, value = fixed(i, c.quantity)
                rows.append(row)
                rhs.append(value)
        water = [i for i, c in enumerate(components) if c.category == MaterialCategory.WATER]
        cement = [
            i for i, c in enumerate(components) if c.category == MaterialCategory.CEMENTITIOUS
        ]
        if design.parameters.w_cm_locked:
            if not water or not cement:
                design.warnings.append(
                    "La relación a/mc requiere al menos un agua y un material cementante."
                )
                return self._failed(design)
            row = [0.0] * n
            for i in water:
                row[i] = 1.0
            for i in cement:
                row[i] = -ratio
            rows.append(row)
            rhs.append(0.0)
        invalid = False
        for constraint in design.ratio_constraints:
            if not constraint.enabled:
                continue
            a = design.component(constraint.numerator_uid)
            b = design.component(constraint.denominator_uid)
            if a is not None and (not a.enabled or (b is not None and not b.enabled)):
                design.warnings.append("Relación omitida: usa un componente inactivo.")
                continue
            if a is None or (constraint.requires_denominator and (b is None or b.uid == a.uid)):
                design.warnings.append(
                    "Relación inválida: falta un componente o se relaciona consigo mismo."
                )
                invalid = True
                continue
            value = self._finite_value(constraint.target_ratio, "La relación")
            if value < 0 or (constraint.mode == ConstraintMode.PERCENT_OF_PAIR and value > 100):
                raise ValueError("Objetivo de relación fuera de rango.")
            if a.category == MaterialCategory.AIR or (b and b.category == MaterialCategory.AIR):
                design.warnings.append("Una relación de masas no puede usar aire en litros.")
                invalid = True
                continue
            row = [0.0] * n
            row[index[a.uid]] = 1.0
            if constraint.mode == ConstraintMode.PERCENT_OF_PAIR:
                row[index[a.uid]] = 1.0 - value / 100.0
                row[index[b.uid]] = -value / 100.0
            elif constraint.mode in (
                ConstraintMode.PERCENT_OF_CEMENTITIOUS,
                ConstraintMode.ML_PER_100KG_CEMENTITIOUS,
            ):
                coefficient = value / 100.0
                if constraint.mode == ConstraintMode.ML_PER_100KG_CEMENTITIOUS:
                    coefficient *= a.material.density_kg_l / 1000.0
                if not cement:
                    invalid = True
                    design.warnings.append("La dosificación requiere material cementante.")
                for i in cement:
                    row[i] -= coefficient
            else:
                coefficient = value
                if constraint.mode == ConstraintMode.PERCENT_OF_B:
                    coefficient /= 100.0
                if constraint.mode == ConstraintMode.ML_PER_100KG_B:
                    coefficient *= a.material.density_kg_l / 100000.0
                row[index[b.uid]] -= coefficient
            rows.append(row)
            rhs.append(0.0)
        if invalid:
            return self._failed(design)
        # Prefer keeping independent non-aggregate quantities; relax these preferences
        # only when the physical equations require it. Manual locks are never relaxed.
        controlled = design.controlled_reasons
        preferences = [
            i
            for i, c in enumerate(components)
            if not c.locked
            and c.uid not in controlled
            and c.category
            not in (MaterialCategory.FINE_AGGREGATE, MaterialCategory.COARSE_AGGREGATE)
        ]
        preferred_rows = [fixed(i, quantities[i]) for i in preferences]
        weights = [max(q, 1.0) ** 2 for q in quantities]
        attempts = [preferred_rows, []]
        if changed_uid in index and not components[index[changed_uid]].locked:
            changed = fixed(index[changed_uid], quantities[index[changed_uid]])
            attempts.insert(0, preferred_rows + [changed])
        solution = None
        for extra in attempts:
            solution = closest_solution(
                rows + [r for r, _ in extra], rhs + [v for _, v in extra], quantities, weights
            )
            if solution is not None:
                if design.parameters.w_cm_locked and sum(solution[i] for i in cement) <= 1e-9:
                    solution = None
                    continue
                break
        if solution is None or any(not isfinite(q) for q in solution):
            design.warnings.append(
                "Conflicto de candados/relaciones: no hay grados de libertad compatibles; se conservan las cantidades."
            )
            return self._failed(design)
        if any(
            abs(sum(a * x for a, x in zip(row, solution, strict=True)) - value) > 1e-5
            for row, value in zip(rows, rhs, strict=True)
        ):
            design.warnings.append(
                "El sistema no cumple simultáneamente las restricciones; se conservan las cantidades."
            )
            return self._failed(design)
        for c, value in zip(components, solution, strict=True):
            if not c.locked:
                c.quantity = value
        return SolveResult(True, target - design.total_absolute_volume_l, list(design.warnings))

    def _failed(self, design):
        residual = design.parameters.target_volume_l - design.total_absolute_volume_l
        design.warnings.append(
            f"No fue posible cerrar el volumen y las restricciones: residual {residual:+.3f} L."
        )
        return SolveResult(False, residual, list(design.warnings))

    @staticmethod
    def _finite_value(value: float, label: str) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} debe ser un número finito.") from error
        if not isfinite(numeric):
            raise ValueError(f"{label} debe ser un número finito.")
        return numeric

    def constraint_actual_value(self, design: MixDesign, constraint: RatioConstraint) -> float:
        numerator = design.component(constraint.numerator_uid)
        denominator = design.component(constraint.denominator_uid)
        if numerator is None:
            return 0.0
        if constraint.mode == ConstraintMode.MASS_RATIO:
            return (
                numerator.quantity / denominator.quantity
                if denominator and denominator.quantity > 1e-9
                else 0.0
            )
        if constraint.mode == ConstraintMode.PERCENT_OF_B:
            return (
                100.0 * numerator.quantity / denominator.quantity
                if denominator and denominator.quantity > 1e-9
                else 0.0
            )
        if constraint.mode == ConstraintMode.PERCENT_OF_PAIR:
            total = numerator.quantity + (denominator.quantity if denominator else 0.0)
            return 100.0 * numerator.quantity / total if total > 1e-9 else 0.0
        if constraint.mode == ConstraintMode.PERCENT_OF_CEMENTITIOUS:
            total = design.total_cementitious_kg
            return 100.0 * numerator.quantity / total if total > 1e-9 else 0.0
        density = max(numerator.material.density_kg_l, 1e-9)
        numerator_ml = numerator.quantity / density * 1000.0
        if constraint.mode == ConstraintMode.ML_PER_100KG_B:
            return (
                numerator_ml * 100.0 / denominator.quantity
                if denominator and denominator.quantity > 1e-9
                else 0.0
            )
        if constraint.mode == ConstraintMode.ML_PER_100KG_CEMENTITIOUS:
            total = design.total_cementitious_kg
            return numerator_ml * 100.0 / total if total > 1e-9 else 0.0
        return 0.0

    def moisture_correction(self, design: MixDesign) -> list[dict[str, float | str]]:
        """Return batch quantities using aggregate moisture/absorption.

        Design aggregate quantities are treated as SSD masses. For each aggregate:
          OD = SSD / (1 + absorption)
          wet batch mass = OD * (1 + moisture)
          free water = OD * (moisture - absorption)
        """
        aggregate_rows: list[dict[str, float | str]] = []
        total_free_water = 0.0

        for component in design.enabled_components():
            quantity = self._finite_value(
                component.quantity, f"La cantidad de {component.material.name}"
            )
            if quantity < 0:
                raise ValueError(f"La cantidad de {component.material.name} no puede ser negativa.")
            if component.category not in (
                MaterialCategory.FINE_AGGREGATE,
                MaterialCategory.COARSE_AGGREGATE,
            ):
                continue
            absorption_pct = self._finite_value(
                component.material.absorption_pct,
                f"La absorción de {component.material.name}",
            )
            moisture_pct = self._finite_value(
                design.batch_moistures.get(component.uid, component.material.moisture_pct),
                f"La humedad de {component.material.name}",
            )
            if absorption_pct < 0:
                raise ValueError(
                    f"La absorción de {component.material.name} no puede ser negativa."
                )
            if moisture_pct < 0:
                raise ValueError(f"La humedad de {component.material.name} no puede ser negativa.")

        for component in design.enabled_components():
            if component.category not in (
                MaterialCategory.FINE_AGGREGATE,
                MaterialCategory.COARSE_AGGREGATE,
            ):
                continue
            absorption = component.material.absorption_pct / 100.0
            moisture = (
                design.batch_moistures.get(component.uid, component.material.moisture_pct) / 100.0
            )
            od_mass = component.quantity / (1.0 + absorption)
            wet_mass = od_mass * (1.0 + moisture)
            free_water = od_mass * (moisture - absorption)
            total_free_water += free_water
            aggregate_rows.append(
                {
                    "uid": component.uid,
                    "name": component.material.name,
                    "design_ssd_kg": component.quantity,
                    "batch_wet_kg": wet_mass,
                    "free_water_kg": free_water,
                }
            )

        water_components = design.by_category(MaterialCategory.WATER)
        design_water = sum(component.quantity for component in water_components)
        corrected_water = max(design_water - total_free_water, 0.0)
        applied_water_adjustment = corrected_water - design_water
        excess_free_water = max(total_free_water - design_water, 0.0)
        water_balance_warning = ""
        if excess_free_water > self.VALUE_TOLERANCE:
            water_balance_warning = (
                f"Los agregados aportan {excess_free_water:.3f} kg de agua libre por encima "
                "del agua de diseño. El agua a cargar se limita a 0 kg, pero la relación "
                "a/mc efectiva aumentará; revise humedades o dosificación."
            )

        results: list[dict[str, float | str]] = []
        for component in design.enabled_components():
            if component.category == MaterialCategory.AIR:
                results.append(
                    {
                        "uid": component.uid,
                        "name": component.material.name,
                        "unit": "L",
                        "absorption_pct": component.material.absorption_pct,
                        "moisture_pct": design.batch_moistures.get(
                            component.uid, component.material.moisture_pct
                        ),
                        "mass_basis": "SSD",
                        "design_quantity": component.quantity,
                        "corrected_quantity": component.quantity,
                        "water_contribution": 0.0,
                        "excess_free_water_kg": excess_free_water,
                        "water_balance_warning": water_balance_warning,
                    }
                )
                continue

            aggregate = next((row for row in aggregate_rows if row["uid"] == component.uid), None)
            if aggregate:
                corrected = float(aggregate["batch_wet_kg"])
                contribution = float(aggregate["free_water_kg"])
            elif component.category == MaterialCategory.WATER:
                water_share = (
                    component.quantity / design_water
                    if design_water > 0
                    else (1.0 / len(water_components) if water_components else 0.0)
                )
                contribution = applied_water_adjustment * water_share
                corrected = component.quantity + contribution
            else:
                corrected = component.quantity
                contribution = 0.0

            results.append(
                {
                    "uid": component.uid,
                    "name": component.material.name,
                    "unit": "kg",
                    "absorption_pct": component.material.absorption_pct,
                    "moisture_pct": design.batch_moistures.get(
                        component.uid, component.material.moisture_pct
                    ),
                    "mass_basis": "SSD",
                    "design_quantity": component.quantity,
                    "corrected_quantity": corrected,
                    "water_contribution": contribution,
                    "excess_free_water_kg": excess_free_water,
                    "water_balance_warning": water_balance_warning,
                }
            )
        return results
