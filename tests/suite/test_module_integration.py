from __future__ import annotations

from PySide6.QtWidgets import QApplication


def test_module_factories_reuse_the_suite_qapplication(qapp, monkeypatch, tmp_path):
    from concrete_mix_designer import config as concrete_config
    from civillab_suite.modules.concretos.adapter import create_window as create_concretos
    from civillab_suite.modules.prefabricados.adapter import create_window as create_prefabricados
    from precon_lab import database as prefabricados_database

    monkeypatch.setattr(concrete_config, "DATABASE_PATH", tmp_path / "concretos.sqlite3")
    monkeypatch.setenv("PRECON_LAB_DATA_DIR", str(tmp_path / "prefabricados"))
    prefabricados_database._engine = None
    prefabricados_database._SessionFactory = None

    returned: list[str] = []
    concretos = create_concretos(lambda: returned.append("concretos"))
    prefabricados = create_prefabricados(lambda: returned.append("prefabricados"))

    assert QApplication.instance() is qapp
    assert any(action.text() == "Volver a CivilLab Suite" for action in concretos.menuBar().actions()[0].menu().actions())
    assert any(action.text() == "Volver a CivilLab Suite" for action in prefabricados.menuBar().actions()[0].menu().actions())

    concretos.show()
    concretos.close()
    prefabricados.show()
    prefabricados.close()
    qapp.processEvents()

    assert returned == ["concretos", "prefabricados"]
    assert QApplication.instance() is qapp
