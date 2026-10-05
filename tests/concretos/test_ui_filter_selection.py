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


def test_workspace_disables_only_active_relation_numerator(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from civillab_suite.ui.shared_controls import ExplicitFocusDoubleSpinBox
    from concrete_mix_designer.data.database import MaterialRepository
    from concrete_mix_designer.services.app_state import AppState
    from concrete_mix_designer.ui.pages.workspace_page import WorkspacePage

    state = AppState(MaterialRepository(tmp_path / "workspace.sqlite3"))
    state.design.parameters.w_cm_locked = False  # Isolate the custom-relation control.
    constraint = state.design.ratio_constraints[0]
    state.update_ratio_constraint(constraint.uid, constraint.target_ratio, True)
    app = QApplication.instance() or QApplication([])
    page = WorkspacePage(state)

    def quantity_item(uid: str):
        for row in range(page.table.rowCount()):
            if page.table.item(row, 1).data(Qt.ItemDataRole.UserRole) == uid:
                return page.table.item(row, 4)
        raise AssertionError("component row not found")

    assert not quantity_item(constraint.numerator_uid).flags() & Qt.ItemFlag.ItemIsEditable
    assert quantity_item(constraint.denominator_uid).flags() & Qt.ItemFlag.ItemIsEditable
    controlled_row = next(
        row
        for row in range(page.table.rowCount())
        if page.table.item(row, 1).data(Qt.ItemDataRole.UserRole) == constraint.numerator_uid
    )
    page._start_quantity_edit(controlled_row, 4)
    app.processEvents()
    assert not page.table.findChildren(ExplicitFocusDoubleSpinBox)

    state.update_ratio_constraint(constraint.uid, constraint.target_ratio, False)
    app.processEvents()
    assert quantity_item(constraint.numerator_uid).flags() & Qt.ItemFlag.ItemIsEditable
    page.close()


def test_workspace_quantity_editor_is_temporary_and_commits_once(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))

    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtWidgets import QApplication

    from civillab_suite.ui.shared_controls import ExplicitFocusDoubleSpinBox
    from concrete_mix_designer.data.database import MaterialRepository
    from concrete_mix_designer.services.app_state import AppState
    from concrete_mix_designer.ui.pages.workspace_page import WorkspacePage

    state = AppState(MaterialRepository(tmp_path / "delegate.sqlite3"))
    app = QApplication.instance() or QApplication([])
    page = WorkspacePage(state)
    row = 0
    uid = page.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
    changes: list[None] = []
    state.design_changed.connect(lambda: changes.append(None))

    assert page.table.cellWidget(row, 4) is None
    page._start_quantity_edit(row, 4)
    app.processEvents()
    editors = page.table.findChildren(ExplicitFocusDoubleSpinBox)
    assert len(editors) == 1

    editors[0].setValue(222.0)
    editors[0].editingFinished.emit()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()

    assert state.design.component(uid).quantity == 222.0
    assert len(changes) == 1
    assert page.table.cellWidget(row, 4) is None
    assert not page.table.findChildren(ExplicitFocusDoubleSpinBox)
    page.close()
