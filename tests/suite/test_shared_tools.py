from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QTabBar, QWidget
from shiboken6 import isValid

from civillab_suite.tools import TOOLS, ToolDescriptor, create_tool_widget
from civillab_suite.ui.tools_page import SharedToolsPage


def test_tool_registry_and_shared_assets(qapp):
    assert {tool.id for tool in TOOLS} == {
        "granulometry", "sand_equivalent", "fractured_faces", "flakiness_index",
        "elongation_index", "atterberg_limits", "moisture_content", "proctor", "cbr",
        "unit_weight_voids", "specific_gravity_fine", "specific_gravity_coarse",
        "los_angeles_abrasion",
    }
    assert len(TOOLS) == len({tool.id for tool in TOOLS}) == 13
    for tool in TOOLS:
        assert tool.name
        assert tool.factory is None
        assert tool.icon_path.is_file()
        assert QSvgRenderer(str(tool.icon_path)).isValid()
        assert not QIcon(str(tool.icon_path)).pixmap(72, 72).isNull()


def test_launcher_opens_deduplicates_closes_and_reopens_every_tool(qapp):
    page = SharedToolsPage()
    page.resize(1000, 700)
    page.show()
    qapp.processEvents()
    assert page.tools is TOOLS
    assert set(page.launchers) == {tool.id for tool in TOOLS}
    assert page._columns == 4
    assert page.tabs.currentWidget() is page.catalog
    for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
        assert page.tabs.tabBar().tabButton(0, side) is None
    page.tabs.tabCloseRequested.emit(0)
    assert page.tabs.count() == 1

    for tool in TOOLS:
        button = page.launchers[tool.id]
        assert button.accessibleName() == button.toolTip() == tool.name
        button.click()
        widget = page.tabs.currentWidget()
        assert page.tabs.count() == 2
        assert page.tabs.tabText(1) == tool.name
        assert type(widget) is QWidget
        assert widget.layout() is None
        assert widget.findChildren(QWidget) == []
        page.tabs.setCurrentIndex(0)
        button.click()
        assert page.tabs.count() == 2
        assert page.tabs.currentWidget() is widget
        page.tabs.tabCloseRequested.emit(1)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not isValid(widget)
        assert page.tabs.count() == 1
        button.click()
        assert page.tabs.count() == 2
        page.close_tool(1)

    page.resize(520, 700)
    qapp.processEvents()
    assert page._columns == 2
    assert page.catalog.verticalScrollBar().maximum() > 0
    assert page.catalog.horizontalScrollBar().maximum() == 0
    page.close()


def test_keyboard_activation_and_catalog_on_reentry(qapp):
    page = SharedToolsPage()
    page.show()
    button = page.launchers[TOOLS[0].id]
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert page.tabs.count() == 2
    page.hide()
    page.show()
    assert page.tabs.currentWidget() is page.catalog
    assert page.tabs.count() == 2
    page.close()


def test_distinct_tool_tabs_survive_index_changes(qapp):
    page = SharedToolsPage()
    for tool in TOOLS[:3]:
        page.open_tool(tool.id)
    retained = page.tabs.currentWidget()
    page.close_tool(1)
    page.open_tool(TOOLS[2].id)
    assert page.tabs.currentWidget() is retained
    assert page.tabs.count() == 3
    page.open_tool(TOOLS[0].id)
    assert page.tabs.count() == 4
    page.close()


def test_factory_can_be_connected_without_a_host_module(qapp):
    parents = []

    def factory(parent):
        parents.append(parent)
        widget = QWidget(parent)
        widget.setObjectName("FutureMiniapp")
        return widget

    descriptor = ToolDescriptor("future_tool", "Herramienta futura", TOOLS[0].icon, factory)
    page = SharedToolsPage((descriptor,))
    page.open_tool(descriptor.id)
    widget = page.tabs.currentWidget()
    assert widget.objectName() == "FutureMiniapp"
    assert page.tabs.isAncestorOf(widget)
    page.open_tool(descriptor.id)
    assert parents == [page.tabs]
    page.close_tool(1)
    page.open_tool(descriptor.id)
    assert len(parents) == 2
    other_parent = QWidget()
    placeholder = create_tool_widget(TOOLS[0], other_parent)
    assert placeholder.parentWidget() is other_parent
    with pytest.raises(ValueError, match="únicos"):
        SharedToolsPage((descriptor, descriptor))
    page.close()
