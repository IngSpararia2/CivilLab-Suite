from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from civillab_suite.core.catalog import CatalogService
from civillab_suite.core.database import CoreDatabase
from civillab_suite.core.pie import PieService
from civillab_suite.core.pie_scheduling import PieScheduleProvider
from civillab_suite.core.scheduling import CompositeScheduleService, NavigationTarget
from civillab_suite.registry import ModuleRegistry, ModuleStatus


@dataclass(slots=True)
class SuiteContext:
    database: CoreDatabase
    registry: ModuleRegistry
    catalog: CatalogService
    pie: PieService
    scheduling: CompositeScheduleService
    navigate: Callable[[NavigationTarget], None]

    @property
    def available_modules(self) -> dict[str, str]:
        return {
            module.id: module.name
            for module in self.registry.all()
            if module.status is ModuleStatus.AVAILABLE and self.registry.is_enabled(module.id)
        }


def build_suite_context(
    database: CoreDatabase,
    registry: ModuleRegistry,
    navigate: Callable[[NavigationTarget], None],
) -> SuiteContext:
    from civillab_suite.modules.concretos.scheduling import ConcretosScheduleProvider
    from civillab_suite.modules.prefabricados.scheduling import PrefabricadosScheduleProvider
    from concrete_mix_designer.data.calendar_repository import CalendarRepository

    catalog = CatalogService(database)
    pie = PieService(database)
    providers = [PieScheduleProvider(pie)]
    if registry.is_enabled("concretos"):
        providers.append(ConcretosScheduleProvider(CalendarRepository(database.path)))
    if registry.is_enabled("prefabricados"):
        providers.append(PrefabricadosScheduleProvider())
    return SuiteContext(
        database=database,
        registry=registry,
        catalog=catalog,
        pie=pie,
        scheduling=CompositeScheduleService(providers),
        navigate=navigate,
    )
