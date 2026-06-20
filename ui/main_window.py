"""
IBIM News Parser — Main application window.

Assembles SearchPanel, NewsPanel, and PreviewPanel into the main QMainWindow.
Handles data fetching via background QThread, database operations, and filtering.
"""

import os
from datetime import datetime
from typing import List, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QMenuBar, QMenu, QMessageBox,
    QProgressDialog, QApplication, QLabel
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QAction, QFont

from config import Config
from core.models import NewsArticle
from core.database import Database
from ui.search_panel import SearchPanel
from ui.news_panel import NewsPanel
from ui.preview_panel import PreviewPanel
from ui.settings_dialog import SettingsDialog


# ═══════════════════════════════════════════════════════════════════
#  Fetch Worker — runs parsers in a background thread
# ═══════════════════════════════════════════════════════════════════

class FetchWorker(QThread):
    """Background thread that fetches news from all configured parsers."""

    progress = pyqtSignal(str)      # status message
    finished = pyqtSignal(list)     # List[NewsArticle]
    error = pyqtSignal(str)         # error message

    def __init__(self, parsers, ticker: str, company_name: str,
                 date_from, date_to, parent=None):
        super().__init__(parent)
        self.parsers = parsers
        self.ticker = ticker
        self.company_name = company_name
        self.date_from = date_from
        self.date_to = date_to

    def run(self):
        """Fetch news from each parser sequentially, combining results."""
        all_articles: List[NewsArticle] = []

        for parser in self.parsers:
            source_name = parser.get_source_name()
            try:
                if not parser.is_configured():
                    self.progress.emit(
                        f"⏭ {source_name}: не налаштовано, пропускаємо"
                      )
                    continue

                self.progress.emit(f"🔄 Завантаження з {source_name}…")
                articles = parser.fetch_news(
                    self.ticker,
                    self.company_name,
                    self.date_from,
                    self.date_to,
                )
                all_articles.extend(articles)
                self.progress.emit(
                    f"✅ {source_name}: отримано {len(articles)} новин"
                )
            except Exception as exc:
                self.progress.emit(f"❌ {source_name}: {exc}")

        # Web scrape full text and analyze articles if any were fetched
        if all_articles:
            # 1. Scrape full text
            self.progress.emit("🌐 Викачування повного тексту статей…")
            scraped_articles: List[NewsArticle] = []
            try:
                from core.scraper import scrape_article_text
                total = len(all_articles)
                for idx, article in enumerate(all_articles):
                    self.progress.emit(f"🌐 Скрапінг повного тексту ({idx + 1}/{total})…")
                    full_text = scrape_article_text(article.source_url)
                    if full_text and len(full_text) > len(article.content or ""):
                        article.content = full_text
                        scraped_articles.append(article)
            except Exception as exc:
                self.progress.emit(f"❌ Помилка скрапінгу: {exc}")

            all_articles = scraped_articles

            # 2. Analyze relevance & impact
            if all_articles:
                self.progress.emit("🧠 Ініціалізація аналізатора FinBERT…")
                try:
                    from core.analyzer import FinancialAnalyzer, calculate_relevance
                    analyzer = FinancialAnalyzer()
                    
                    total = len(all_articles)
                    for idx, article in enumerate(all_articles):
                        self.progress.emit(f"🧠 - Аналіз впливу та релевантності ({idx + 1}/{total})…")
                        
                        # Relevance calculation
                        article.relevance = calculate_relevance(
                            article.title,
                            article.content or article.summary,
                            self.ticker,
                            self.company_name
                        )
                        
                        # Impact (FinBERT sentiment analysis)
                        text_for_sentiment = (article.title or "") + ". " + (article.summary or article.content or "")
                        article.impact = analyzer.analyze_sentiment(text_for_sentiment)
                except Exception as exc:
                    self.progress.emit(f"❌ Помилка аналізу: {exc}")

        self.finished.emit(all_articles)


