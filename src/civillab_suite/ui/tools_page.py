"""Shared launcher and internal miniapp navigation for every laboratory."""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from civillab_suite.tools import TOOLS, ToolDescriptor, create_tool_widget
from civillab_suite.ui.styles import TOOLS_STYLESHEET


class SharedToolsPage(QWidget):
    TILE_SIZE = 188
    SPACING = 16

    def __init__(self, tools: Sequence[ToolDescriptor] = TOOLS, parent=None):
        super().__init__(parent)
        self.setObjectName("SharedToolsPage")
        self.setStyleSheet(TOOLS_STYLESHEET)
        self.tools = tools
        self._descriptors = {tool.id: tool for tool in tools}
        if len(self._descriptors) != len(tools):
            raise ValueError("Los identificadores de herramientas deben ser únicos.")
        self._open_tools: dict[str, QWidget] = {}
        self.launchers: dict[str, QToolButton] = {}

        self.tabs = QTabWidget()
        self.tabs.setObjectName("ToolsTabs")
        self.tabs.setTabsClosable(True)
        self.tabs.setAccessibleName("Pestañas de herramientas")
        self.tabs.tabCloseRequested.connect(self.close_tool)

        self.catalog = QScrollArea()
        self.catalog.setObjectName("ToolsCatalog")
        self.catalog.setWidgetResizable(True)
        self.catalog.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.catalog.setAccessibleName("Catálogo de herramientas")
        content = QWidget()
        content.setObjectName("ToolsCatalogContent")
        self.grid = QGridLayout(content)
        self.grid.setContentsMargins(20, 20, 20, 20)
        self.grid.setSpacing(self.SPACING)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        for tool in tools:
            tile = QToolButton()
            tile.setObjectName("ToolTile")
            tile.setFixedSize(self.TILE_SIZE, self.TILE_SIZE)
            tile.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            tile.setToolTip(tool.name)
            tile.setAccessibleName(tool.name)
            # Child labels allow long names to wrap without eliding their text.
            icon = QLabel()
            icon.setPixmap(QIcon(str(tool.icon_path)).pixmap(QSize(72, 72)))
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name = QLabel(tool.name)
            name.setWordWrap(True)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            for label in (icon, name):
                label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(12, 14, 12, 14)
            tile_layout.addStretch()
            tile_layout.addWidget(icon)
            tile_layout.addWidget(name)
            tile_layout.addStretch()
            tile.clicked.connect(partial(self.open_tool, tool.id))
            self.launchers[tool.id] = tile
        self.catalog.setWidget(content)
        self.catalog.viewport().installEventFilter(self)
        self._columns = 0
        self._arrange_tiles(4)
        self.tabs.addTab(self.catalog, "Herramientas")
        for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
            self.tabs.tabBar().setTabButton(0, side, None)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(self.tabs)

    def _arrange_tiles(self, columns: int) -> None:
        if columns == self._columns:
            return
        self._columns = columns
        for index, tile in enumerate(self.launchers.values()):
            self.grid.addWidget(tile, index // columns, index % columns)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.catalog.viewport() and event.type() == QEvent.Type.Resize:
            width = self.catalog.viewport().width() - 40
            columns = max(1, min(4, (width + self.SPACING) // (self.TILE_SIZE + self.SPACING)))
            self._arrange_tiles(columns)
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:  # noqa: N802
        self.tabs.setCurrentWidget(self.catalog)
        super().showEvent(event)

    def open_tool(self, tool_id: str) -> None:
        tool = self._descriptors[tool_id]
        widget = self._open_tools.get(tool_id)
        if widget is None:
            widget = create_tool_widget(tool, self.tabs)
            self.tabs.addTab(widget, QIcon(str(tool.icon_path)), tool.name)
            self._open_tools[tool_id] = widget
        self.tabs.setCurrentWidget(widget)

    def close_tool(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is None or widget is self.catalog:
            return
        tool_id = next(key for key, value in self._open_tools.items() if value is widget)
        del self._open_tools[tool_id]
        self.tabs.removeTab(index)
        widget.deleteLater()
