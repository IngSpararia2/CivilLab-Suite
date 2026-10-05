"""Host-independent tool catalog and construction entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from civillab_suite.config import ASSETS_DIR

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ToolDescriptor:
    id: str
    name: str
    icon: str
    factory: Callable[[QWidget], QWidget] | None = None

    @property
    def icon_path(self) -> Path:
        return ASSETS_DIR / "shared" / "tools" / self.icon


TOOLS = (
    ToolDescriptor("granulometry", "Granulometría", "granulometry.svg"),
    ToolDescriptor("sand_equivalent", "Equivalente de arena", "sand_equivalent.svg"),
    ToolDescriptor("fractured_faces", "Caras fracturadas", "fractured_faces.svg"),
    ToolDescriptor("flakiness_index", "Índice de aplanamiento", "flakiness_index.svg"),
    ToolDescriptor("elongation_index", "Índice de alargamiento", "elongation_index.svg"),
    ToolDescriptor("atterberg_limits", "Límites de Atterberg / Índice de plasticidad", "atterberg_limits.svg"),
    ToolDescriptor("moisture_content", "Contenido de humedad", "moisture_content.svg"),
    ToolDescriptor("proctor", "Proctor", "proctor.svg"),
    ToolDescriptor("cbr", "CBR", "cbr.svg"),
    ToolDescriptor("unit_weight_voids", "Masa unitaria y vacíos", "unit_weight_voids.svg"),
    ToolDescriptor("specific_gravity_fine", "Gravedad específica y absorción — agregado fino", "specific_gravity_fine.svg"),
    ToolDescriptor("specific_gravity_coarse", "Gravedad específica y absorción — agregado grueso", "specific_gravity_coarse.svg"),
    ToolDescriptor("los_angeles_abrasion", "Desgaste Los Ángeles", "los_angeles_abrasion.svg"),
)


def create_tool_widget(tool: ToolDescriptor, parent: QWidget) -> QWidget:
    """Build a fresh miniapp (or an empty placeholder) owned by the caller."""
    from PySide6.QtWidgets import QWidget

    widget = tool.factory(parent) if tool.factory is not None else QWidget(parent)
    widget.setParent(parent)
    return widget
