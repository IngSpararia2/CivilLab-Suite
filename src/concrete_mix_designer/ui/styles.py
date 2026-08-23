APP_STYLESHEET = """
QMainWindow, QDialog {
    background: #f4f7fb;
}
QWidget {
    color: #1f2937;
    font-size: 10pt;
}
QWidget:disabled {
    color: #8493a3;
}
QFrame#AppHeader {
    background: #12355b;
    border-bottom: 3px solid #f5a000;
}
QFrame#AppHeader QLabel {
    background: transparent;
    color: white;
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
    border: 1px solid #5e7892;
    border-radius: 9px;
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
QToolButton#SidebarToggle:pressed {
    background: #0b2948;
}
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
    border: 2px solid white;
    padding: 7px 11px;
}
QLabel#AppBrandTitle {
    font-size: 16pt;
    font-weight: 700;
}
QLabel#AppBrandSubtitle {
    color: #d7e3ef;
    font-size: 9.5pt;
}
QLabel#VersionBadge {
    background: #274d72;
    color: #f8fbff;
    border: 1px solid #5e7892;
    border-radius: 10px;
    padding: 4px 10px;
    font-weight: 600;
}
QMenuBar {
    background: #0b2948;
    color: white;
    padding: 2px 8px;
}
QMenuBar::item {
    background: transparent;
    border-radius: 4px;
    padding: 5px 10px;
}
QMenuBar::item:selected {
    background: #274d72;
}
QMenu {
    background: white;
    border: 1px solid #cbd6e2;
    padding: 5px;
}
QMenu::item {
    border-radius: 4px;
    padding: 7px 28px 7px 10px;
}
QMenu::item:selected {
    background: #dceafb;
    color: #12355b;
}
QMenu::separator {
    background: #dce3ec;
    height: 1px;
    margin: 5px 8px;
}
QFrame#Card {
    background: white;
    border: 1px solid #dce3ec;
    border-radius: 12px;
}
QGroupBox {
    background: white;
    border: 1px solid #dce3ec;
    border-radius: 9px;
    font-weight: 700;
    margin-top: 12px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #12355b;
}
QLabel#Title {
    font-size: 21pt;
    font-weight: 700;
    color: #12355b;
}
QLabel#SectionTitle {
    font-size: 14pt;
    font-weight: 700;
    color: #12355b;
}
QLabel#Subtitle {
    font-size: 10.5pt;
    color: #526579;
}
QLabel#Metric {
    font-size: 18pt;
    font-weight: 700;
    color: #0b6e4f;
}
QLabel#WarningBanner {
    background: #fff6e6;
    color: #704500;
    border: 1px solid #f2c078;
    border-radius: 7px;
    padding: 9px;
}
QLabel#StatusPill {
    background: #fff1cc;
    color: #704500;
    border: 1px solid #e4bc59;
    border-radius: 9px;
    padding: 3px 8px;
    font-size: 9pt;
    font-weight: 600;
}
QPushButton {
    background: #1769aa;
    color: white;
    border: 1px solid #1769aa;
    border-radius: 7px;
    min-height: 20px;
    padding: 7px 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: #12588f;
    border-color: #12588f;
}
QPushButton:pressed {
    background: #0d4775;
    border-color: #0d4775;
}
QPushButton:focus {
    border: 2px solid #f5a000;
    padding: 6px 12px;
}
QPushButton:disabled {
    background: #a9b7c6;
    border-color: #a9b7c6;
    color: #eef3f7;
}
QPushButton#Secondary {
    background: #e7eef6;
    color: #24415e;
    border-color: #cbd6e2;
}
QPushButton#Secondary:hover {
    background: #d8e5f2;
    border-color: #9fb2c6;
}
QPushButton#Secondary:pressed {
    background: #c8d9e9;
}
QPushButton#Secondary:disabled {
    background: #edf1f5;
    border-color: #d7dfe7;
    color: #94a2b0;
}
QPushButton#Danger {
    background: #b42318;
    border-color: #b42318;
}
QPushButton#Danger:hover {
    background: #921f16;
    border-color: #921f16;
}
QPushButton#Danger:pressed {
    background: #74180f;
    border-color: #74180f;
}
QPushButton#Danger:disabled {
    background: #d6aaa6;
    border-color: #d6aaa6;
}
QToolButton {
    background: #e7eef6;
    color: #24415e;
    border: 1px solid #cbd6e2;
    border-radius: 5px;
    padding: 4px 7px;
}
QToolButton:hover {
    background: #d8e5f2;
    border-color: #9fb2c6;
}
QToolButton:checked {
    background: #d5eadf;
    color: #0b6e4f;
    border-color: #80b89f;
}
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
QDateTimeEdit:hover {
    border-color: #8fa5ba;
}
QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus, QSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus, QDateEdit:focus, QTimeEdit:focus,
QDateTimeEdit:focus {
    border: 2px solid #1769aa;
    padding: 4px 6px;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    background: #edf2f7;
    border: none;
    border-left: 1px solid #bcc9d6;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    width: 26px;
}
QComboBox::drop-down:hover {
    background: #d8e5f2;
}
QComboBox::down-arrow {
    image: url(assets/chevron_down.svg);
    width: 12px;
    height: 8px;
}
QDateEdit::drop-down, QDateTimeEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    background: #edf2f7;
    border: none;
    border-left: 1px solid #bcc9d6;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    width: 26px;
}
QDateEdit::drop-down:hover, QDateTimeEdit::drop-down:hover {
    background: #d8e5f2;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QDateEdit::up-button, QTimeEdit::up-button, QDateTimeEdit::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    background: #edf2f7;
    border: none;
    border-left: 1px solid #bcc9d6;
    border-top-right-radius: 5px;
    width: 24px;
    height: 15px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button,
QDateEdit::down-button, QTimeEdit::down-button, QDateTimeEdit::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    background: #edf2f7;
    border: none;
    border-top: 1px solid #d7e0e9;
    border-left: 1px solid #bcc9d6;
    border-bottom-right-radius: 5px;
    width: 24px;
    height: 15px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QDateEdit::up-button:hover, QTimeEdit::up-button:hover, QDateTimeEdit::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover,
QDateEdit::down-button:hover, QTimeEdit::down-button:hover, QDateTimeEdit::down-button:hover {
    background: #d8e5f2;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QDateEdit::up-arrow, QTimeEdit::up-arrow, QDateTimeEdit::up-arrow {
    image: url(assets/chevron_up.svg);
    width: 10px;
    height: 7px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow,
QDateEdit::down-arrow, QTimeEdit::down-arrow, QDateTimeEdit::down-arrow {
    image: url(assets/chevron_down.svg);
    width: 10px;
    height: 7px;
}
QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {
    background: #e7eef6;
    border: 1px solid #9fb2c6;
    border-radius: 5px;
    min-width: 28px;
    min-height: 24px;
    padding: 2px;
}
QCalendarWidget QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget QToolButton#qt_calendar_nextmonth:hover {
    background: #d8e5f2;
    border-color: #6f8ca6;
}
QCalendarWidget QToolButton#qt_calendar_prevmonth {
    image: url(assets/chevron_left.svg);
}
QCalendarWidget QToolButton#qt_calendar_nextmonth {
    image: url(assets/chevron_right.svg);
}
QComboBox QAbstractItemView {
    background: white;
    border: 1px solid #bcc9d6;
    min-width: 240px;
    selection-background-color: #dceafb;
    selection-color: #12355b;
    outline: none;
}
QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 5px 10px;
}
QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected {
    background: #dceafb;
    color: #12355b;
}
QTableView, QListView, QTreeView {
    background: white;
    alternate-background-color: #f7f9fc;
    border: 1px solid #dce3ec;
    border-radius: 6px;
    gridline-color: #e5ebf2;
    selection-background-color: #dceafb;
    selection-color: #12355b;
    outline: none;
}
QTableView::item {
    padding: 5px;
    border: none;
}
QTableView::item:hover {
    background: #eef5fc;
}
QTableView::item:selected {
    background: #d5e7f8;
    color: #12355b;
}
QHeaderView::section {
    background: #eaf0f7;
    color: #24415e;
    border: none;
    border-bottom: 1px solid #cbd6e2;
    border-right: 1px solid #dce3ec;
    padding: 7px 8px;
    font-weight: 700;
}
QTableCornerButton::section {
    background: #eaf0f7;
    border: none;
    border-bottom: 1px solid #cbd6e2;
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
QTabBar::tab:hover {
    background: #dce8f4;
}
QTabBar::tab:selected {
    background: #1769aa;
    color: white;
    border-color: #1769aa;
}
QTabWidget#MainNavigation::pane {
    background: #f4f7fb;
    border: none;
    border-radius: 0;
}
QTabBar#MainTabBar {
    background: white;
}
QTabBar#MainTabBar::tab {
    background: white;
    color: #526579;
    border: none;
    border-bottom: 3px solid transparent;
    border-radius: 0;
    margin: 0;
    padding: 9px 14px 8px 14px;
    font-weight: 600;
}
QTabBar#MainTabBar::tab:hover {
    background: #eef4fb;
    color: #12355b;
}
QTabBar#MainTabBar::tab:selected {
    background: white;
    color: #12355b;
    border-bottom-color: #f5a000;
}
QCheckBox { spacing: 7px; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background: #e1e7ed;
    border: 1px solid #aebdca;
    border-radius: 4px;
}
QCheckBox::indicator:hover {
    background: #d5dee7;
    border-color: #8499ab;
}
QCheckBox::indicator:checked {
    background: #455563;
    border-color: #344454;
    image: url(assets/checkmark_blue.svg);
}
QCheckBox::indicator:checked:hover {
    background: #3c4b58;
    border-color: #24415e;
}
QSplitter::handle {
    background: #dce3ec;
}
QSplitter::handle:hover {
    background: #9fb2c6;
}
QSplitter::handle:horizontal {
    width: 5px;
    margin: 4px 2px;
}
QSplitter::handle:vertical {
    height: 5px;
    margin: 2px 4px;
}
QScrollBar:vertical {
    background: #edf2f7;
    width: 12px;
    margin: 0;
}
QScrollBar:horizontal {
    background: #edf2f7;
    height: 12px;
    margin: 0;
}
QScrollBar::handle {
    background: #aebdca;
    border-radius: 5px;
    min-height: 28px;
    min-width: 28px;
}
QScrollBar::handle:hover {
    background: #8499ab;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QToolTip {
    background: #12355b;
    color: white;
    border: 1px solid #31587b;
    border-radius: 4px;
    padding: 5px;
}
QStatusBar {
    background: #12355b;
    color: white;
    border-top: 1px solid #31587b;
}
QStatusBar::item { border: none; }
QStatusBar QLabel {
    background: transparent;
    color: white;
}
QLabel#CopyrightCredit {
    background: #0b2948;
    color: #ffffff;
    border: 1px solid #31587b;
    border-radius: 5px;
    font-weight: 600;
    padding: 3px 10px;
    margin: 2px 4px;
}
"""
