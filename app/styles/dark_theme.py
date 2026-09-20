"""
VideoCutPub - QSS Dark Theme Stylesheet for PySide6
"""

DARK_THEME_QSS = """
QMainWindow {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}

QGroupBox {
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 12px;
    font-weight: bold;
    color: #89b4fa;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
}

QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}

QPushButton:pressed {
    background-color: #585b70;
}

QPushButton:disabled {
    background-color: #181825;
    color: #6c7086;
    border-color: #313244;
}

QPushButton#btn_start {
    background-color: #a6e3a1;
    color: #11111b;
    border: none;
    font-size: 14px;
}

QPushButton#btn_start:hover {
    background-color: #94e2d5;
}

QPushButton#btn_cancel {
    background-color: #f38ba8;
    color: #11111b;
    border: none;
}

QPushButton#btn_cancel:hover {
    background-color: #e78284;
}

QLineEdit, QComboBox, QSpinBox {
    background-color: #181825;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 5px 8px;
    color: #cdd6f4;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #89b4fa;
}

QTableWidget {
    background-color: #181825;
    gridline-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    selection-background-color: #45475a;
    selection-color: #cdd6f4;
}

QHeaderView::section {
    background-color: #313244;
    color: #b4befe;
    padding: 6px;
    border: none;
    font-weight: bold;
}

QProgressBar {
    border: 1px solid #45475a;
    border-radius: 6px;
    text-align: center;
    background-color: #181825;
    color: #cdd6f4;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 5px;
}

QRadioButton {
    spacing: 6px;
}

QRadioButton::indicator {
    width: 14px;
    height: 14px;
}
"""
