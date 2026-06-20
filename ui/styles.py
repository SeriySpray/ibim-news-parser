"""
IBIM News Parser — Dark Theme Stylesheet.

Provides a comprehensive, production-quality QSS stylesheet
for the PyQt6 desktop application with a modern dark theme.
"""


def get_stylesheet() -> str:
    """Return the complete QSS stylesheet string for the application."""
    return """
    /* ============================================================
       IBIM Dark Theme — PyQt6 QSS Stylesheet
       Color Palette:
         Background:  #0f0f14 (base), #1a1a24 (panels), #252532 (cards)
         Accent:      #6c5ce7 (primary), #a29bfe (light)
         Semantic:    #00cec9 (success), #fdcb6e (warning), #ff7675 (danger)
         Text:        #f0f0f5 (primary), #8b8ba3 (secondary), #55556a (muted)
         Borders:     #2d2d3f
       ============================================================ */

    /* --- Base Widgets --- */

    QMainWindow {
        background-color: #0f0f14;
    }

    QWidget {
        background-color: #0f0f14;
        color: #f0f0f5;
        font-family: 'Segoe UI', sans-serif;
    }

    QLabel {
        color: #f0f0f5;
        background-color: transparent;
    }

    QDialog {
        background-color: #1a1a24;
    }

    /* --- Buttons --- */

    QPushButton {
        background-color: #252532;
        color: #f0f0f5;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        padding: 8px 16px;
    }

    QPushButton:hover {
        background-color: #2d2d3f;
        border-color: #6c5ce7;
    }

    QPushButton:pressed {
        background-color: #1a1a24;
    }

    QPushButton:disabled {
        background-color: #1a1a24;
        color: #55556a;
        border-color: #252532;
    }

    QPushButton#accentButton {
        background-color: #6c5ce7;
        color: #f0f0f5;
        border: 1px solid #6c5ce7;
    }

    QPushButton#accentButton:hover {
        background-color: #7d6ff0;
        border-color: #7d6ff0;
    }

    QPushButton#accentButton:pressed {
        background-color: #5a4bd1;
        border-color: #5a4bd1;
    }

    /* --- Input Fields --- */

    QLineEdit {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        padding: 8px;
        color: #f0f0f5;
        selection-background-color: rgba(108, 92, 231, 0.5);
        selection-color: #f0f0f5;
    }

    QLineEdit:focus {
        border-color: #6c5ce7;
    }

    QLineEdit:disabled {
        background-color: #151520;
        color: #55556a;
    }

    QDateEdit {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        padding: 8px;
        color: #f0f0f5;
    }

    QDateEdit:focus {
        border-color: #6c5ce7;
    }

    QDateEdit::drop-down {
        border: none;
        width: 24px;
        subcontrol-position: center right;
        subcontrol-origin: padding;
        border-left: 1px solid #2d2d3f;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
    }

    /* --- ComboBox --- */

    QComboBox {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        padding: 8px;
        color: #f0f0f5;
        min-width: 80px;
    }

    QComboBox:focus {
        border-color: #6c5ce7;
    }

    QComboBox::drop-down {
        border: none;
        width: 24px;
        subcontrol-position: center right;
        subcontrol-origin: padding;
        border-left: 1px solid #2d2d3f;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
    }

    QComboBox::down-arrow {
        image: none;
    }

    QComboBox QAbstractItemView {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        selection-background-color: #6c5ce7;
        selection-color: #f0f0f5;
        color: #f0f0f5;
        outline: 0;
    }

    /* --- Table Widget --- */

    QTableWidget {
        background-color: #1a1a24;
        alternate-background-color: #1f1f2e;
        gridline-color: #2d2d3f;
        selection-background-color: rgba(108, 92, 231, 0.35);
        selection-color: #f0f0f5;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        outline: 0;
    }

    QTableWidget::item {
        padding: 6px;
        border-bottom: 1px solid #2d2d3f;
    }

    QTableWidget::item:selected {
        background-color: rgba(108, 92, 231, 0.35);
        color: #f0f0f5;
    }

    /* --- Header View --- */

    QHeaderView::section {
        background-color: #1a1a24;
        color: #8b8ba3;
        border: none;
        border-bottom: 2px solid #2d2d3f;
        padding: 8px;
        font-weight: bold;
    }

    QHeaderView::section:hover {
        color: #f0f0f5;
    }

    /* --- Text Browser --- */

    QTextBrowser {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        padding: 12px;
        color: #f0f0f5;
        selection-background-color: rgba(108, 92, 231, 0.5);
        selection-color: #f0f0f5;
    }

    QTextEdit {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        padding: 12px;
        color: #f0f0f5;
        selection-background-color: rgba(108, 92, 231, 0.5);
        selection-color: #f0f0f5;
    }

    /* --- Splitter --- */

    QSplitter::handle {
        background-color: #2d2d3f;
        width: 2px;
    }

    QSplitter::handle:hover {
        background-color: #6c5ce7;
    }

    /* --- Status Bar --- */

    QStatusBar {
        background-color: #0f0f14;
        color: #8b8ba3;
        border-top: 1px solid #2d2d3f;
    }

    QStatusBar::item {
        border: none;
    }

    /* --- Menu Bar & Menus --- */

    QMenuBar {
        background-color: #0f0f14;
        color: #f0f0f5;
        border-bottom: 1px solid #2d2d3f;
    }

    QMenuBar::item {
        padding: 6px 12px;
        background-color: transparent;
    }

    QMenuBar::item:selected {
        background-color: #252532;
        border-radius: 4px;
    }

    QMenu {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        padding: 4px;
    }

    QMenu::item {
        padding: 6px 24px;
        color: #f0f0f5;
        border-radius: 4px;
    }

    QMenu::item:selected {
        background-color: #6c5ce7;
        color: #f0f0f5;
    }

    QMenu::separator {
        height: 1px;
        background-color: #2d2d3f;
        margin: 4px 8px;
    }

    /* --- Scroll Bars (Vertical) --- */

    QScrollBar:vertical {
        width: 8px;
        background: #0f0f14;
        border: none;
    }

    QScrollBar::handle:vertical {
        background: #2d2d3f;
        border-radius: 4px;
        min-height: 30px;
    }

    QScrollBar::handle:vertical:hover {
        background: #6c5ce7;
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0;
        border: none;
    }

    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {
        background: none;
    }

    /* --- Scroll Bars (Horizontal) --- */

    QScrollBar:horizontal {
        height: 8px;
        background: #0f0f14;
        border: none;
    }

    QScrollBar::handle:horizontal {
        background: #2d2d3f;
        border-radius: 4px;
        min-width: 30px;
    }

    QScrollBar::handle:horizontal:hover {
        background: #6c5ce7;
    }

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {
        width: 0;
        border: none;
    }

    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {
        background: none;
    }

    /* --- Group Box --- */

    QGroupBox {
        border: 1px solid #2d2d3f;
        border-radius: 8px;
        margin-top: 16px;
        padding-top: 20px;
        color: #f0f0f5;
        font-weight: bold;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: #a29bfe;
    }

    /* --- Tab Widget --- */

    QTabWidget::pane {
        border: 1px solid #2d2d3f;
        background-color: #1a1a24;
        border-radius: 6px;
    }

    QTabBar::tab {
        background-color: #252532;
        color: #8b8ba3;
        padding: 8px 20px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin-right: 2px;
    }

    QTabBar::tab:hover {
        color: #f0f0f5;
        background-color: #2d2d3f;
    }

    QTabBar::tab:selected {
        background-color: #1a1a24;
        color: #f0f0f5;
        border-bottom: 2px solid #6c5ce7;
    }

    /* --- Check Box --- */

    QCheckBox {
        color: #f0f0f5;
        spacing: 8px;
        background-color: transparent;
    }

    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: 2px solid #2d2d3f;
        border-radius: 4px;
        background-color: #1a1a24;
    }

    QCheckBox::indicator:hover {
        border-color: #6c5ce7;
    }

    QCheckBox::indicator:checked {
        background-color: #6c5ce7;
        border-color: #6c5ce7;
    }

    /* --- Radio Button --- */

    QRadioButton {
        color: #f0f0f5;
        spacing: 8px;
        background-color: transparent;
    }

    QRadioButton::indicator {
        width: 18px;
        height: 18px;
        border: 2px solid #2d2d3f;
        border-radius: 10px;
        background-color: #1a1a24;
    }

    QRadioButton::indicator:hover {
        border-color: #6c5ce7;
    }

    QRadioButton::indicator:checked {
        background-color: #6c5ce7;
        border-color: #6c5ce7;
    }

    /* --- Progress Bar --- */

    QProgressBar {
        background-color: #252532;
        border-radius: 4px;
        text-align: center;
        color: #f0f0f5;
        border: none;
        min-height: 16px;
    }

    QProgressBar::chunk {
        background-color: #6c5ce7;
        border-radius: 4px;
    }

    /* --- ToolTip --- */

    QToolTip {
        background-color: #252532;
        color: #f0f0f5;
        border: 1px solid #2d2d3f;
        padding: 6px;
        border-radius: 4px;
    }

    /* --- Spin Box --- */

    QSpinBox,
    QDoubleSpinBox {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        padding: 8px;
        color: #f0f0f5;
    }

    QSpinBox:focus,
    QDoubleSpinBox:focus {
        border-color: #6c5ce7;
    }

    QSpinBox::up-button,
    QSpinBox::down-button,
    QDoubleSpinBox::up-button,
    QDoubleSpinBox::down-button {
        background-color: #252532;
        border: none;
        width: 20px;
    }

    QSpinBox::up-button:hover,
    QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover,
    QDoubleSpinBox::down-button:hover {
        background-color: #6c5ce7;
    }

    /* --- Slider --- */

    QSlider::groove:horizontal {
        height: 4px;
        background-color: #252532;
        border-radius: 2px;
    }

    QSlider::handle:horizontal {
        background-color: #6c5ce7;
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }

    QSlider::handle:horizontal:hover {
        background-color: #7d6ff0;
    }

    /* --- List Widget --- */

    QListWidget {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        color: #f0f0f5;
        outline: 0;
    }

    QListWidget::item {
        padding: 6px;
        border-bottom: 1px solid #2d2d3f;
    }

    QListWidget::item:selected {
        background-color: rgba(108, 92, 231, 0.35);
        color: #f0f0f5;
    }

    QListWidget::item:hover {
        background-color: #252532;
    }

    /* --- Tree Widget --- */

    QTreeWidget {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        border-radius: 6px;
        color: #f0f0f5;
        outline: 0;
    }

    QTreeWidget::item {
        padding: 4px;
    }

    QTreeWidget::item:selected {
        background-color: rgba(108, 92, 231, 0.35);
        color: #f0f0f5;
    }

    QTreeWidget::item:hover {
        background-color: #252532;
    }

    /* --- Dock Widget --- */

    QDockWidget {
        color: #f0f0f5;
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
    }

    QDockWidget::title {
        background-color: #1a1a24;
        border: 1px solid #2d2d3f;
        padding: 6px;
        text-align: left;
    }

    /* --- Tool Bar --- */

    QToolBar {
        background-color: #0f0f14;
        border-bottom: 1px solid #2d2d3f;
        spacing: 4px;
        padding: 2px;
    }

    QToolButton {
        background-color: transparent;
        color: #f0f0f5;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 4px 8px;
    }

    QToolButton:hover {
        background-color: #252532;
        border-color: #2d2d3f;
    }

    QToolButton:pressed {
        background-color: #1a1a24;
    }
    """
