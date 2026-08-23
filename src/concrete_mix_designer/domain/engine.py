from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from concrete_mix_designer.domain.models import (
    ConstraintMode,
    MaterialCategory,
    MixComponent,
    MixDesign,
    RatioConstraint,
)


@dataclass(slots=True)
class SolveResult:
    converged: bool
    residual_l: float
    warnings: list[str]


class MixCalculationEngine:
    """Constraint solver for the desktop MVP.

    Priority order:
    1. Locked water/cementitious ratio.
    2. Visible custom relationships and admixture dosage rules.
    3. Closure of absolute volume to the configured target, normally 1000 L.

    The first pass treats the component edited by the user as temporarily fixed.
    Reconciliation passes then solve all active constraints together.
    """

    TOLERANCE_L = 0.02
    VALUE_TOLERANCE = 1e-6

    def recalculate(self, design: MixDesign, changed_uid: str | None = None) -> SolveResult:
        design.warnings.clear()
        self._sanitize(design)

        if design.parameters.w_cm_locked:
            self._enforce_water_cementitious_ratio(design, changed_uid)
        self._enforce_constraints(design, changed_uid)
        self._close_absolute_volume(design, changed_uid)

        # Reconcile constraints after volumetric compensation. Pair constraints
        # preserve their combined mass when neither side is explicitly fixed,
        # which keeps cementitious totals and aggregate ratios stable.
        for _ in range(5):
            previous = self._state_signature(design)
            if design.parameters.w_cm_locked:
                self._enforce_water_cementitious_ratio(design, None)
            self._enforce_constraints(design, None)
            self._close_absolute_volume(design, None)
            if self._state_signature(design) == previous:
                break

        residual = design.parameters.target_volume_l - design.total_absolute_volume_l
        converged = abs(residual) <= self.TOLERANCE_L
        if not converged:
            design.warnings.append(
                f"No fue posible cerrar el volumen: quedan {residual:+.2f} L. "
                "Libera al menos un componente compatible o revisa los candados y relaciones."
            )
        design.warnings[:] = list(dict.fromkeys(design.warnings))
        return SolveResult(converged=converged, residual_l=residual, warnings=list(design.warnings))

    @staticmethod
    def _state_signature(design: MixDesign) -> tuple[float, ...]:
        return tuple(round(component.quantity, 8) for component in design.components)

    def _sanitize(self, design: MixDesign) -> None:
        params = design.parameters
        params.target_volume_l = self._finite_value(
            params.target_volume_l, "El volumen objetivo"
        )
        params.target_w_cm = self._finite_value(
            params.target_w_cm, "La relación agua/material cementante"
        )
        params.target_volume_l = max(params.target_volume_l, 1.0)
        params.target_w_cm = max(params.target_w_cm, 0.05)

        for component in design.components:
            component.quantity = self._finite_value(
                component.quantity,
                f"La cantidad de {component.material.name}",
            )
            component.quantity = max(component.quantity, 0.0)
            specific_gravity = self._finite_value(
                component.material.specific_gravity,
                f"La gravedad específica de {component.material.name}",
            )
            component.material.specific_gravity = specific_gravity
            if component.category != MaterialCategory.AIR and specific_gravity <= 0:
                component.material.specific_gravity = 1.0
                design.warnings.append(
                    f"Se corrigió la gravedad específica inválida de {component.material.name}."
                )

        for constraint in design.ratio_constraints:
            constraint.target_ratio = self._finite_value(
                constraint.target_ratio, "El objetivo de la relación o dosificación"
            )
            constraint.target_ratio = max(constraint.target_ratio, 0.0)

    @staticmethod
    def _finite_value(value: float, label: str) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} debe ser un número finito.") from error
        if not isfinite(numeric):
            raise ValueError(f"{label} debe ser un número finito.")
        return numeric

    def _enforce_water_cementitious_ratio(
        self, design: MixDesign, changed_uid: str | None
    ) -> None:
        waters = design.by_category(MaterialCategory.WATER)
        cementitious = design.by_category(MaterialCategory.CEMENTITIOUS)
        if not waters or not cementitious:
            design.warnings.append(
                "La relación a/mc requiere al menos un agua y un material cementante."
            )
            return

        changed = design.component(changed_uid)
        ratio = design.parameters.target_w_cm
        water_locked = all(component.locked for component in waters)
        cement_locked = all(component.locked for component in cementitious)

        if changed and changed.category == MaterialCategory.CEMENTITIOUS and not water_locked:
            target_water = design.total_cementitious_kg * ratio
            self._set_total_quantity(
                waters,
                target_water,
                temporary_fixed_uid=None,
                warning_sink=design.warnings,
                label="agua",
            )
            return

        if cement_locked and not water_locked:
            target_water = design.total_cementitious_kg * ratio
            self._set_total_quantity(
                waters,
                target_water,
                temporary_fixed_uid=(
                    changed_uid if changed and changed.category == MaterialCategory.WATER else None
                ),
                warning_sink=design.warnings,
                label="agua",
            )
            return

        target_cementitious = design.water_kg / ratio
        temporary_fixed = (
            changed_uid if changed and changed.category == MaterialCategory.CEMENTITIOUS else None
        )
        self._set_cementitious_total(design, target_cementitious, temporary_fixed)

    def _set_total_quantity(
        self,
        components: list[MixComponent],
        target_total: float,
        temporary_fixed_uid: str | None,
        warning_sink: list[str],
        label: str,
    ) -> None:
        fixed = [
            component
            for component in components
            if component.locked or component.uid == temporary_fixed_uid
        ]
        adjustable = [component for component in components if component not in fixed]
        fixed_total = sum(component.quantity for component in fixed)
        remainder = target_total - fixed_total

        if remainder < -self.VALUE_TOLERANCE:
            warning_sink.append(
                f"Conflicto de candados: los valores fijos de {label} superan el objetivo."
            )
            return
        if not adjustable:
            if abs(remainder) > self.VALUE_TOLERANCE:
                warning_sink.append(
                    f"No hay componentes libres de {label} para satisfacer la restricción."
                )
            return

        self._allocate_mass(adjustable, max(remainder, 0.0))

    def _set_cementitious_total(
        self,
        design: MixDesign,
        target_total: float,
        temporary_fixed_uid: str | None,
    ) -> None:
        components = design.by_category(MaterialCategory.CEMENTITIOUS)
        fixed = [
            component
            for component in components
            if component.locked or component.uid == temporary_fixed_uid
        ]
        adjustable = [component for component in components if component not in fixed]
        fixed_total = sum(component.quantity for component in fixed)
        remainder = target_total - fixed_total

        if remainder < -self.VALUE_TOLERANCE:
            design.warnings.append(
                "Conflicto de candados: los cementantes fijos exceden el total exigido por a/mc."
            )
            return
        if not adjustable:
            if abs(remainder) > self.VALUE_TOLERANCE:
                design.warnings.append(
                    "No hay cementantes libres para mantener la relación agua/material cementante."
                )
            return

        # Preserve the current visible proportions. Explicit composition rules
        # are applied immediately afterwards and therefore replace blend_pct.
        self._allocate_mass(adjustable, max(remainder, 0.0))

    @staticmethod
    def _allocate_mass(components: list[MixComponent], target_total: float) -> None:
        if not components:
            return
        weights = [max(component.quantity, 0.0) for component in components]
        if sum(weights) <= 1e-9:
            weights = [1.0] * len(components)
        total_weight = sum(weights)
        for component, weight in zip(components, weights, strict=True):
            component.quantity = target_total * weight / total_weight

    def _enforce_constraints(self, design: MixDesign, changed_uid: str | None) -> None:
        for constraint in design.ratio_constraints:
            if not constraint.enabled:
                continue
            numerator = design.component(constraint.numerator_uid)
            denominator = design.component(constraint.denominator_uid)
            if numerator is None:
                design.warnings.append("Existe una relación cuyo material A ya no está en el diseño.")
                continue
            if not numerator.enabled or (
                constraint.requires_denominator
                and denominator is not None
                and not denominator.enabled
            ):
                design.warnings.append(
                    f"{numerator.material.name}: la relación se omitió porque usa un componente inactivo."
                )
                continue
            if constraint.requires_denominator and (
                denominator is None or denominator.uid == numerator.uid
            ):
                design.warnings.append(
                    f"{numerator.material.name}: la relación requiere un material B válido."
                )
                continue

            if constraint.mode in {
                ConstraintMode.MASS_RATIO,
                ConstraintMode.PERCENT_OF_B,
                ConstraintMode.PERCENT_OF_PAIR,
            }:
                self._enforce_pair_mass_constraint(
                    design, constraint, numerator, denominator, changed_uid
                )
            elif constraint.mode == ConstraintMode.ML_PER_100KG_B:
                self._enforce_ml_per_component(
                    design, constraint, numerator, denominator, changed_uid
                )
            elif constraint.mode == ConstraintMode.PERCENT_OF_CEMENTITIOUS:
                self._enforce_percent_cementitious(design, constraint, numerator)
            elif constraint.mode == ConstraintMode.ML_PER_100KG_CEMENTITIOUS:
                self._enforce_ml_cementitious(design, constraint, numerator)

    def _enforce_pair_mass_constraint(
        self,
        design: MixDesign,
        constraint: RatioConstraint,
        numerator: MixComponent,
        denominator: MixComponent,
        changed_uid: str | None,
    ) -> None:
        numerator_fixed = numerator.locked or numerator.uid == changed_uid
        denominator_fixed = denominator.locked or denominator.uid == changed_uid

        if constraint.mode == ConstraintMode.PERCENT_OF_PAIR:
            fraction = constraint.target_ratio / 100.0
            if fraction > 1.0:
                design.warnings.append(
                    f"{numerator.material.name}: el porcentaje del total A+B no puede superar 100 %."
                )
                return
            if numerator_fixed and denominator_fixed:
                total = numerator.quantity + denominator.quantity
                actual = numerator.quantity / total if total > 1e-9 else 0.0
                if abs(actual - fraction) > self.VALUE_TOLERANCE:
                    self._fixed_constraint_warning(design, numerator, denominator)
                return
            if numerator_fixed:
                if fraction <= 1e-9:
                    if numerator.quantity > self.VALUE_TOLERANCE:
                        self._fixed_constraint_warning(design, numerator, denominator)
                    else:
                        numerator.quantity = 0.0
                    return
                denominator.quantity = max(numerator.quantity * (1.0 - fraction) / fraction, 0.0)
                return
            if denominator_fixed:
                if fraction >= 1.0 - 1e-9:
                    if denominator.quantity > self.VALUE_TOLERANCE:
                        self._fixed_constraint_warning(design, numerator, denominator)
                    else:
                        denominator.quantity = 0.0
                    return
                numerator.quantity = max(denominator.quantity * fraction / (1.0 - fraction), 0.0)
                return

            pair_total = numerator.quantity + denominator.quantity
            numerator.quantity = pair_total * fraction
            denominator.quantity = pair_total * (1.0 - fraction)
            return

        mass_ratio = constraint.target_ratio
        if constraint.mode == ConstraintMode.PERCENT_OF_B:
            mass_ratio /= 100.0

        if numerator_fixed and denominator_fixed:
            actual = numerator.quantity / denominator.quantity if denominator.quantity > 1e-9 else 0.0
            if abs(actual - mass_ratio) > self.VALUE_TOLERANCE:
                self._fixed_constraint_warning(design, numerator, denominator)
            return
        if numerator_fixed:
            if mass_ratio <= 1e-9:
                if numerator.quantity > self.VALUE_TOLERANCE:
                    self._fixed_constraint_warning(design, numerator, denominator)
                else:
                    denominator.quantity = max(denominator.quantity, 0.0)
                return
            denominator.quantity = numerator.quantity / mass_ratio
            return
        if denominator_fixed:
            numerator.quantity = denominator.quantity * mass_ratio
            return

        pair_total = numerator.quantity + denominator.quantity
        if mass_ratio <= 1e-9:
            numerator.quantity = 0.0
            denominator.quantity = pair_total
        else:
            denominator.quantity = pair_total / (1.0 + mass_ratio)
            numerator.quantity = pair_total - denominator.quantity

    def _enforce_ml_per_component(
        self,
        design: MixDesign,
        constraint: RatioConstraint,
        numerator: MixComponent,
        denominator: MixComponent,
        changed_uid: str | None,
    ) -> None:
        density = max(numerator.material.density_kg_l, 1e-9)
        dose = constraint.target_ratio
        numerator_fixed = numerator.locked or numerator.uid == changed_uid
        denominator_fixed = denominator.locked or denominator.uid == changed_uid

        if numerator_fixed and denominator_fixed:
            actual = self.constraint_actual_value(design, constraint)
            if abs(actual - dose) > self.VALUE_TOLERANCE:
                self._fixed_constraint_warning(design, numerator, denominator)
            return
        if numerator_fixed:
            if dose <= 1e-9:
                if numerator.quantity > self.VALUE_TOLERANCE:
                    self._fixed_constraint_warning(design, numerator, denominator)
                return
            denominator.quantity = numerator.quantity / density * 1000.0 * 100.0 / dose
            return

        # A is the dosed product. B remains the basis when neither is fixed.
        volume_l = dose * denominator.quantity / 100.0 / 1000.0
        numerator.quantity = volume_l * density

    def _enforce_percent_cementitious(
        self, design: MixDesign, constraint: RatioConstraint, numerator: MixComponent
    ) -> None:
        target = design.total_cementitious_kg * constraint.target_ratio / 100.0
        if numerator.locked:
            if abs(numerator.quantity - target) > self.VALUE_TOLERANCE:
                design.warnings.append(
                    f"{numerator.material.name} está bloqueado y no cumple su porcentaje del cementante total."
                )
            return
        numerator.quantity = target

    def _enforce_ml_cementitious(
        self, design: MixDesign, constraint: RatioConstraint, numerator: MixComponent
    ) -> None:
        density = max(numerator.material.density_kg_l, 1e-9)
        volume_l = (
            constraint.target_ratio * design.total_cementitious_kg / 100.0 / 1000.0
        )
        target = volume_l * density
        if numerator.locked:
            if abs(numerator.quantity - target) > self.VALUE_TOLERANCE:
                design.warnings.append(
                    f"{numerator.material.name} está bloqueado y no cumple su dosis por cementante total."
                )
            return
        numerator.quantity = target

    @staticmethod
    def _fixed_constraint_warning(
        design: MixDesign, numerator: MixComponent, denominator: MixComponent
    ) -> None:
        design.warnings.append(
            f"{numerator.material.name} y {denominator.material.name} están fijos y no cumplen la relación."
        )

    def constraint_actual_value(
        self, design: MixDesign, constraint: RatioConstraint
    ) -> float:
        numerator = design.component(constraint.numerator_uid)
        denominator = design.component(constraint.denominator_uid)
        if numerator is None:
            return 0.0
        if constraint.mode == ConstraintMode.MASS_RATIO:
            return numerator.quantity / denominator.quantity if denominator and denominator.quantity > 1e-9 else 0.0
        if constraint.mode == ConstraintMode.PERCENT_OF_B:
            return 100.0 * numerator.quantity / denominator.quantity if denominator and denominator.quantity > 1e-9 else 0.0
        if constraint.mode == ConstraintMode.PERCENT_OF_PAIR:
            total = numerator.quantity + (denominator.quantity if denominator else 0.0)
            return 100.0 * numerator.quantity / total if total > 1e-9 else 0.0
        if constraint.mode == ConstraintMode.PERCENT_OF_CEMENTITIOUS:
            total = design.total_cementitious_kg
            return 100.0 * numerator.quantity / total if total > 1e-9 else 0.0
        density = max(numerator.material.density_kg_l, 1e-9)
        numerator_ml = numerator.quantity / density * 1000.0
        if constraint.mode == ConstraintMode.ML_PER_100KG_B:
            return numerator_ml * 100.0 / denominator.quantity if denominator and denominator.quantity > 1e-9 else 0.0
        if constraint.mode == ConstraintMode.ML_PER_100KG_CEMENTITIOUS:
            total = design.total_cementitious_kg
            return numerator_ml * 100.0 / total if total > 1e-9 else 0.0
        return 0.0

    def _close_absolute_volume(self, design: MixDesign, changed_uid: str | None) -> None:
        residual = design.parameters.target_volume_l - design.total_absolute_volume_l
        if abs(residual) <= self.TOLERANCE_L:
            return

        aggregates = [
            component
            for component in design.enabled_components()
            if component.category in (MaterialCategory.FINE_AGGREGATE, MaterialCategory.COARSE_AGGREGATE)
            and not component.locked
            and component.uid != changed_uid
        ]
        if not aggregates:
            aggregates = [
                component
                for component in design.enabled_components()
                if component.category in (MaterialCategory.FINE_AGGREGATE, MaterialCategory.COARSE_AGGREGATE)
                and not component.locked
            ]
        if aggregates:
            self._adjust_pool_by_absolute_volume(aggregates, residual)

        residual = design.parameters.target_volume_l - design.total_absolute_volume_l
        if abs(residual) <= self.TOLERANCE_L:
            return
        if design.parameters.w_cm_locked:
            self._adjust_water_cementitious_pair(design, residual, changed_uid)

    def _adjust_pool_by_absolute_volume(
        self, pool: list[MixComponent], delta_l: float
    ) -> None:
        if not pool or abs(delta_l) <= self.TOLERANCE_L:
            return

        if delta_l > 0:
            current_volumes = [component.absolute_volume_l for component in pool]
            weights = current_volumes if sum(current_volumes) > 1e-9 else [1.0] * len(pool)
            weight_sum = sum(weights)
            for component, weight in zip(pool, weights, strict=True):
                add_l = delta_l * weight / weight_sum
                component.quantity += add_l * component.material.specific_gravity
            return

        volume_to_remove = -delta_l
        active = list(pool)
        while active and volume_to_remove > self.TOLERANCE_L:
            current = [component.absolute_volume_l for component in active]
            current_total = sum(current)
            if current_total <= 1e-9:
                break
            removed_this_round = 0.0
            survivors: list[MixComponent] = []
            for component, component_volume in zip(active, current, strict=True):
                requested = volume_to_remove * component_volume / current_total
                removable = min(requested, component_volume)
                new_volume = component_volume - removable
                component.quantity = new_volume * component.material.specific_gravity
                removed_this_round += removable
                if new_volume > self.TOLERANCE_L:
                    survivors.append(component)
            if removed_this_round <= 1e-9:
                break
            volume_to_remove -= removed_this_round
            active = survivors

    def _adjust_water_cementitious_pair(
        self, design: MixDesign, residual_l: float, changed_uid: str | None
    ) -> None:
        all_waters = design.by_category(MaterialCategory.WATER)
        all_cementitious = design.by_category(MaterialCategory.CEMENTITIOUS)
        adjustable_waters = [
            component
            for component in all_waters
            if not component.locked and component.uid != changed_uid
        ]
        adjustable_cementitious = [
            component
            for component in all_cementitious
            if not component.locked and component.uid != changed_uid
        ]
        if not adjustable_waters or not adjustable_cementitious:
            return

        ratio = design.parameters.target_w_cm
        weights = [max(component.quantity, 0.0) for component in adjustable_cementitious]
        if sum(weights) <= 1e-9:
            weights = [1.0] * len(adjustable_cementitious)
        weight_sum = sum(weights)

        liters_per_kg_cementitious = ratio
        for component, weight in zip(adjustable_cementitious, weights, strict=True):
            share = weight / weight_sum
            liters_per_kg_cementitious += share / component.material.specific_gravity
        if liters_per_kg_cementitious <= 1e-9:
            return

        target_total_c = design.total_cementitious_kg + residual_l / liters_per_kg_cementitious
        if target_total_c <= 0:
            return
        self._set_cementitious_total(design, target_total_c, temporary_fixed_uid=None)
        self._set_total_quantity(
            all_waters,
            target_total_c * ratio,
            temporary_fixed_uid=None,
            warning_sink=design.warnings,
            label="agua",
        )

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
                raise ValueError(
                    f"La cantidad de {component.material.name} no puede ser negativa."
                )
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
                component.material.moisture_pct,
                f"La humedad de {component.material.name}",
            )
            if absorption_pct < 0:
                raise ValueError(
                    f"La absorción de {component.material.name} no puede ser negativa."
                )
            if moisture_pct < 0:
                raise ValueError(
                    f"La humedad de {component.material.name} no puede ser negativa."
                )

        for component in design.enabled_components():
            if component.category not in (
                MaterialCategory.FINE_AGGREGATE,
                MaterialCategory.COARSE_AGGREGATE,
            ):
                continue
            absorption = component.material.absorption_pct / 100.0
            moisture = component.material.moisture_pct / 100.0
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
                        "design_quantity": component.quantity,
                        "corrected_quantity": component.quantity,
                        "water_contribution": 0.0,
                        "excess_free_water_kg": excess_free_water,
                        "water_balance_warning": water_balance_warning,
                    }
                )
                continue

            aggregate = next(
                (row for row in aggregate_rows if row["uid"] == component.uid), None
            )
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
                    "design_quantity": component.quantity,
                    "corrected_quantity": corrected,
                    "water_contribution": contribution,
                    "excess_free_water_kg": excess_free_water,
                    "water_balance_warning": water_balance_warning,
                }
            )
        return results
