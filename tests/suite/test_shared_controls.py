from __future__ import annotations

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QPushButton,
    QScrollArea,
    QStyle,
    QTableWidget,
    QWidget,
)


def test_shared_control_assets_and_concrete_stylesheet_are_stable():
    from civillab_suite.ui.shared_controls import (
        SHARED_BUTTON_CONTRAST_STYLESHEET,
        SHARED_CONTROL_ASSETS_DIR,
        SHARED_CONTROLS_STYLESHEET,
    )
    from concrete_mix_designer.ui.styles import APP_STYLESHEET
    from precon_lab.ui.styles import APP_STYLESHEET as PRECON_APP_STYLESHEET

    for name in (
        "check.svg",
        "chevron_down.svg",
        "chevron_up.svg",
        "chevron_left.svg",
        "chevron_right.svg",
    ):
        assert (SHARED_CONTROL_ASSETS_DIR / name).is_file()
    assert "assets/chevron_" not in APP_STYLESHEET
    assert "checkmark_blue.svg" not in APP_STYLESHEET
    assert SHARED_CONTROL_ASSETS_DIR.as_posix() in SHARED_CONTROLS_STYLESHEET
    assert "QCheckBox::indicator:checked" in SHARED_CONTROLS_STYLESHEET
    assert "width: 17px" in SHARED_CONTROLS_STYLESHEET
    assert "QPushButton#Danger" in SHARED_BUTTON_CONTRAST_STYLESHEET
    assert APP_STYLESHEET.endswith(SHARED_BUTTON_CONTRAST_STYLESHEET)
    assert PRECON_APP_STYLESHEET.endswith(SHARED_BUTTON_CONTRAST_STYLESHEET)


def test_shared_combo_tuning_is_idempotent_and_handles_late_combos(qapp):
    from civillab_suite.ui.shared_controls import (
        install_shared_control_tuning,
        tune_shared_controls,
    )

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


def test_light_palette_and_embedded_widget_row_height_are_explicit(qapp):
    from civillab_suite.ui.shared_controls import (
        apply_light_surface_palette,
        ensure_table_row_height,
    )

    root = QWidget()
    apply_light_surface_palette(root)
    assert root.palette().color(QPalette.ColorRole.Base).name() == "#ffffff"

    table = QTableWidget(1, 1)
    button = QPushButton("Acción")
    table.setCellWidget(0, 0, button)
    height = ensure_table_row_height(table, 0, vertical_padding=8)
    assert height >= button.sizeHint().height() + 8
    assert table.rowHeight(0) == height


def test_late_dialog_inherits_registered_light_surface_palette(qapp):
    from civillab_suite.ui.shared_controls import tune_shared_controls

    root = QWidget()
    tune_shared_controls(root, light_surfaces=True)
    dialog = QDialog(root)
    area = QScrollArea(dialog)
    dialog.show()
    qapp.processEvents()

    assert dialog.palette().color(QPalette.ColorRole.Base).name() == "#ffffff"
    assert area.viewport().palette().color(QPalette.ColorRole.Base).name() == "#ffffff"
    dialog.close()


def test_spinbox_without_focus_ignores_wheel(qapp):
    from civillab_suite.ui.shared_controls import ExplicitFocusDoubleSpinBox

    class WheelStub:
        ignored = False

        def ignore(self):
            self.ignored = True

    spin = ExplicitFocusDoubleSpinBox()
    spin.setValue(5.0)
    event = WheelStub()
    spin.wheelEvent(event)

    assert event.ignored
    assert spin.value() == 5.0


def test_module_button_contrast_survives_generic_widget_color(qapp):
    from concrete_mix_designer.ui.styles import APP_STYLESHEET

    root = QWidget()
    root.setStyleSheet(APP_STYLESHEET)
    primary = QPushButton("Primario", root)
    danger = QPushButton("Peligro", root)
    danger.setObjectName("Danger")
    secondary = QPushButton("Secundario", root)
    secondary.setObjectName("Secondary")
    table_action = QPushButton("Acción", root)
    table_action.setObjectName("TableAction")
    root.show()
    qapp.processEvents()

    assert primary.palette().color(QPalette.ColorRole.ButtonText).name() == "#ffffff"
    assert danger.palette().color(QPalette.ColorRole.ButtonText).name() == "#ffffff"
    assert secondary.palette().color(QPalette.ColorRole.ButtonText).name() == "#24415e"
    assert table_action.palette().color(QPalette.ColorRole.ButtonText).name() == "#24415e"
    root.close()
