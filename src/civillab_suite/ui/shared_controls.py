"""Neutral visual primitives shared by the CivilLab laboratory modules."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QProxyStyle, QStyle, QTableView, QWidget

from civillab_suite.config import ASSETS_DIR


SHARED_CONTROL_ASSETS_DIR = ASSETS_DIR / "shared"


class ComboBoxDropDownStyle(QProxyStyle):
    """Keep a combo field visible while its non-native popup is open."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.StyleHint.SH_ComboBox_Popup:
            return 0
        return super().styleHint(hint, option, widget, returnData)


class ComboBoxTuning(QObject):
    """Applies the shared popup ergonomics to existing and future combos."""

    MAX_VISIBLE_ROWS = 8
    _REGISTERED_PROPERTY = "_civillab_shared_combo_tuned"

    def register_descendants(self, root: QWidget) -> None:
        if isinstance(root, QComboBox):
            self.register(root)
        for combo in root.findChildren(QComboBox):
            self.register(combo)

    def register(self, combo: QComboBox) -> None:
        if combo.property(self._REGISTERED_PROPERTY):
            return
        combo.setMaxVisibleItems(self.MAX_VISIBLE_ROWS)
        view = combo.view()
        view.setVerticalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        combo.setProperty(self._REGISTERED_PROPERTY, True)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget):
            self.register_descendants(watched)
        return super().eventFilter(watched, event)


def install_shared_control_tuning() -> ComboBoxTuning | None:
    """Install global combo behavior once for the current QApplication."""

    app = QApplication.instance()
    if app is None:
        return None

    if getattr(app, "_civillab_shared_combo_style", None) is None:
        style = ComboBoxDropDownStyle(app.style())
        style.setParent(app)
        app.setStyle(style)
        app._civillab_shared_combo_style = style

    tuning = getattr(app, "_civillab_shared_combo_tuning", None)
    if tuning is None:
        tuning = ComboBoxTuning(app)
        app.installEventFilter(tuning)
        app._civillab_shared_combo_tuning = tuning
    return tuning


def tune_shared_controls(root: QWidget) -> None:
    """Configure controls already present in a module window or dialog."""

    tuning = install_shared_control_tuning()
    if tuning is not None:
        tuning.register_descendants(root)


