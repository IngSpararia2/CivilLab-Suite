"""Sistema visual compartido por toda la interfaz de Prefabricados Lab."""

from civillab_suite.ui.shared_controls import (
    SHARED_CONTROL_ASSETS_DIR,
    SHARED_CONTROLS_STYLESHEET,
)

APP_STYLESHEET = SHARED_CONTROLS_STYLESHEET + """
QMainWindow, QDialog {
    background: #f4f7fb;
}
QWidget {
    color: #1f2937;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QWidget:disabled { color: #8493a3; }

QWidget#ProcedurePopup {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #8fa5ba;
    border-radius: 12px;
}
QLabel#ProcedureTitle {
    color: #0b467f;
    font-size: 14pt;
    font-weight: 700;
}
QLabel#ProcedureMetadata {
    color: #2f587a;
    font-size: 10.5pt;
    line-height: 1.25em;
}
QScrollArea#ProcedureScroll {
    background: #f8fbff;
    border: 1px solid #d1dfec;
    border-radius: 8px;
}
QLabel#ProcedureDetail {
    background: #f8fbff;
    color: #1f2937;
    padding: 10px;
    selection-background-color: #1769aa;
    selection-color: #ffffff;
}

QFrame#AppSidebar {
    background: #12355b;
    border: none;
    border-right: 3px solid #f5a000;
}
QFrame#AppSidebar QLabel {
    background: transparent;
    color: white;
}
QLabel#AppLogo {
    background: #ffffff;
    border: 1px solid #5e7892;
    border-radius: 10px;
    padding: 2px;
}
QLabel#SidebarBrandTitle {
    color: white;
    font-size: 14pt;
    font-weight: 700;
    padding-top: 2px;
}
QLabel#SidebarVersion {
    color: #c9d8e6;
    font-size: 9pt;
    padding-bottom: 3px;
}
QToolButton#SidebarToggle {
    background: #274d72;
    color: white;
    border: 1px solid #5e7892;
    border-radius: 7px;
    font-size: 18pt;
    font-weight: 700;
    padding: 2px;
}
QToolButton#SidebarToggle:hover {
    background: #315d85;
    border-color: #86a0b8;
}
QToolButton#SidebarToggle:pressed { background: #0b2948; }
QPushButton#SidebarNavButton {
    background: transparent;
    color: #e4edf5;
    border: 1px solid transparent;
    border-radius: 7px;
    min-height: 24px;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
}
QPushButton#SidebarNavButton:hover {
    background: #274d72;
    border-color: #416887;
}
QPushButton#SidebarNavButton:checked {
    background: #f5a000;
    color: #102f4f;
    border-color: #ffc14b;
}
QPushButton#SidebarNavButton:focus {
    border-color: white;
}

QFrame#PageHeader {
    background: white;
    border: none;
    border-bottom: 1px solid #dce3ec;
}
QLabel#CurrentSection {
    color: #12355b;
    font-size: 19pt;
    font-weight: 700;
}
QLabel#CurrentSectionHint {
    color: #526579;
    font-size: 9.5pt;
}
QLabel#pageTitle, QLabel#Title {
    color: #12355b;
    font-size: 21pt;
    font-weight: 700;
    margin-bottom: 8px;
}
QLabel#SectionTitle {
    color: #12355b;
    font-size: 14pt;
    font-weight: 700;
}
QLabel#Subtitle { color: #526579; font-size: 10.5pt; }

QFrame#Card, QFrame#MetricCard {
    background: white;
    border: 1px solid #dce3ec;
    border-radius: 12px;
}
QFrame#MetricCard QLabel#MetricValue {
    color: #0b6e4f;
    font-size: 23pt;
    font-weight: 700;
}
QFrame#MetricCard QLabel#MetricTitle {
    color: #526579;
    font-size: 10pt;
    font-weight: 600;
}
QLabel#InfoBanner {
    background: #eef5fc;
    color: #24415e;
    border: 1px solid #c5d9ec;
    border-radius: 8px;
    padding: 10px;
}
QLabel#WarningBanner {
    background: #fff6e6;
    color: #704500;
    border: 1px solid #f2c078;
    border-radius: 7px;
    padding: 9px;
}

QGroupBox {
    background: white;
    border: 1px solid #dce3ec;
    border-radius: 9px;
    font-weight: 700;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #12355b;
}

QPushButton#TableAction, QToolButton#TableAction {
    background: #e7eef6;
    color: #24415e;
    border: 1px solid #cbd6e2;
    border-radius: 6px;
    min-height: 18px;
    min-width: 0;
    padding: 3px 7px;
    font-weight: 600;
}
QScrollArea#HistoricalResultsScroll {
    background: white;
    border: 1px solid #dce3ec;
    border-radius: 6px;
}
QScrollArea#HistoricalResultsScroll QWidget#qt_scrollarea_viewport,
QScrollArea#HistoricalResultsScroll QWidget#HistoricalResultsContent {
    background: white;
}
QLabel#HistoricalEmptyState {
    color: #526579;
    background: #f8fbff;
    border: 1px dashed #c5d9ec;
    border-radius: 7px;
    padding: 14px;
}
QPushButton#TableAction:hover, QToolButton#TableAction:hover {
    background: #d8e5f2;
    border-color: #9fb2c6;
}
QPushButton#TableAction:focus, QToolButton#TableAction:focus { border-color: #f5a000; }


QTableView, QTableWidget, QListView, QListWidget, QTreeView {
    background: white;
    alternate-background-color: #f7f9fc;
    border: 1px solid #dce3ec;
    border-radius: 6px;
    gridline-color: #e5ebf2;
    selection-background-color: #dceafb;
    selection-color: #12355b;
    outline: none;
}
QTableView::item, QTableWidget::item { padding: 5px; border: none; }
QTableView::item:hover, QTableWidget::item:hover, QListWidget::item:hover {
    background: #eef5fc;
}
QTableView::item:selected, QTableWidget::item:selected, QListWidget::item:selected {
    background: #d5e7f8;
    color: #12355b;
}
QListWidget::item { padding: 8px; border-radius: 5px; }
QHeaderView::section {
    background: #eaf0f7;
    color: #24415e;
    border: none;
    border-bottom: 1px solid #cbd6e2;
    border-right: 1px solid #dce3ec;
    padding: 7px 8px;
    font-weight: 700;
    min-height: 30px;
}
QHeaderView::section:hover { background: #dce8f4; }
QTableView QHeaderView, QTableWidget QHeaderView {
    background: #eaf0f7;
}
QTableView QHeaderView::section:vertical, QTableWidget QHeaderView::section:vertical {
    background: #eaf0f7;
    border-right: 1px solid #dce3ec;
}
QTableCornerButton::section {
    background: #eaf0f7;
    border: none;
    border-bottom: 1px solid #cbd6e2;
    border-right: 1px solid #dce3ec;
}

QTabWidget::pane {
    border: 1px solid #dce3ec;
    border-radius: 6px;
    background: white;
}
QTabBar::tab {
    background: #eaf0f7;
    color: #24415e;
    border: 1px solid #dce3ec;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 9px 14px;
    margin-right: 2px;
}
QTabBar::tab:hover { background: #dce8f4; }
QTabBar::tab:selected {
    background: #1769aa;
    color: white;
    border-color: #1769aa;
}

QMenuBar { background: #0b2948; color: white; padding: 2px 8px; }
QMenuBar::item { background: transparent; border-radius: 4px; padding: 5px 10px; }
QMenuBar::item:selected { background: #274d72; }
QMenu { background: white; border: 1px solid #cbd6e2; padding: 5px; }
QMenu::item { border-radius: 4px; padding: 7px 28px 7px 10px; }
QMenu::item:selected { background: #dceafb; color: #12355b; }
QStatusBar { background: #12355b; color: white; border-top: 1px solid #31587b; }
QStatusBar::item { border: none; }
QStatusBar QLabel { background: transparent; color: white; }
QLabel#CopyrightCredit {
    background: #0b2948;
    color: white;
    border: 1px solid #31587b;
    border-radius: 5px;
    font-weight: 600;
    padding: 3px 10px;
    margin: 2px 4px;
}
QScrollBar:vertical {
    background: #edf2f7;
    width: 16px;
    margin: 16px 0 16px 0;
}
QScrollBar:horizontal {
    background: #edf2f7;
    height: 16px;
    margin: 0 16px 0 16px;
}
QScrollBar::handle {
    background: #aebdca;
    border-radius: 5px;
    min-height: 28px;
    min-width: 28px;
}
QScrollBar::handle:hover { background: #8499ab; }
QScrollBar::sub-line:vertical {
    background: #dfe8f1;
    border: 1px solid #c0cedc;
    subcontrol-origin: margin;
    subcontrol-position: top;
    height: 16px;
    image: url("__ASSETS__/chevron_up.svg");
}
QScrollBar::add-line:vertical {
    background: #dfe8f1;
    border: 1px solid #c0cedc;
    subcontrol-origin: margin;
    subcontrol-position: bottom;
    height: 16px;
    image: url("__ASSETS__/chevron_down.svg");
}
QScrollBar::sub-line:horizontal {
    background: #dfe8f1;
    border: 1px solid #c0cedc;
    subcontrol-origin: margin;
    subcontrol-position: left;
    width: 16px;
    image: url("__ASSETS__/chevron_left.svg");
}
QScrollBar::add-line:horizontal {
    background: #dfe8f1;
    border: 1px solid #c0cedc;
    subcontrol-origin: margin;
    subcontrol-position: right;
    width: 16px;
    image: url("__ASSETS__/chevron_right.svg");
}
QScrollBar::add-line:hover, QScrollBar::sub-line:hover { background: #cbd9e6; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
""".replace("__ASSETS__", SHARED_CONTROL_ASSETS_DIR.as_posix())
