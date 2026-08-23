from __future__ import annotations

from PySide6.QtWidgets import QApplication

from civillab_suite.registry import ModuleStatus, create_default_registry
from civillab_suite.ui.shell import SuiteWindow


def test_default_registry_centralizes_availability_and_assets():
    registry = create_default_registry()
    modules = {module.id: module for module in registry.all()}

    assert tuple(modules) == ("concretos", "prefabricados", "suelos")
    assert registry.is_enabled("concretos")
    assert registry.is_enabled("prefabricados")
    assert not registry.is_enabled("suelos")
    assert modules["suelos"].status is ModuleStatus.NOT_IMPLEMENTED
    assert all(module.logo_path.is_file() for module in modules.values())


def test_shell_renders_three_official_logos_and_disables_suelos(qapp):
    window = SuiteWindow(create_default_registry())

    assert QApplication.instance() is qapp
    assert set(window.cards) == {"concretos", "prefabricados", "suelos"}
    assert all(card.logo_label.pixmap() is not None for card in window.cards.values())
    assert window.cards["concretos"].open_button.isEnabled()
    assert window.cards["prefabricados"].open_button.isEnabled()
    assert not window.cards["suelos"].open_button.isEnabled()
    assert window.cards["suelos"].status_label.text() == "PRÓXIMAMENTE"

    window.close()