SHARED_CONTROLS_STYLESHEET = """
QPushButton {
    background: #1769aa;
    color: white;
    border: 1px solid #1769aa;
    border-radius: 7px;
    min-height: 20px;
    padding: 7px 13px;
    font-weight: 600;
}
QPushButton:hover { background: #12588f; border-color: #12588f; }
QPushButton:pressed { background: #0d4775; border-color: #0d4775; }
QPushButton:focus { border-color: #f5a000; }
QPushButton:disabled { background: #a9b7c6; border-color: #a9b7c6; color: #eef3f7; }
QPushButton#Secondary { background: #e7eef6; color: #24415e; border-color: #cbd6e2; }
QPushButton#Secondary:hover { background: #d8e5f2; border-color: #9fb2c6; }
QPushButton#Secondary:pressed { background: #c8d9e9; }
QPushButton#Secondary:disabled { background: #edf1f5; border-color: #d7dfe7; color: #94a2b0; }
QPushButton#Danger { background: #b42318; border-color: #b42318; }
QPushButton#Danger:hover { background: #921f16; border-color: #921f16; }
QPushButton#Danger:pressed { background: #74180f; border-color: #74180f; }
QPushButton#Danger:disabled { background: #d6aaa6; border-color: #d6aaa6; }

QLineEdit, QDoubleSpinBox, QComboBox, QSpinBox, QTextBrowser,
QPlainTextEdit, QTextEdit, QDateEdit, QTimeEdit, QDateTimeEdit {
    background: white;
    border: 1px solid #bcc9d6;
    border-radius: 6px;
    min-height: 20px;
    padding: 5px 7px;
    selection-background-color: #1769aa;
    selection-color: white;
}
QLineEdit:hover, QDoubleSpinBox:hover, QComboBox:hover, QSpinBox:hover,
QPlainTextEdit:hover, QTextEdit:hover, QDateEdit:hover, QTimeEdit:hover,
QDateTimeEdit:hover { border-color: #8fa5ba; }
QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus, QSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus, QDateEdit:focus, QTimeEdit:focus,
QDateTimeEdit:focus { border-color: #1769aa; }
QComboBox::drop-down, QDateEdit::drop-down, QDateTimeEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    background: #edf2f7;
    border: none;
    border-left: 1px solid #bcc9d6;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    width: 26px;
}
QComboBox::drop-down:hover, QDateEdit::drop-down:hover, QDateTimeEdit::drop-down:hover { background: #d8e5f2; }
QComboBox::down-arrow, QDateEdit::down-arrow, QDateTimeEdit::down-arrow {
    image: url("__ASSETS__/chevron_down.svg"); width: 12px; height: 8px;
}
QComboBox QAbstractItemView {
    background: white; border: 1px solid #bcc9d6; selection-background-color: #dceafb;
    selection-color: #12355b; outline: none;
}
QComboBox QAbstractItemView::item { padding: 6px 9px; }
QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected { background: #dceafb; color: #12355b; }

QSpinBox::up-button, QDoubleSpinBox::up-button, QDateEdit::up-button,
QTimeEdit::up-button, QDateTimeEdit::up-button {
    subcontrol-origin: border; subcontrol-position: top right; background: #edf2f7;
    border: none; border-left: 1px solid #bcc9d6; border-top-right-radius: 5px;
    width: 24px; height: 15px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button, QDateEdit::down-button,
QTimeEdit::down-button, QDateTimeEdit::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right; background: #edf2f7;
    border: none; border-top: 1px solid #d7e0e9; border-left: 1px solid #bcc9d6;
    border-bottom-right-radius: 5px; width: 24px; height: 15px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QDateEdit::up-button:hover,
QTimeEdit::up-button:hover, QDateTimeEdit::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::down-button:hover, QDateEdit::down-button:hover, QTimeEdit::down-button:hover,
QDateTimeEdit::down-button:hover { background: #d8e5f2; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateEdit::up-arrow,
QTimeEdit::up-arrow, QDateTimeEdit::up-arrow { image: url("__ASSETS__/chevron_up.svg"); width: 10px; height: 7px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateEdit::down-arrow,
QTimeEdit::down-arrow, QDateTimeEdit::down-arrow { image: url("__ASSETS__/chevron_down.svg"); width: 10px; height: 7px; }

QCalendarWidget QWidget#qt_calendar_navigationbar { background: #eaf0f7; border-bottom: 1px solid #cbd6e2; }
QCalendarWidget QToolButton#qt_calendar_prevmonth, QCalendarWidget QToolButton#qt_calendar_nextmonth {
    background: #e7eef6; border: 1px solid #9fb2c6; border-radius: 5px;
    min-width: 30px; min-height: 26px; padding: 2px;
}
QCalendarWidget QToolButton#qt_calendar_prevmonth:hover, QCalendarWidget QToolButton#qt_calendar_nextmonth:hover { background: #d8e5f2; border-color: #6f8ca6; }
QCalendarWidget QToolButton#qt_calendar_prevmonth { image: url("__ASSETS__/chevron_left.svg"); }
QCalendarWidget QToolButton#qt_calendar_nextmonth { image: url("__ASSETS__/chevron_right.svg"); }
QCalendarWidget QToolButton#qt_calendar_monthbutton, QCalendarWidget QToolButton#qt_calendar_yearbutton { color: #12355b; background: transparent; border: none; font-weight: 700; }

QCheckBox { spacing: 7px; }
""".replace("__ASSETS__", SHARED_CONTROL_ASSETS_DIR.as_posix())
