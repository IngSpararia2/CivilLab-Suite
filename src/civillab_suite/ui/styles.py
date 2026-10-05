TOOLS_STYLESHEET = """
QWidget#SharedToolsPage, QWidget#SharedToolsPage QWidget {
    font-family: "Segoe UI"; font-size: 13px;
}
QWidget#SharedToolsPage, QWidget#ToolsCatalogContent {
    background: #f4f7fb; color: #1f2937; font-size: 13px;
}
QScrollArea#ToolsCatalog { background: #f4f7fb; border: none; }
QScrollArea#ToolsCatalog QScrollBar:vertical {
    background: #edf2f7; width: 12px; margin: 0;
}
QScrollArea#ToolsCatalog QScrollBar::handle:vertical {
    background: #a9b7c6; border-radius: 6px; min-height: 24px;
}
QScrollArea#ToolsCatalog QScrollBar::handle:vertical:hover { background: #7891a8; }
QScrollArea#ToolsCatalog QScrollBar::add-line:vertical,
QScrollArea#ToolsCatalog QScrollBar::sub-line:vertical {
    width: 0; height: 0; border: none; image: none; background: transparent;
}
QScrollArea#ToolsCatalog QScrollBar::add-page:vertical,
QScrollArea#ToolsCatalog QScrollBar::sub-page:vertical { background: transparent; }
QToolButton#ToolTile {
    background: #ffffff; color: #24415e; border: 1px solid #cbd6e2;
    border-radius: 24px; padding: 0; font-weight: 600;
}
QToolButton#ToolTile:hover { background: #eaf3fc; border-color: #1769aa; }
QToolButton#ToolTile:pressed { background: #d8e5f2; border-color: #12588f; }
QToolButton#ToolTile:focus { border: 2px solid #f5a000; }
QToolButton#ToolTile QLabel { background: transparent; color: #24415e; font-size: 13px; }
QTabWidget#ToolsTabs::pane {
    background: #f4f7fb; border: 1px solid #cbd6e2; border-radius: 8px;
}
QTabWidget#ToolsTabs QTabBar::tab {
    background: #e7eef6; color: #24415e; border: 1px solid #cbd6e2;
    padding: 9px 13px; margin-right: 3px;
}
QTabWidget#ToolsTabs QTabBar::tab:selected { background: #ffffff; color: #1769aa; }
QTabWidget#ToolsTabs QTabBar::tab:hover { background: #d8e5f2; }
"""


SHELL_STYLESHEET = """
QMainWindow#SuiteWindow, QWidget#SuiteCentral {
    background: #07111f;
    color: #e6edf7;
}
QFrame#HeroPanel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0d1d32, stop:0.55 #102943, stop:1 #0b1a2c);
    border: 1px solid #24415e;
    border-radius: 22px;
}
QLabel#SuiteEyebrow {
    color: #65c7ff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#SuiteTitle {
    color: #ffffff;
    font-size: 34px;
    font-weight: 800;
}
QLabel#SuiteSubtitle {
    color: #a9bbcf;
    font-size: 15px;
}
QFrame#ModuleCard {
    background: #0e1b2c;
    border: 1px solid #263c54;
    border-radius: 20px;
}
QFrame#ModuleCard:hover {
    background: #112238;
    border-color: #3e668b;
}
QLabel#ModuleLogo {
    background: transparent;
}
QLabel#ModuleName {
    color: #ffffff;
    font-size: 21px;
    font-weight: 750;
}
QLabel#ModuleDescription {
    color: #aebed0;
    font-size: 13px;
}
QLabel#StatusAvailable {
    color: #8ff0be;
    background: #123e31;
    border: 1px solid #247759;
    border-radius: 9px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#StatusSoon {
    color: #a9c9f8;
    background: #163255;
    border: 1px solid #285b94;
    border-radius: 9px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 700;
}
QPushButton#OpenModuleButton {
    color: #07111f;
    background: #f5f8fc;
    border: none;
    border-radius: 10px;
    padding: 11px 16px;
    font-size: 13px;
    font-weight: 750;
}
QPushButton#OpenModuleButton:hover {
    background: #dcecff;
}
QPushButton#OpenModuleButton:pressed {
    background: #bddcff;
}
QPushButton#OpenModuleButton:disabled {
    color: #73859a;
    background: #1a293b;
    border: 1px solid #2b4058;
}
QStatusBar {
    color: #8ea3ba;
    background: #07111f;
}
QMenuBar, QMenu {
    color: #dce8f5;
    background: #0d1a2a;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #1d3a57;
}
"""
