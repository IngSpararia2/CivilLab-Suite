from __future__ import annotations

from PySide6.QtWidgets import QApplication

from civillab_suite.tools import TOOLS
from civillab_suite.ui.tools_page import SharedToolsPage


def test_module_factories_reuse_the_suite_qapplication(qapp, monkeypatch, tmp_path):
    from civillab_suite.modules.concretos.adapter import create_window as create_concretos
    from civillab_suite.modules.prefabricados.adapter import create_window as create_prefabricados
    from concrete_mix_designer import config as concrete_config
    from precon_lab import database as prefabricados_database

    monkeypatch.setattr(concrete_config, "DATABASE_PATH", tmp_path / "concretos.sqlite3")
    monkeypatch.setenv("PRECON_LAB_DATA_DIR", str(tmp_path / "prefabricados"))
    prefabricados_database._engine = None
    prefabricados_database._SessionFactory = None

    returned: list[str] = []
    concretos = create_concretos(lambda: returned.append("concretos"))
    prefabricados = create_prefabricados(lambda: returned.append("prefabricados"))

    assert QApplication.instance() is qapp
    assert type(concretos.tools_page) is type(prefabricados.tools_page) is SharedToolsPage
    assert concretos.tools_page.tools is prefabricados.tools_page.tools is TOOLS
    assert concretos.tools_page is not prefabricados.tools_page
    assert dict(prefabricados.pages)["Herramientas"] is prefabricados.tools_page
    assert any(action.text() == "Volver a CivilLab Suite" for action in concretos.menuBar().actions()[0].menu().actions())
    assert any(action.text() == "Volver a CivilLab Suite" for action in prefabricados.menuBar().actions()[0].menu().actions())

    concretos.show()
    concretos.close()
    prefabricados.show()
    prefabricados.close()
    qapp.processEvents()

    # Direct launch uses the same implementation even without adapter injection.
    from concrete_mix_designer.ui.main_window import MainWindow as ConcreteWindow
    from precon_lab.ui.main_window import MainWindow as PrefabricatedWindow

    direct_concrete = ConcreteWindow(concretos.state)
    direct_prefabricated = PrefabricatedWindow()
    assert type(direct_concrete.tools_page) is SharedToolsPage
    assert type(direct_prefabricated.tools_page) is SharedToolsPage
    assert direct_concrete.tools_page.tools is direct_prefabricated.tools_page.tools is TOOLS
    direct_concrete.close()
    direct_prefabricated.close()

    assert returned == ["concretos", "prefabricados"]
    assert QApplication.instance() is qapp