# ═══════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Primary application window for IBIM News Parser (simplified)."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.config = Config()
        self._parsers = []
        self._current_articles: List[NewsArticle] = []
        self._fetch_worker: Optional[FetchWorker] = None

        self._init_parsers()
        self._init_ui()
        self._init_menu()
        self._connect_signals()

        # Initial refresh
        self._refresh_from_db()

    # ── Parser initialisation ─────────────────────────────────────
    def _init_parsers(self):
        """Create parser instances (gracefully skip if module missing)."""
        self._parsers = []
        try:
            from parsers.finnhub_parser import FinnhubParser
            self._parsers.append(FinnhubParser())
        except ImportError:
            pass
        try:
            from parsers.newsapi_parser import NewsAPIParser
            self._parsers.append(NewsAPIParser())
        except ImportError:
            pass
        try:
            from parsers.rss_parser import RSSParser
            self._parsers.append(RSSParser())
        except ImportError:
            pass

    # ── UI setup ──────────────────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle("IBIM News Parser")
        self.resize(1300, 800)
        self._center_on_screen()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Search panel (top)
        self.search_panel = SearchPanel()
        main_layout.addWidget(self.search_panel)

        # Splitter — news list (left) + preview (right)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.news_panel = NewsPanel()
        self.preview_panel = PreviewPanel()

        self.splitter.addWidget(self.news_panel)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setStretchFactor(0, 45)
        self.splitter.setStretchFactor(1, 55)

        main_layout.addWidget(self.splitter, 1)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Готово")
        self.count_status = QLabel("")
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.count_status)

    def _center_on_screen(self):
        """Center the window on the primary screen."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2 + geo.x()
            y = (geo.height() - self.height()) // 2 + geo.y()
            self.move(x, y)

    # ── Menu bar ──────────────────────────────────────────────────
    def _init_menu(self):
        menubar = self.menuBar()

        # ── File menu ──
        file_menu = menubar.addMenu("Файл")
        exit_action = QAction("Вихід", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ── View menu ──
        view_menu = menubar.addMenu("Вигляд")
        refresh_action = QAction("Оновити", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh_from_db)
        view_menu.addAction(refresh_action)

        # ── Settings menu ──
        settings_menu = menubar.addMenu("Налаштування")
        api_keys_action = QAction("API ключі…", self)
        api_keys_action.triggered.connect(self._open_settings)
        settings_menu.addAction(api_keys_action)

        # ── Help menu ──
        help_menu = menubar.addMenu("Довідка")
        about_action = QAction("Про програму", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ── Signal connections ────────────────────────────────────────
    def _connect_signals(self):
        # Search panel
        self.search_panel.fetch_requested.connect(self._on_fetch_requested)
        self.search_panel.filter_changed.connect(self._on_filter_changed)

        # News panel
        self.news_panel.article_selected.connect(self._on_article_selected)

    # ── Fetch workflow ────────────────────────────────────────────
    def _on_fetch_requested(self, ticker: str, company_name: str,
                             date_from, date_to):
        """Start fetching news from all configured parsers."""
        if self._fetch_worker and self._fetch_worker.isRunning():
            QMessageBox.warning(
                self, "Зайнято",
                "Завантаження вже виконується. Зачекайте."
            )
            return

        if not ticker.strip():
            QMessageBox.warning(
                self, "Помилка",
                "Введіть назву компанії або тікер."
            )
            return

        if not self._parsers:
            QMessageBox.warning(
                self, "Помилка",
                "Немає доступних парсерів. Перевірте налаштування API."
            )
            return

        # Convert QDate to Python datetime objects for parsers
        py_date_from = datetime.combine(date_from.toPyDate(), datetime.min.time()) if isinstance(date_from, QDate) else date_from
        py_date_to = datetime.combine(date_to.toPyDate(), datetime.max.time()) if isinstance(date_to, QDate) else date_to

        # Progress dialog
        self._progress = QProgressDialog(
            "Завантаження новин…", "Скасувати", 0, 0, self
        )
        self._progress.setWindowTitle("Завантаження")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.show()

        # Create and start worker
        self._fetch_worker = FetchWorker(
            self._parsers, ticker.strip(), company_name.strip(),
            py_date_from, py_date_to, self
        )
        self._fetch_worker.progress.connect(self._on_fetch_progress)
        self._fetch_worker.finished.connect(self._on_fetch_finished)
        self._fetch_worker.error.connect(self._on_fetch_error)

        self._progress.canceled.connect(self._fetch_worker.terminate)

        self._fetch_worker.start()
        self.status_label.setText("Завантаження…")

    def _on_fetch_progress(self, message: str):
        """Update progress dialog with status message."""
        if hasattr(self, '_progress') and self._progress:
            self._progress.setLabelText(message)
        self.status_label.setText(message)

    def _on_fetch_finished(self, articles: List[NewsArticle]):
        """Handle completed fetch — insert into DB and refresh list."""
        if hasattr(self, '_progress') and self._progress:
            self._progress.close()
            self._progress = None

        # Insert new articles into database
        new_count = 0
        for article in articles:
            if not self.db.article_exists(article.source_url):
                if self.db.insert_article(article):
                    new_count += 1

        total = self.db.get_article_count()

        self.status_label.setText(
            f"Завершено: {new_count} нових з {len(articles)} | "
            f"Всього у базі: {total} | "
            f"Останнє оновлення: {datetime.now().strftime('%H:%M:%S')}"
        )

        # Refresh the table with current filters
        self._refresh_from_db()

    def _on_fetch_error(self, error_msg: str):
        """Handle fetch error."""
        if hasattr(self, '_progress') and self._progress:
            self._progress.close()
            self._progress = None

        self.status_label.setText(f"Помилка: {error_msg}")
        QMessageBox.critical(self, "Помилка завантаження", error_msg)

    # ── Filtering / refresh ───────────────────────────────────────
    def _on_filter_changed(self):
        """Re-query database with current filter settings."""
        self._refresh_from_db()

    def _refresh_from_db(self):
        """Query articles from database matching dates and filter by company query."""
        filters = self.search_panel.get_filters()

        company_query = filters.get('company_query', '').strip()
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        min_relevance = filters.get('min_relevance', 0.0)
        min_impact = filters.get('min_impact', 0.0)

        # Convert QDate to Python datetime objects
        py_date_from = None
        if date_from:
            py_date_from = datetime.combine(date_from.toPyDate(), datetime.min.time())
        py_date_to = None
        if date_to:
            py_date_to = datetime.combine(date_to.toPyDate(), datetime.max.time())

        # If there's no search query, show nothing
        if not company_query:
            self._current_articles = []
            self.news_panel.load_articles([])
            self.count_status.setText("Статей: 0")
            self.preview_panel.clear()
            return

        try:
            # Query articles from database within the specified date range and with relevance/impact filters
            articles = self.db.search_articles(
                date_from=py_date_from,
                date_to=py_date_to,
                min_relevance=min_relevance if min_relevance > 0.0 else None,
                min_impact=min_impact if min_impact > 0.0 else None,
            )
        except Exception:
            articles = []

        # Filter locally in Python by company name or ticker (case-insensitive substring match)
        term = company_query.lower()
        articles = [
            a for a in articles
            if term in (a.company_ticker or '').lower()
            or term in (a.company_name or '').lower()
        ]

        self._current_articles = articles
        self.news_panel.load_articles(articles)
        self.count_status.setText(f"Статей: {len(articles)}")
        self.preview_panel.clear()

    # ── Article selection ─────────────────────────────────────────
    def _on_article_selected(self, article):
        """Show selected article in the preview panel."""
        if article:
            self.preview_panel.show_article(article)
        else:
            self.preview_panel.clear()

    # ── Settings ──────────────────────────────────────────────────
    def _open_settings(self):
        """Open the API settings dialog."""
        dialog = SettingsDialog(self)
        if dialog.exec():
            # Reload parsers after settings change
            self._init_parsers()
            self.status_label.setText("Налаштування збережено")

    # ── About ─────────────────────────────────────────────────────
    def _show_about(self):
        QMessageBox.about(
            self,
            "Про IBIM News Parser",
            "<h2>IBIM News Parser</h2>"
            "<p>Інвестиційний агрегатор новин для аналізу ринку.</p>"
            "<p>Збирає та відображає фінансові новини з різних джерел "
            "по вибраній компанії за обраний період.</p>"
            "<hr>"
            "<p style='color: #8b8ba3;'>Версія 1.0.0 (спрощена)</p>"
        )

    # ── Cleanup ───────────────────────────────────────────────────
    def closeEvent(self, event):
        """Ensure background threads are stopped on exit."""
        if self._fetch_worker and self._fetch_worker.isRunning():
            self._fetch_worker.terminate()
            self._fetch_worker.wait(3000)
        event.accept()
