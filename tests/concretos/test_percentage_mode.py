from __future__ import annotations

import os

import pytest

from concrete_mix_designer.data.database import MaterialRepository
from concrete_mix_designer.domain.mix_normalization import RecipeEntry, normalize_observed_recipe
from concrete_mix_designer.domain.models import MaterialCategory
from concrete_mix_designer.services.app_state import AppState


def test_percentage_mode_preserves_constraints_and_locks(tmp_path):
    state = AppState(MaterialRepository(tmp_path / "percentage.sqlite3"))
    constraints = list(state.design.ratio_constraints)
    locks = {component.uid: component.locked for component in state.design.components}
    quantities = {component.uid: component.quantity for component in state.design.components}

    state.set_percentage_mode(True)

    assert state.percentage_mode
    assert state.percentage_total == pytest.approx(100.0)
    assert state.design.ratio_constraints == constraints
    assert {component.uid: component.locked for component in state.design.components} == locks
    assert {component.uid: component.quantity for component in state.design.components} == quantities

    editable = next(
        component
        for component in state.design.components
        if component.category != MaterialCategory.AIR
    )
    before = {component.uid: component.quantity for component in state.design.components}
    state.set_percentage(editable.uid, state.percentage_values[editable.uid] - 1.0)
    assert not state.percentage_total_is_valid
    assert {component.uid: component.quantity for component in state.design.components} == before

    state.set_percentage(editable.uid, state.percentage_values[editable.uid] + 1.0)
    assert state.percentage_total_is_valid
    assert state.design.total_absolute_volume_l == pytest.approx(1000.0)

    state.set_percentage_mode(False)
    assert not state.percentage_mode
    assert state.design.ratio_constraints == constraints
    assert {component.uid: component.locked for component in state.design.components} == locks


def test_apply_inverse_recipe_replaces_composition_and_rules(tmp_path):
    state = AppState(MaterialRepository(tmp_path / "inverse.sqlite3"))
    chosen = [
        component.material
        for component in state.design.components
        if component.category in {
            MaterialCategory.WATER,
            MaterialCategory.CEMENTITIOUS,
            MaterialCategory.FINE_AGGREGATE,
        }
    ][:3]
    observed = [3.85, 4.50, 9.0]
    result = normalize_observed_recipe(
        [
            RecipeEntry(
                str(material.id),
                quantity,
                material.specific_gravity,
                material.category == MaterialCategory.AIR,
            )
            for material, quantity in zip(chosen, observed, strict=True)
        ]
    )
    state.set_percentage_mode(True)

    state.replace_with_normalized_recipe(
        [(material, result.quantities[str(material.id)]) for material in chosen]
    )

    assert not state.percentage_mode
    assert [component.material.id for component in state.design.components] == [
        material.id for material in chosen
    ]
    assert not state.design.ratio_constraints
    assert not state.design.parameters.w_cm_locked
    assert all(not component.locked for component in state.design.components)
    assert state.design.total_absolute_volume_l == pytest.approx(1000.0, abs=0.02)
    if state.design.total_cementitious_kg:
        assert state.design.parameters.target_w_cm == pytest.approx(state.design.actual_w_cm)


def test_percentage_ui_column_and_editability(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from concrete_mix_designer.ui.dialogs.inverse_mix_calculator_dialog import (
        InverseMixCalculatorDialog,
    )
    from concrete_mix_designer.ui.pages.workspace_page import WorkspacePage

    app = QApplication.instance() or QApplication([])
    state = AppState(MaterialRepository(tmp_path / "percentage-ui.sqlite3"))
    page = WorkspacePage(state)
    assert page.table.isColumnHidden(2)
    assert page.table.columnWidth(4) >= 130
    target = page.constraints_table.cellWidget(0, 4)
    delete = page.constraints_table.cellWidget(0, 6)
    assert target.minimumHeight() == delete.minimumHeight()
    assert target.maximumHeight() == delete.maximumHeight()

    state.set_percentage_mode(True)
    app.processEvents()
    assert not page.table.isColumnHidden(2)
    air_row = next(
        row
        for row, component in enumerate(state.design.components)
        if component.category == MaterialCategory.AIR
    )
    assert not page.table.item(air_row, 2).flags() & Qt.ItemFlag.ItemIsEditable
    assert not page.table.item(0, 4).flags() & Qt.ItemFlag.ItemIsEditable
    assert page.percentage_total_label.text().startswith("Σ ")

    dialog = InverseMixCalculatorDialog(
        state.materials,
        [component.material for component in state.design.components],
    )
    assert not dialog.apply_button.isEnabled()
    dialog.close()
    page.close()
