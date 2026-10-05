from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from concrete_mix_designer.data.database import MaterialRepository
from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
from concrete_mix_designer.domain.aci_seed import AciSuggestion, suggest_initial_values
from concrete_mix_designer.domain.engine import MixCalculationEngine, SolveResult
from concrete_mix_designer.domain.laboratory_models import (
    FreshTestType,
    ProductionRecord,
    SavedDesignRecord,
    SpecimenStatus,
    SpecimenType,
)
from concrete_mix_designer.domain.metadata_models import (
    DesignSpecification,
    MaterialCharacterization,
)
from concrete_mix_designer.domain.mix_normalization import (
    PERCENT_TOLERANCE,
    PercentageEntry,
    quantities_from_mass_percentages,
)
from concrete_mix_designer.domain.models import (
    ConstraintMode,
    Material,
    MaterialCategory,
    MixComponent,
    MixDesign,
    MixParameters,
    RatioConstraint,
)


class AppState(QObject):
    design_changed = Signal()
    materials_changed = Signal()
    library_changed = Signal()
    productions_changed = Signal()
    message = Signal(str)
    calculation_mode_changed = Signal()

    def __init__(
        self,
        repository: MaterialRepository,
        laboratory_repository: LaboratoryRepository | None = None,
    ):
        super().__init__()
        self.repository = repository
        self.laboratory_repository = (
            laboratory_repository
            if laboratory_repository is not None
            else LaboratoryRepository(repository.database_path)
        )
        self.engine = MixCalculationEngine()
        self.design = self._build_default_design()
        self.current_saved_design_id: int | None = None
        self.auto_recalculate = True
        self.is_dirty = False
        self.percentage_mode = False
        self.percentage_values: dict[str, float] = {}
        self.percentage_error = ""
        self.last_result = self.engine.recalculate(self.design)

    @property
    def materials(self) -> list[Material]:
        return self.repository.list_all()

    @property
    def saved_designs(self) -> list[SavedDesignRecord]:
        return self.laboratory_repository.list_designs()

    @property
    def design_groups(self) -> list[str]:
        return self.laboratory_repository.list_design_groups()

    @property
    def productions(self) -> list[ProductionRecord]:
        return self.laboratory_repository.list_productions()

    def _build_default_design(self) -> MixDesign:
        materials = self.materials
        used_ids: set[int] = set()

        def take_material(name: str, category: MaterialCategory) -> Material | None:
            candidates = [
                material
                for material in materials
                if material.category == category and material.id not in used_ids
            ]
            exact = next(
                (material for material in candidates if material.name.casefold() == name.casefold()),
                None,
            )
            selected = exact or min(
                candidates,
                key=lambda material: (
                    not material.is_seed,
                    material.id if material.id is not None else 2**63,
                    material.name.casefold(),
                ),
                default=None,
            )
            if selected is not None and selected.id is not None:
                used_ids.add(selected.id)
            return selected

        component_specs = (
            ("Agua", MaterialCategory.WATER, 185.0, True),
            ("Cemento Portland Tipo I", MaterialCategory.CEMENTITIOUS, 296.0, False),
            ("Ceniza volante", MaterialCategory.CEMENTITIOUS, 74.0, False),
            ("Arena estándar", MaterialCategory.FINE_AGGREGATE, 700.0, False),
            ("Grava estándar", MaterialCategory.COARSE_AGGREGATE, 1050.0, False),
            ("Superplastificante", MaterialCategory.ADMIXTURE, 0.0, False),
            ("Aire", MaterialCategory.AIR, 20.0, True),
        )
        components: list[MixComponent] = []
        resolved: dict[str, MixComponent] = {}
        for name, category, quantity, locked in component_specs:
            material = take_material(name, category)
            if material is None:
                continue
            component = MixComponent(material, quantity, locked=locked)
            components.append(component)
            resolved[name] = component

        constraints: list[RatioConstraint] = []
        cement = resolved.get("Cemento Portland Tipo I")
        fly_ash = resolved.get("Ceniza volante")
        if cement is not None and fly_ash is not None:
            constraints.append(
                RatioConstraint(
                    numerator_uid=cement.uid,
                    denominator_uid=fly_ash.uid,
                    target_ratio=80.0,
                    mode=ConstraintMode.PERCENT_OF_PAIR,
                    enabled=False,
                )
            )

        return MixDesign(
            parameters=MixParameters(
                fc_mpa=28.0,
                slump_mm=100.0,
                nominal_max_size_mm=19.0,
                target_w_cm=0.50,
                w_cm_locked=True,
                target_volume_l=1000.0,
            ),
            components=components,
            ratio_constraints=constraints,
        )

    def reset_design(self) -> None:
        self.percentage_mode = False
        self.percentage_values.clear()
        self.percentage_error = ""
        self.design = self._build_default_design()
        self.current_saved_design_id = None
        self.recalculate()
        self.message.emit("Se restauró la mezcla inicial.")

    def recalculate(self, changed_uid: str | None = None) -> SolveResult:
        if self.percentage_mode:
            if self.percentage_total_is_valid:
                return self._apply_percentage_quantities()
            self.is_dirty = True
            self.design_changed.emit()
            return self.last_result
        self.last_result = self.engine.recalculate(self.design, changed_uid)
        self.is_dirty = False
        self.design_changed.emit()
        return self.last_result

    def set_auto_recalculate(self, enabled: bool) -> None:
        self.auto_recalculate = bool(enabled)
        self.calculation_mode_changed.emit()
        if enabled and self.is_dirty:
            self.recalculate()

    def _after_edit(self, changed_uid: str | None = None) -> None:
        if self.auto_recalculate:
            self.recalculate(changed_uid)
        else:
            self.is_dirty = True
            self.design_changed.emit()

    def set_quantity(self, uid: str, value: float) -> None:
        if self.percentage_mode:
            return
        component = self.design.component(uid)
        if component is None:
            return
        if uid in self.design.controlled_reasons:
            return
        component.quantity = value
        self._after_edit(changed_uid=uid)

    @property
    def percentage_total(self) -> float:
        return sum(
            self.percentage_values.get(component.uid, 0.0)
            for component in self.design.enabled_components()
            if component.category != MaterialCategory.AIR
        )

    @property
    def percentage_total_is_valid(self) -> bool:
        return abs(self.percentage_total - 100.0) <= PERCENT_TOLERANCE

    @property
    def percentage_design_is_valid(self) -> bool:
        return self.percentage_total_is_valid and not self.percentage_error

    def set_percentage_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.percentage_mode:
            return
        if enabled:
            mass_components = [
                component
                for component in self.design.enabled_components()
                if component.category != MaterialCategory.AIR
            ]
            total_mass = sum(component.quantity for component in mass_components)
            if total_mass <= 0:
                raise ValueError(
                    "No es posible derivar porcentajes porque la masa total en kg es cero."
                )
            percentages = {
                component.uid: component.quantity / total_mass * 100.0
                for component in mass_components
            }
            air_volume = sum(
                component.quantity
                for component in self.design.by_category(MaterialCategory.AIR)
            )
            quantities_from_mass_percentages(
                [
                    PercentageEntry(
                        key=component.uid,
                        percentage=percentages[component.uid],
                        specific_gravity=component.material.specific_gravity,
                    )
                    for component in mass_components
                ],
                air_volume_l=air_volume,
                target_volume_l=self.design.parameters.target_volume_l,
            )
            self.percentage_values = percentages
            self.percentage_mode = True
            self.percentage_error = ""
            self.is_dirty = False
            self.design_changed.emit()
            return

        self.percentage_mode = False
        self.percentage_values.clear()
        self.percentage_error = ""
        self.recalculate()

    def set_percentage(self, uid: str, value: float) -> None:
        if not self.percentage_mode:
            return
        component = self.design.component(uid)
        if component is None or component.category == MaterialCategory.AIR:
            return
        self.percentage_values[uid] = max(float(value), 0.0)
        if self.percentage_total_is_valid:
            self._apply_percentage_quantities()
        else:
            self.percentage_error = ""
            self.is_dirty = True
            self.design_changed.emit()

    def _apply_percentage_quantities(self) -> SolveResult:
        entries = [
            PercentageEntry(
                key=component.uid,
                percentage=self.percentage_values.get(component.uid, 0.0),
                specific_gravity=component.material.specific_gravity,
            )
            for component in self.design.enabled_components()
            if component.category != MaterialCategory.AIR
        ]
        air_volume = sum(
            component.quantity
            for component in self.design.by_category(MaterialCategory.AIR)
        )
        try:
            quantities = quantities_from_mass_percentages(
                entries,
                air_volume_l=air_volume,
                target_volume_l=self.design.parameters.target_volume_l,
            )
        except ValueError as error:
            self.percentage_error = str(error)
            self.design.warnings[:] = [str(error)]
            self.is_dirty = True
            self.last_result = SolveResult(False, 0.0, list(self.design.warnings))
            self.design_changed.emit()
            return self.last_result

        for uid, quantity in quantities.items():
            component = self.design.component(uid)
            if component is not None:
                component.quantity = quantity
        self.percentage_error = ""
        residual = self.design.parameters.target_volume_l - self.design.total_absolute_volume_l
        converged = abs(residual) <= self.engine.TOLERANCE_L
        self.design.warnings[:] = (
            []
            if converged
            else [f"El cálculo por porcentaje deja un residual de {residual:+.3f} L."]
        )
        self.last_result = SolveResult(converged, residual, list(self.design.warnings))
        self.is_dirty = False
        self.design_changed.emit()
        return self.last_result

    def replace_with_normalized_recipe(
        self, entries: list[tuple[Material, float]]
    ) -> None:
        """Replace only the active mix composition with a normalized recipe."""

        if not entries:
            raise ValueError("La receta normalizada no contiene materiales.")
        material_keys = [
            material.id if material.id is not None else id(material)
            for material, _quantity in entries
        ]
        if len(material_keys) != len(set(material_keys)):
            raise ValueError("No se puede incluir el mismo material más de una vez.")
        self.percentage_mode = False
        self.percentage_values.clear()
        self.percentage_error = ""
        self.design.components = [
            MixComponent(material=material, quantity=float(quantity), locked=False)
            for material, quantity in entries
        ]
        self.design.ratio_constraints.clear()
        self.design.parameters.w_cm_locked = False
        self.design.parameters.target_volume_l = 1000.0
        if self.design.total_cementitious_kg > 0 and self.design.water_kg >= 0:
            self.design.parameters.target_w_cm = self.design.actual_w_cm
        self.current_saved_design_id = None
        self.recalculate()
        if (
            self.design.by_category(MaterialCategory.WATER)
            and self.design.by_category(MaterialCategory.CEMENTITIOUS)
        ):
            self.design.parameters.target_w_cm = self.design.actual_w_cm
            self.design_changed.emit()

    def set_locked(self, uid: str, locked: bool) -> None:
        if self.percentage_mode:
            return
        component = self.design.component(uid)
        if component is None:
            return
        component.locked = locked
        self._after_edit()

    def update_parameters(
        self,
        *,
        fc_mpa: float | None = None,
        slump_mm: float | None = None,
        nominal_max_size_mm: float | None = None,
        target_w_cm: float | None = None,
        w_cm_locked: bool | None = None,
    ) -> None:
        params = self.design.parameters
        if fc_mpa is not None:
            params.fc_mpa = fc_mpa
        if slump_mm is not None:
            params.slump_mm = slump_mm
        if nominal_max_size_mm is not None:
            params.nominal_max_size_mm = nominal_max_size_mm
        if target_w_cm is not None and not self.percentage_mode:
            params.target_w_cm = target_w_cm
        if w_cm_locked is not None and not self.percentage_mode:
            params.w_cm_locked = w_cm_locked
        self._after_edit()

    def get_suggestion(self, air_entrained: bool) -> AciSuggestion:
        params = self.design.parameters
        return suggest_initial_values(
            params.fcr_mpa if params.fcr_mpa is not None else params.fc_mpa,
            params.slump_mm,
            params.nominal_max_size_mm,
            air_entrained,
        )

    def apply_suggestion(self, suggestion: AciSuggestion) -> None:
        params = self.design.parameters
        params.target_w_cm = suggestion.w_cm
        waters = self.design.by_category(MaterialCategory.WATER)
        if waters:
            waters[0].quantity = suggestion.water_kg_m3
        air_components = self.design.by_category(MaterialCategory.AIR)
        if air_components:
            air_components[0].quantity = suggestion.air_pct * 10.0
        self.recalculate(changed_uid=waters[0].uid if waters else None)
        self.message.emit("Se aplicó la sugerencia inicial como punto de partida.")

    def add_ratio_constraint(
        self,
        mode: ConstraintMode,
        numerator_uid: str,
        denominator_uid: str | None,
        target_value: float,
    ) -> RatioConstraint:
        if self.percentage_mode:
            raise ValueError("Las relaciones están suspendidas durante el cálculo por porcentaje.")
        if mode in {
            ConstraintMode.MASS_RATIO,
            ConstraintMode.PERCENT_OF_B,
            ConstraintMode.PERCENT_OF_PAIR,
            ConstraintMode.ML_PER_100KG_B,
        }:
            if denominator_uid is None or numerator_uid == denominator_uid:
                raise ValueError("Selecciona dos componentes diferentes.")
        constraint = RatioConstraint(
            numerator_uid=numerator_uid,
            denominator_uid=denominator_uid,
            target_ratio=max(float(target_value), 0.0),
            mode=mode,
        )
        self.design.ratio_constraints.append(constraint)
        self._after_edit()
        return constraint

    def update_ratio_constraint(self, uid: str, target_value: float, enabled: bool) -> None:
        if self.percentage_mode:
            return
        constraint = next((item for item in self.design.ratio_constraints if item.uid == uid), None)
        if constraint is None:
            return
        constraint.target_ratio = max(float(target_value), 0.0)
        constraint.enabled = bool(enabled)
        self._after_edit()

    def remove_ratio_constraint(self, uid: str) -> None:
        if self.percentage_mode:
            return
        self.design.ratio_constraints = [
            item for item in self.design.ratio_constraints if item.uid != uid
        ]
        self._after_edit()

    def add_component(self, material: Material) -> MixComponent:
        if self.percentage_mode:
            raise ValueError("Desactiva el cálculo por porcentaje para cambiar los componentes.")
        if material.category == MaterialCategory.AIR and self.design.by_category(MaterialCategory.AIR):
            raise ValueError("La mezcla ya tiene un componente de aire.")
        quantity = 0.0
        component = MixComponent(material=material, quantity=quantity)
        self.design.components.append(component)
        self.recalculate()
        return component

    def remove_component(self, uid: str) -> None:
        if self.percentage_mode:
            return
        self.design.components = [component for component in self.design.components if component.uid != uid]
        self.design.ratio_constraints = [
            constraint
            for constraint in self.design.ratio_constraints
            if constraint.numerator_uid != uid and constraint.denominator_uid != uid
        ]
        self.recalculate()

    def save_material(self, material: Material) -> Material:
        saved = self.repository.save(material)
        for component in self.design.components:
            if component.material.id == saved.id:
                component.material = saved
        self.materials_changed.emit()
        self.recalculate()
        return saved

    def get_material_characterization(
        self, material_id: int | None
    ) -> MaterialCharacterization:
        if material_id is None:
            return MaterialCharacterization()
        return self.repository.get_characterization(material_id)

    def save_material_with_characterization(
        self,
        material: Material,
        characterization: MaterialCharacterization,
    ) -> Material:
        saved, _ = self.repository.save_with_characterization(
            material, characterization
        )
        for component in self.design.components:
            if component.material.id == saved.id:
                component.material = saved
        self.materials_changed.emit()
        self.recalculate()
        self.message.emit(f"Material '{saved.name}' y su caracterización fueron guardados.")
        return saved

    def delete_material(self, material_id: int) -> None:
        if any(component.material.id == material_id for component in self.design.components):
            raise ValueError("No se puede eliminar un material usado en la mezcla actual.")
        self.repository.delete(material_id)
        self.materials_changed.emit()

    # ------------------------------------------------------------------
    # Existing JSON import/export remains available for portability.
    # ------------------------------------------------------------------
    def save_design(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.design.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.message.emit(f"Diseño guardado en {path.name}.")

    def load_design(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.percentage_mode = False
        self.percentage_values.clear()
        self.percentage_error = ""
        self.design = MixDesign.from_dict(payload)
        self.current_saved_design_id = None
        self.recalculate()
        self.message.emit(f"Diseño cargado desde {path.name}.")

    # ------------------------------------------------------------------
    # Internal saved-design library and grouping.
    # ------------------------------------------------------------------
    def create_design_group(self, name: str) -> str:
        group_name = self.laboratory_repository.create_design_group(name)
        self.library_changed.emit()
        self.message.emit(f"Grupo '{group_name}' disponible para nuevos diseños.")
        return group_name

    def get_design_specification(self, design_id: int) -> DesignSpecification:
        return self.laboratory_repository.get_design_specification(design_id)

    def save_current_design_to_library(
        self,
        name: str,
        description: str = "",
        group_name: str = "",
        specification: DesignSpecification | None = None,
    ) -> SavedDesignRecord:
        """Save the active calculation as an independent library record.

        Designs can be organised under an optional group name. The former
        automatic-revision behaviour is intentionally not used because it was
        ambiguous for operators and required loading a source record first.
        """
        if self.percentage_mode and not self.percentage_design_is_valid:
            raise ValueError("Los porcentajes deben sumar 100 % antes de guardar el diseño.")
        if self.is_dirty:
            self.recalculate()
        record = self.laboratory_repository.create_design(
            name=name,
            group_name=group_name,
            description=description,
            design=self.design,
            source_design_id=None,
            specification=(
                specification
                if specification is not None
                else DesignSpecification.from_mix_design(self.design)
            ),
        )
        self.current_saved_design_id = record.id
        self.library_changed.emit()
        group_text = f" en el grupo '{record.group_name}'" if record.group_name else ""
        self.message.emit(f"Diseño '{record.name}' guardado{group_text}.")
        return record

    def load_design_from_library(self, design_id: int) -> None:
        record = self.laboratory_repository.get_design(design_id)
        if record is None:
            raise ValueError("El diseño seleccionado no existe.")
        self.percentage_mode = False
        self.percentage_values.clear()
        self.percentage_error = ""
        self.design = self.laboratory_repository.load_mix_design(design_id)
        self.current_saved_design_id = design_id
        self.recalculate()
        self.message.emit(
            f"Se cargó '{record.name}' en el Laboratorio."
        )

    def archive_saved_design(self, design_id: int) -> None:
        self.laboratory_repository.archive_design(design_id, True)
        if self.current_saved_design_id == design_id:
            self.current_saved_design_id = None
        self.library_changed.emit()
        self.message.emit("Diseño archivado; su historial de producción se conservó.")

    # ------------------------------------------------------------------
    # Production and laboratory records.
    # ------------------------------------------------------------------
    def create_production(
        self,
        *,
        design_id: int,
        produced_at: datetime,
        batch_code: str,
        batch_volume_m3: float,
        notes: str,
        schedules: list[tuple[SpecimenType, float, int]],
        batch_moistures: dict[str, float] | None = None,
    ) -> ProductionRecord:
        production = self.laboratory_repository.create_production(
            design_id=design_id,
            produced_at=produced_at,
            batch_code=batch_code,
            batch_volume_m3=batch_volume_m3,
            notes=notes,
            schedules=schedules,
            batch_moistures=batch_moistures,
        )
        self.productions_changed.emit()
        self.library_changed.emit()
        self.message.emit(f"Producción '{production.batch_code}' registrada.")
        return production

    def add_specimen_schedule(
        self,
        *,
        production_id: int,
        specimen_type: SpecimenType,
        target_age_days: float,
        count: int,
    ) -> None:
        self.laboratory_repository.add_specimen_schedule(
            production_id=production_id,
            specimen_type=specimen_type,
            target_age_days=target_age_days,
            count=count,
        )
        self.productions_changed.emit()
        self.message.emit("Muestras añadidas a la programación.")

    def add_fresh_test(
        self,
        *,
        production_id: int,
        test_type: FreshTestType,
        measured_at: datetime,
        slump_mm: float | None,
        spread_d1_mm: float | None,
        spread_d2_mm: float | None,
        concrete_temperature_c: float | None,
        air_content_pct: float | None,
        unit_weight_kg_m3: float | None,
        notes: str,
    ) -> None:
        self.laboratory_repository.add_fresh_test(
            production_id=production_id,
            test_type=test_type,
            measured_at=measured_at,
            slump_mm=slump_mm,
            spread_d1_mm=spread_d1_mm,
            spread_d2_mm=spread_d2_mm,
            concrete_temperature_c=concrete_temperature_c,
            air_content_pct=air_content_pct,
            unit_weight_kg_m3=unit_weight_kg_m3,
            notes=notes,
        )
        self.productions_changed.emit()
        self.message.emit("Dato de concreto fresco guardado.")

    def update_fresh_test(self, *, test_id: int, **values) -> None:
        self.laboratory_repository.update_fresh_test(test_id=test_id, **values)
        self.productions_changed.emit()
        self.message.emit("Dato de concreto fresco actualizado.")

    def delete_fresh_test(self, test_id: int) -> None:
        self.laboratory_repository.delete_fresh_test(test_id)
        self.productions_changed.emit()
        self.message.emit("Dato de concreto fresco eliminado.")

    def record_compression_result(self, *, specimen_id: int, **values) -> None:
        self.laboratory_repository.upsert_compression_result(
            specimen_id=specimen_id, **values
        )
        self.productions_changed.emit()
        self.library_changed.emit()
        self.message.emit("Resultado de compresión guardado.")

    def record_flexural_result(self, *, specimen_id: int, **values) -> None:
        self.laboratory_repository.upsert_flexural_result(
            specimen_id=specimen_id, **values
        )
        self.productions_changed.emit()
        self.library_changed.emit()
        self.message.emit("Resultado de módulo de rotura guardado.")

    def delete_specimen_result(self, specimen_id: int) -> bool:
        deleted = self.laboratory_repository.delete_specimen_result(specimen_id)
        if deleted:
            self.productions_changed.emit()
            self.library_changed.emit()
            self.message.emit("Resultado de resistencia eliminado.")
        return deleted

    def set_specimen_status(self, specimen_id: int, status: SpecimenStatus) -> None:
        self.laboratory_repository.set_specimen_status(specimen_id, status)
        self.productions_changed.emit()
