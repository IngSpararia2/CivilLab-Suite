from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from pathlib import Path
from typing import Callable

from .config import SUITE_ASSETS_DIR
from .licensing import LicensePolicy, StaticLicensePolicy


class ModuleStatus(StrEnum):
    AVAILABLE = "available"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True, slots=True)
class ModuleDescriptor:
    id: str
    name: str
    description: str
    logo_path: Path
    status: ModuleStatus
    license_key: str
    entrypoint: str | None
    accent_color: str

    def load_entrypoint(self) -> Callable:
        if self.entrypoint is None:
            raise RuntimeError(f"El módulo {self.name} todavía no tiene punto de entrada.")
        module_name, function_name = self.entrypoint.split(":", maxsplit=1)
        return getattr(import_module(module_name), function_name)


class ModuleRegistry:
    def __init__(
        self,
        modules: tuple[ModuleDescriptor, ...],
        license_policy: LicensePolicy,
    ) -> None:
        self._modules = {module.id: module for module in modules}
        self.license_policy = license_policy

    def all(self) -> tuple[ModuleDescriptor, ...]:
        return tuple(self._modules.values())

    def get(self, module_id: str) -> ModuleDescriptor:
        try:
            return self._modules[module_id]
        except KeyError as error:
            raise KeyError(f"Módulo desconocido: {module_id}") from error

    def is_enabled(self, module_id: str) -> bool:
        module = self.get(module_id)
        return (
            module.status is ModuleStatus.AVAILABLE
            and self.license_policy.is_enabled(module.license_key)
        )


def create_default_registry(
    license_policy: LicensePolicy | None = None,
) -> ModuleRegistry:
    modules = (
        ModuleDescriptor(
            id="concretos",
            name="Concretos Lab",
            description="Diseño de mezclas, materiales, producción y control de ensayos.",
            logo_path=SUITE_ASSETS_DIR / "concretos_lab.png",
            status=ModuleStatus.AVAILABLE,
            license_key="concretos",
            entrypoint="civillab_suite.modules.concretos.adapter:create_window",
            accent_color="#f59e0b",
        ),
        ModuleDescriptor(
            id="prefabricados",
            name="Prefabricados Lab",
            description="Producción, muestreo, PIE, itinerarios, resultados e históricos.",
            logo_path=SUITE_ASSETS_DIR / "prefabricados_lab.png",
            status=ModuleStatus.AVAILABLE,
            license_key="prefabricados",
            entrypoint="civillab_suite.modules.prefabricados.adapter:create_window",
            accent_color="#14b8a6",
        ),
        ModuleDescriptor(
            id="suelos",
            name="Suelos Lab",
            description="Módulo reservado para el futuro desarrollo geotécnico.",
            logo_path=SUITE_ASSETS_DIR / "suelos_lab.png",
            status=ModuleStatus.NOT_IMPLEMENTED,
            license_key="suelos",
            entrypoint="civillab_suite.modules.suelos.adapter:create_window",
            accent_color="#2196f3",
        ),
    )
    return ModuleRegistry(modules, license_policy or StaticLicensePolicy())
