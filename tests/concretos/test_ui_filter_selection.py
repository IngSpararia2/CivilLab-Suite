from __future__ import annotations

import os
from datetime import datetime


def test_filter_signals_preserve_selected_record_id(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from concrete_mix_designer.data.database import MaterialRepository
    from concrete_mix_designer.data.laboratory_repository import LaboratoryRepository
    from concrete_mix_designer.services.app_state import AppState
    from concrete_mix_designer.ui.pages.design_library_page import DesignLibraryPage
    from concrete_mix_designer.ui.pages.production_page import ProductionPage

    database = tmp_path / "filters.sqlite3"
    state = AppState(MaterialRepository(database), LaboratoryRepository(database))
    first_design = state.save_current_design_to_library("Diseño 1")
    selected_design = state.save_current_design_to_library("Diseño 2")
    state.create_production(
        design_id=first_design.id,
        produced_at=datetime(2026, 8, 1, 8, 0),
        batch_code="PROD-1",
        batch_volume_m3=1.0,
        notes="",
        schedules=[],
    )
    selected_production = state.create_production(
        design_id=selected_design.id,
        produced_at=datetime(2026, 8, 1, 9, 0),
        batch_code="PROD-2",
        batch_volume_m3=1.0,
        notes="",
        schedules=[],
    )

    app = QApplication.instance() or QApplication([])
    library_page = DesignLibraryPage(state)
    production_page = ProductionPage(state)

    for row in range(library_page.table.rowCount()):
        if library_page.table.item(row, 1).data(Qt.UserRole) == selected_design.id:
            library_page.table.selectRow(row)
            break
    for row in range(production_page.production_table.rowCount()):
        if (
            production_page.production_table.item(row, 0).data(Qt.UserRole)
            == selected_production.id
        ):
            production_page.production_table.selectRow(row)
            break

    assert library_page.selected_design_id() == selected_design.id
    assert production_page.selected_production_id() == selected_production.id

    # The emitted value is 1.0, equal to the first database ID. It must be
    # discarded as a Qt signal payload instead of being mistaken for selected_id.
    library_page.min_strength.setValue(1.0)
    production_page.min_strength.setValue(1.0)
    app.processEvents()

    assert library_page.selected_design_id() == selected_design.id
    assert production_page.selected_production_id() == selected_production.id

    library_page.close()
    production_page.close()
