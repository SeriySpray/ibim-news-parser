"""
Діалог налаштувань API-ключів.

Дозволяє користувачу вводити, перевіряти та зберігати
ключі для Finnhub та NewsAPI.
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QGroupBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from config import Config
import urllib.request
import json


class SettingsDialog(QDialog):
    """Діалог для керування API-ключами."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Налаштування')
        self.setFixedSize(480, 520)
        self.setModal(True)
        self.config = Config()

        main_layout = QVBoxLayout(self)

        # Заголовок
        title = QLabel('Налаштування API')
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(14)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # --- Finnhub ---
        finnhub_group = QGroupBox('Finnhub')
        finnhub_layout = QVBoxLayout(finnhub_group)

        finnhub_input_layout = QHBoxLayout()
        self.finnhub_input = QLineEdit()
        self.finnhub_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.finnhub_input.setPlaceholderText('Введіть API ключ Finnhub')
        finnhub_input_layout.addWidget(self.finnhub_input)

        self.finnhub_toggle = QPushButton('👁')
        self.finnhub_toggle.setFixedWidth(36)
        self.finnhub_toggle.clicked.connect(
            lambda: self._toggle_echo(self.finnhub_input))
        finnhub_input_layout.addWidget(self.finnhub_toggle)
        finnhub_layout.addLayout(finnhub_input_layout)

        finnhub_link = QLabel(
            '<a href="https://finnhub.io/register" style="color: #a29bfe;">'
            'Зареєструватися на Finnhub ↗</a>')
        finnhub_link.setOpenExternalLinks(True)
        finnhub_layout.addWidget(finnhub_link)

        finnhub_check_layout = QHBoxLayout()
        finnhub_check_btn = QPushButton('Перевірити')
        finnhub_check_btn.clicked.connect(self._test_finnhub)
        finnhub_check_layout.addWidget(finnhub_check_btn)
        self.finnhub_status = QLabel()
        finnhub_check_layout.addWidget(self.finnhub_status)
        finnhub_layout.addLayout(finnhub_check_layout)

        main_layout.addWidget(finnhub_group)

        # --- NewsAPI ---
        newsapi_group = QGroupBox('NewsAPI')
        newsapi_layout = QVBoxLayout(newsapi_group)

        newsapi_input_layout = QHBoxLayout()
        self.newsapi_input = QLineEdit()
        self.newsapi_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.newsapi_input.setPlaceholderText('Введіть API ключ NewsAPI')
        newsapi_input_layout.addWidget(self.newsapi_input)

        self.newsapi_toggle = QPushButton('👁')
        self.newsapi_toggle.setFixedWidth(36)
        self.newsapi_toggle.clicked.connect(
            lambda: self._toggle_echo(self.newsapi_input))
        newsapi_input_layout.addWidget(self.newsapi_toggle)
        newsapi_layout.addLayout(newsapi_input_layout)

        newsapi_link = QLabel(
            '<a href="https://newsapi.org/register" style="color: #a29bfe;">'
            'Зареєструватися на NewsAPI ↗</a>')
        newsapi_link.setOpenExternalLinks(True)
        newsapi_layout.addWidget(newsapi_link)

        newsapi_check_layout = QHBoxLayout()
        newsapi_check_btn = QPushButton('Перевірити')
        newsapi_check_btn.clicked.connect(self._test_newsapi)
        newsapi_check_layout.addWidget(newsapi_check_btn)
        self.newsapi_status = QLabel()
        newsapi_check_layout.addWidget(self.newsapi_status)
        newsapi_layout.addLayout(newsapi_check_layout)

        main_layout.addWidget(newsapi_group)

        # Розтяжка
        main_layout.addStretch()

        # Кнопки дій
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton('Скасувати')
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton('Зберегти')
        save_btn.setObjectName('accentButton')
        save_btn.clicked.connect(self._save)
        button_layout.addWidget(save_btn)

        main_layout.addLayout(button_layout)

        # Завантажити поточні ключі
        self.finnhub_input.setText(self.config.get_api_key('finnhub'))
        self.newsapi_input.setText(self.config.get_api_key('newsapi'))
        self._update_status(self.finnhub_status,
                            self.config.get_api_key('finnhub'))
        self._update_status(self.newsapi_status,
                            self.config.get_api_key('newsapi'))

    # ------------------------------------------------------------------
    # Внутрішні методи
    # ------------------------------------------------------------------

    def _toggle_echo(self, line_edit: QLineEdit):
        """Перемкнути видимість тексту в полі вводу."""
        if line_edit.echoMode() == QLineEdit.EchoMode.Password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def _test_finnhub(self):
        """Перевірити ключ Finnhub через API-запит."""
        key = self.finnhub_input.text().strip()
        if not key:
            self.finnhub_status.setText('❌ Ключ не введено')
            return
        try:
            url = f'https://finnhub.io/api/v1/stock/symbol?exchange=US&token={key}'
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self.finnhub_status.setText('✅ Ключ дійсний')
                else:
                    self.finnhub_status.setText(f'❌ Помилка: {resp.status}')
        except Exception as e:
            self.finnhub_status.setText(f'❌ Помилка: {e}')

    def _test_newsapi(self):
        """Перевірити ключ NewsAPI через API-запит."""
        key = self.newsapi_input.text().strip()
        if not key:
            self.newsapi_status.setText('❌ Ключ не введено')
            return
        try:
            url = (f'https://newsapi.org/v2/top-headlines?'
                   f'country=us&pageSize=1&apiKey={key}')
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get('status') == 'ok':
                    self.newsapi_status.setText('✅ Ключ дійсний')
                else:
                    self.newsapi_status.setText(
                        f'❌ {data.get("message", "Невідома помилка")}')
        except Exception as e:
            self.newsapi_status.setText(f'❌ Помилка: {e}')

    def _update_status(self, label: QLabel, key: str):
        """Оновити статус-мітку на основі наявності ключа."""
        if key:
            label.setText('✅ Налаштовано')
        else:
            label.setText('❌ Не налаштовано')

    def _save(self):
        """Зберегти API-ключі в конфігурацію та закрити діалог."""
        finnhub_key = self.finnhub_input.text().strip()
        newsapi_key = self.newsapi_input.text().strip()
        self.config.set_api_key('finnhub', finnhub_key)
        self.config.set_api_key('newsapi', newsapi_key)
        self.accept()
