from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QStyle, QWidget


def test_shared_control_assets_and_concrete_stylesheet_are_stable():
    from civillab_suite.ui.shared_controls import (
        SHARED_CONTROL_ASSETS_DIR,
        SHARED_CONTROLS_STYLESHEET,
    )
    from concrete_mix_designer.ui.styles import APP_STYLESHEET

    for name in ("chevron_down.svg", "chevron_up.svg", "chevron_left.svg", "chevron_right.svg"):
        assert (SHARED_CONTROL_ASSETS_DIR / name).is_file()
    assert "assets/chevron_" not in APP_STYLESHEET
    assert "checkmark_blue.svg" not in APP_STYLESHEET
    assert SHARED_CONTROL_ASSETS_DIR.as_posix() in SHARED_CONTROLS_STYLESHEET


def test_shared_combo_tuning_is_idempotent_and_handles_late_combos(qapp):
    from civillab_suite.ui.shared_controls import install_shared_control_tuning, tune_shared_controls

    first = install_shared_control_tuning()
    second = install_shared_control_tuning()

    assert first is second
    assert qapp.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup) == 0

    root = QWidget()
    tune_shared_controls(root)
    combo = QComboBox(root)
    combo.addItems([str(index) for index in range(12)])
    root.show()
    qapp.processEvents()

    assert combo.property("_civillab_shared_combo_tuned") is True
    assert combo.maxVisibleItems() == 8
    assert combo.view().verticalScrollBarPolicy().name == "ScrollBarAsNeeded"
    assert combo.view().horizontalScrollBarPolicy().name == "ScrollBarAlwaysOff"

    root.close()
