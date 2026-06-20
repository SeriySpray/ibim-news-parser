"""
Панель попереднього перегляду статті.

Віджет тільки для читання, що відображає обрану новину
з заголовком, метаданими та повним вмістом.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser, QSizePolicy
from PyQt6.QtGui import QFont
from core.models import NewsArticle


class PreviewPanel(QWidget):
    """Панель перегляду обраної статті (тільки для читання, спрощена версія)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_article = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Заголовок
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(16)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        # 2. Мета-рядок (джерело | дата | тікер)
        meta_layout = QHBoxLayout()

        self.source_label = QLabel()
        self.source_label.setStyleSheet('color: #8b8ba3;')
        meta_layout.addWidget(self.source_label)

        sep1 = QLabel('|')
        sep1.setStyleSheet('color: #55556a;')
        meta_layout.addWidget(sep1)

        self.date_label = QLabel()
        self.date_label.setStyleSheet('color: #8b8ba3;')
        meta_layout.addWidget(self.date_label)

        sep2 = QLabel('|')
        sep2.setStyleSheet('color: #55556a;')
        meta_layout.addWidget(sep2)

        self.ticker_label = QLabel()
        self.ticker_label.setStyleSheet('color: #a29bfe; font-weight: bold;')
        meta_layout.addWidget(self.ticker_label)

        meta_layout.addStretch()
        layout.addLayout(meta_layout)

        # 3. Контент
        self.content_browser = QTextBrowser()
        self.content_browser.setOpenExternalLinks(True)
        self.content_browser.setSizePolicy(QSizePolicy.Policy.Expanding,
                                           QSizePolicy.Policy.Expanding)
        layout.addWidget(self.content_browser)

        # Початковий стан — заповнювач
        self.clear()

    def _format_text_to_html(self, text: str) -> str:
        """Перетворює звичайний текст у HTML з абзацами для гарної читабельності."""
        import html
        if not text:
            return ""
        escaped = html.escape(text)
        paragraphs = escaped.split('\n\n')
        html_paragraphs = []
        for p in paragraphs:
            p_clean = p.strip()
            if p_clean:
                p_with_br = p_clean.replace('\n', '<br>')
                html_paragraphs.append(
                    f'<p style="margin-bottom: 14px; line-height: 1.6; font-size: 11pt; color: #f0f0f5;">'
                    f'{p_with_br}</p>'
                )
        return "".join(html_paragraphs)

    def show_article(self, article: NewsArticle):
        """Відобразити обрану статтю у панелі перегляду."""
        self._current_article = article

        self.title_label.setText(article.title)
        self.source_label.setText(article.source)
        self.date_label.setText(
            article.published_at.strftime('%d.%m.%Y %H:%M')
            if article.published_at else '')
        self.ticker_label.setText(article.company_ticker)

        # Контент
        if article.content:
            self.content_browser.setHtml(self._format_text_to_html(article.content))
        elif article.summary:
            self.content_browser.setHtml(self._format_text_to_html(article.summary))
        else:
            self.content_browser.setHtml(
                '<p style="color: #55556a; text-align: center; '
                'margin-top: 80px; font-size: 14pt;">Вміст відсутній</p>'
            )

    def clear(self):
        """Очистити панель та показати заповнювач."""
        self._current_article = None
        self.title_label.setText('')
        self.source_label.setText('')
        self.date_label.setText('')
        self.ticker_label.setText('')
        self.content_browser.setHtml(
            '<p style="color: #55556a; text-align: center; '
            'margin-top: 80px; font-size: 14pt;">'
            'Оберіть новину для перегляду</p>')
