"""
IBIM News Parser — Entry point.

Launches the PyQt6 desktop application.
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from config import Config
from core.database import Database
from ui.main_window import MainWindow
from ui.styles import get_stylesheet


def main():
    config = Config()
    config.load()

    db = Database()
    db.initialize()

    app = QApplication(sys.argv)
    app.setStyleSheet(get_stylesheet())
    app.setFont(QFont('Segoe UI', 10))
    app.setApplicationName('IBIM News Parser')

    window = MainWindow(db)
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
