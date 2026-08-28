"""
Панель новин — віджет для відображення списку новинних статей у таблиці.

Відображає спрощений список статей з датою, заголовком, джерелом,
релевантністю та впливом на ціну акцій.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel, QAbstractItemView
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor
from core.models import NewsArticle


class NewsPanel(QWidget):
    """Панель для відображення списку новинних статей (з показниками аналітики)."""

    article_selected = pyqtSignal(object)
    articles_selected = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._articles: list = []
        self._init_ui()

    def _init_ui(self):
        """Ініціалізація інтерфейсу панелі новин."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Лічильник новин
        self.count_label = QLabel('Завантажено: 0 новин')
        self.count_label.setStyleSheet('color: #8b8ba3; font-weight: bold;')
        layout.addWidget(self.count_label)

        # Таблиця новин
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(['Дата', 'Заголовок', 'Джерело', 'Релевантність', 'Вплив', 'Реал. зміна', 'Прогноз'])

        # Ширина колонок
        self.table.setColumnWidth(0, 95)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 75)
        self.table.setColumnWidth(5, 95)
        self.table.setColumnWidth(6, 85)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)

        # Налаштування таблиці
        self.table.setSortingEnabled(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Підключення сигналів таблиці
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self.table)

    def load_articles(self, articles: list):
        """Завантажити список статей у таблицю.

        Args:
            articles: Список об'єктів NewsArticle для відображення.
        """
        self._articles = list(articles)
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(self._articles))

        for idx, article in enumerate(self._articles):
            # Колонка 0 — дата
            if article.published_at is not None:
                date_text = article.published_at.strftime('%d.%m.%Y')
            else:
                date_text = ''
            date_item = QTableWidgetItem(date_text)
            date_item.setData(Qt.ItemDataRole.UserRole, idx)
            self.table.setItem(idx, 0, date_item)

            # Column 1 — заголовок
            title_item = QTableWidgetItem(article.title)
            self.table.setItem(idx, 1, title_item)

            # Column 2 — джерело
            source_item = QTableWidgetItem(article.source)
            self.table.setItem(idx, 2, source_item)

            # Column 3 — релевантність
            rel_val = getattr(article, 'relevance', 0.0)
            rel_item = QTableWidgetItem(f"{rel_val * 100:.0f}%")
            rel_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 3, rel_item)

            # Column 4 — вплив на акції
            imp_val = getattr(article, 'impact', 0.0)
            imp_item = QTableWidgetItem(f"{imp_val:+.2f}")
            imp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Підсвічування кольорами: зелений (позитивний), червоний (негативний), сірий (нейтральний)
            if imp_val > 0.15:
                imp_item.setForeground(QColor('#00cec9'))
            elif imp_val < -0.15:
                imp_item.setForeground(QColor('#ff7675'))
            else:
                imp_item.setForeground(QColor('#8b8ba3'))
                
            self.table.setItem(idx, 4, imp_item)

            # Column 5 — реальна зміна акцій
            real_val = getattr(article, 'real_stock_return', None)
            if real_val is not None and real_val != 0.0:
                real_item = QTableWidgetItem(f"{real_val:+.2f}%")
                if real_val > 0.0:
                    real_item.setForeground(QColor('#00cec9'))
                else:
                    real_item.setForeground(QColor('#ff7675'))
            else:
                real_item = QTableWidgetItem("—")
                real_item.setForeground(QColor('#8b8ba3'))
            real_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 5, real_item)

            # Column 6 — прогноз зміни акцій
            pred_val = getattr(article, 'predicted_stock_return', None)
            if pred_val is not None and pred_val != 0.0:
                pred_item = QTableWidgetItem(f"{pred_val:+.2f}%")
                if pred_val > 0.0:
                    pred_item.setForeground(QColor('#00cec9'))
                else:
                    pred_item.setForeground(QColor('#ff7675'))
            else:
                pred_item = QTableWidgetItem("—")
                pred_item.setForeground(QColor('#8b8ba3'))
            pred_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 6, pred_item)

        self.table.setSortingEnabled(True)
        self.count_label.setText(f'Завантажено: {len(articles)} новин')

    def get_selected_articles(self) -> list:
        """Отримати список обраних статей.

        Returns:
            Список об'єктів NewsArticle, що відповідають виділеним рядкам.
        """
        selected_rows = set()
        for index in self.table.selectionModel().selectedRows():
            row = index.row()
            date_item = self.table.item(row, 0)
            if date_item is not None:
                article_idx = date_item.data(Qt.ItemDataRole.UserRole)
                if article_idx is not None and 0 <= article_idx < len(self._articles):
                    selected_rows.add(article_idx)

        return [self._articles[i] for i in sorted(selected_rows)]

    def clear(self):
        """Очистити таблицю та скинути дані."""
        self.table.setRowCount(0)
        self._articles = []
        self.count_label.setText('Завантажено: 0 новин')

    def _on_selection_changed(self):
        """Обробник зміни виділення у таблиці."""
        selected = self.get_selected_articles()
        if len(selected) == 1:
            self.article_selected.emit(selected[0])
        self.articles_selected.emit(selected)

    def select_article_by_id(self, article_id: str):
        """Select the row matching the given article ID."""
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                date_item = self.table.item(row, 0)
                if date_item is not None:
                    idx = date_item.data(Qt.ItemDataRole.UserRole)
                    if idx is not None and 0 <= idx < len(self._articles):
                        if self._articles[idx].id == article_id:
                            self.table.selectRow(row)
                            break
        finally:
            self.table.blockSignals(False)
