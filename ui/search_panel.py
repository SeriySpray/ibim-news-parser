"""
Панель пошуку новин.

Містить поля для введення назви компанії або тікера, вибору діапазону дат
та фільтрації за релевантністю та впливом на акції.
"""

from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLineEdit, QDateEdit, 
                             QPushButton, QLabel, QSpinBox, QDoubleSpinBox)
from PyQt6.QtCore import pyqtSignal, QDate


class SearchPanel(QWidget):
    """Панель пошуку новин для IBIM (з фільтрами аналітики)."""

    fetch_requested = pyqtSignal(str, str, object, object)  # query, query, date_from, date_to
    filter_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_widgets()
        self._init_layout()
        self._connect_signals()

    def _init_widgets(self):
        # --- Діапазон дат ---
        self.date_from = QDateEdit()
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat('dd.MM.yyyy')

        self.date_to = QDateEdit()
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat('dd.MM.yyyy')

        # --- Назва компанії / Тікер ---
        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText('Назва компанії або тікер (напр. Apple, AAPL)')
        self.company_input.setMinimumWidth(260)

        # --- Фільтри аналітики ---
        self.min_relevance_spin = QSpinBox()
        self.min_relevance_spin.setRange(0, 100)
        self.min_relevance_spin.setSingleStep(5)
        self.min_relevance_spin.setValue(0)
        self.min_relevance_spin.setSuffix('%')
        self.min_relevance_spin.setFixedWidth(75)

        self.min_impact_spin = QDoubleSpinBox()
        self.min_impact_spin.setRange(0.0, 1.0)
        self.min_impact_spin.setSingleStep(0.05)
        self.min_impact_spin.setValue(0.0)
        self.min_impact_spin.setDecimals(2)
        self.min_impact_spin.setFixedWidth(75)

        # --- Кнопка завантаження ---
        self.fetch_btn = QPushButton('Завантажити')
        self.fetch_btn.setObjectName('accentButton')

    def _init_layout(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        layout.addWidget(QLabel('Період з:'))
        layout.addWidget(self.date_from)
        layout.addWidget(QLabel('до:'))
        layout.addWidget(self.date_to)

        layout.addWidget(QLabel('Компанія:'))
        layout.addWidget(self.company_input)

        layout.addWidget(QLabel('Релевантність від:'))
        layout.addWidget(self.min_relevance_spin)
        layout.addWidget(QLabel('Вплив від:'))
        layout.addWidget(self.min_impact_spin)

        layout.addStretch()
        layout.addWidget(self.fetch_btn)

    def _connect_signals(self):
        self.fetch_btn.clicked.connect(self._on_fetch)
        self.company_input.textChanged.connect(self.filter_changed)
        self.date_from.dateChanged.connect(self.filter_changed)
        self.date_to.dateChanged.connect(self.filter_changed)
        self.min_relevance_spin.valueChanged.connect(self.filter_changed)
        self.min_impact_spin.valueChanged.connect(self.filter_changed)

    def _on_fetch(self):
        """Емітує сигнал fetch_requested з введеними значеннями."""
        query = self.company_input.text().strip()
        self.fetch_requested.emit(
            query,
            query,
            self.date_from.date(),
            self.date_to.date(),
        )

    def get_filters(self) -> dict:
        """Повертає словник поточних фільтрів."""
        return {
            'company_query': self.company_input.text().strip(),
            'date_from': self.date_from.date(),
            'date_to': self.date_to.date(),
            'min_relevance': self.min_relevance_spin.value() / 100.0,
            'min_impact': self.min_impact_spin.value(),
        }
