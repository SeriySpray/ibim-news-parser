"""
IBIM News Parser — Main application window.

Assembles SearchPanel, NewsPanel, and PreviewPanel into the main QMainWindow.
Handles data fetching via background QThread, database operations, and filtering.
"""

import os
import logging
from datetime import datetime
from typing import List, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QMenuBar, QMenu, QMessageBox,
    QProgressDialog, QApplication, QLabel
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QAction, QFont

logger = logging.getLogger(__name__)

from config import Config
from core.models import NewsArticle
from core.database import Database
from ui.search_panel import SearchPanel
from ui.news_panel import NewsPanel
from ui.preview_panel import PreviewPanel
from ui.settings_dialog import SettingsDialog
from ui.auto_train_panel import AutoTrainPanel
from ui.model_eval_panel import ModelEvalPanel


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
            if self.isInterruptionRequested():
                return
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
                logger.warning("Parser %s error: %s", source_name, exc)
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
                    try:
                        full_text = scrape_article_text(article.source_url)
                        if full_text and len(full_text) > len(article.content or ""):
                            article.content = full_text
                    except Exception as exc:
                        logger.debug("Scraper error for %s: %s", article.source_url, exc)
                    scraped_articles.append(article)
            except Exception as exc:
                self.progress.emit(f"⚠️ Помилка ініціалізації скрапінгу: {exc}")
                # У разі критичної помилки залишаємо вихідні статті
                scraped_articles = all_articles

            all_articles = scraped_articles

            # 2. Analyze relevance & impact
            if all_articles:
                try:
                    from core.analyzer import FinancialAnalyzer, calculate_relevance
                    from core.classifier import NewsClassifierZeroShot

                    # ── FinBERT ──
                    analyzer = FinancialAnalyzer()
                    self.progress.emit("⏳ Завантаження FinBERT (може тривати до 5 хв при першому запуску)…")
                    try:
                        analyzer._lazy_init()
                        self.progress.emit("✅ FinBERT завантажено.")
                    except Exception as e:
                        logger.error("FinBERT init failed: %s", e)
                        self.progress.emit(f"⚠️ FinBERT не завантажився: {e}")
                        analyzer = None

                    if self.isInterruptionRequested():
                        self.finished.emit(all_articles)
                        return

                    # ── mDeBERTa Zero-Shot ──
                    zeroshot_classifier = NewsClassifierZeroShot()
                    use_zeroshot = False
                    self.progress.emit("⏳ Завантаження mDeBERTa Zero-Shot (~1 ГБ, може тривати до 10 хв)…")
                    try:
                        zeroshot_classifier._lazy_init()
                        use_zeroshot = True
                        self.progress.emit("✅ mDeBERTa завантажено.")
                    except Exception as e:
                        logger.error("mDeBERTa init failed: %s", e)
                        self.progress.emit(f"⚠️ mDeBERTa не завантажився, використовується локальний розрахунок: {e}")

                    if self.isInterruptionRequested():
                        self.finished.emit(all_articles)
                        return

                    total = len(all_articles)
                    for idx, article in enumerate(all_articles):
                        if self.isInterruptionRequested():
                            break
                        self.progress.emit(f"🧠 [{idx + 1}/{total}] {article.title[:55]}…")

                        # Relevance
                        try:
                            if use_zeroshot:
                                article.relevance = zeroshot_classifier.predict(
                                    article.title,
                                    article.content or article.summary or "",
                                    self.company_name or self.ticker
                                )
                            else:
                                article.relevance = calculate_relevance(
                                    article.title, article.content or article.summary or "",
                                    self.ticker, self.company_name
                                )
                        except Exception as e:
                            logger.warning("Relevance failed for '%s': %s", article.title[:40], e)

                        # Sentiment
                        if analyzer is not None:
                            try:
                                text_for_sentiment = (article.title or "") + ". " + (article.summary or article.content or "")
                                article.impact = analyzer.analyze_sentiment(text_for_sentiment)
                            except Exception as e:
                                logger.warning("FinBERT failed for '%s': %s", article.title[:40], e)

                        # Predict stock return using trained model
                        try:
                            from core.predictor import predict_stock_return
                            pred_val = predict_stock_return(article.title, article.summary, article.content)
                            if pred_val is not None:
                                article.predicted_stock_return = pred_val
                        except Exception as e:
                            logger.debug("On-the-fly prediction failed: %s", e)

                except Exception as exc:
                    logger.error("Analysis init error: %s", exc, exc_info=True)
                    self.progress.emit(f"❌ Помилка аналізу: {exc}")

        self.finished.emit(all_articles)


class ReclassifyWorker(QThread):
    """Background thread that reclassifies all database articles using the Zero-Shot model."""
    progress = pyqtSignal(str)      # status message
    finished = pyqtSignal(int)      # number of updated articles
    error = pyqtSignal(str)         # error message

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db

    def run(self):
        try:
            from core.classifier import NewsClassifierZeroShot
            from core.database import Database
            
            db_thread = Database()
            conn = db_thread._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, content, summary, company_name, company_ticker FROM articles")
            rows = cursor.fetchall()
            
            total = len(rows)
            if total == 0:
                self.finished.emit(0)
                return

            self.progress.emit("🧠 Ініціалізація моделі...")
            zeroshot = NewsClassifierZeroShot()
            zeroshot._lazy_init()
            classifier_func = lambda t, c, name, ticker: zeroshot.predict(t, c, name or ticker)

            updated_count = 0
            for idx, (art_id, title, content, summary, name, ticker) in enumerate(rows):
                self.progress.emit(f"🧠 Класифікація новин ({idx + 1}/{total})...")
                score = classifier_func(title, content or summary, name, ticker)
                
                cursor.execute(
                    "UPDATE articles SET relevance = ? WHERE id = ?",
                    (score, art_id)
                )
                updated_count += 1
                
                if updated_count % 20 == 0:
                    conn.commit()
            
            conn.commit()
            self.finished.emit(updated_count)
        except Exception as e:
            self.error.emit(str(e))


class AlignPricesWorker(QThread):
    """Background thread that fetches stock prices and aligns news articles with returns."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db

    def run(self):
        try:
            from core.database import Database
            from core.market_data import align_article_with_return
            
            db_thread = Database()
            conn = db_thread._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT id, company_ticker FROM articles WHERE company_ticker != ''")
            rows = cursor.fetchall()
            
            total = len(rows)
            if total == 0:
                self.finished.emit(0)
                return

            aligned_count = 0
            for idx, row_data in enumerate(rows):
                if self.isInterruptionRequested():
                    break
                art_id = row_data["id"]
                self.progress.emit(f"📈 Зіставлення новин з цінами акцій ({idx + 1}/{total})…")
                try:
                    res = align_article_with_return(db_thread, art_id)
                    if res is not None:
                        aligned_count += 1
                except Exception as e:
                    logger.warning("Failed to align article %s: %s", art_id, e)
            
            self.finished.emit(aligned_count)
        except Exception as e:
            logger.error("AlignPricesWorker error: %s", e, exc_info=True)
            self.error.emit(str(e))


class TrainPredictorWorker(QThread):
    """Background thread that trains the PyTorch return predictor model."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db

    def run(self):
        try:
            from core.database import Database
            from core.predictor import train_predictor_model
            
            db_thread = Database()
            self.progress.emit("🧠 Ініціалізація FinBERT та підготовка даних…")
            result_msg = train_predictor_model(db_thread, progress_callback=self.progress.emit)
            self.finished.emit(result_msg)
        except Exception as e:
            self.error.emit(str(e))


class PredictWorker(QThread):
    """Background thread that runs stock return predictions on all news."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db

    def run(self):
        try:
            from core.database import Database
            from core.predictor import predict_stock_return
            
            db_thread = Database()
            conn = db_thread._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, summary, content FROM articles")
            rows = cursor.fetchall()
            
            total = len(rows)
            if total == 0:
                self.finished.emit(0)
                return

            pred_count = 0
            for idx, row_data in enumerate(rows):
                if self.isInterruptionRequested():
                    break
                art_id = row_data["id"]
                title = row_data["title"]
                summary = row_data["summary"]
                content = row_data["content"]
                self.progress.emit(f"🔮 Прогнозування змін цін акцій ({idx + 1}/{total})…")
                try:
                    pred_val = predict_stock_return(title, summary, content)
                    if pred_val is not None:
                        cursor.execute(
                            "UPDATE articles SET predicted_stock_return = ? WHERE id = ?",
                            (pred_val, art_id)
                        )
                        pred_count += 1
                        
                        if pred_count % 20 == 0:
                            conn.commit()
                except Exception as e:
                    logger.warning("Prediction failed for article %s: %s", art_id, e)
            
            try:
                conn.commit()
            except Exception as e:
                logger.error("Failed final commit in PredictWorker: %s", e)
            self.finished.emit(pred_count)
        except Exception as e:
            logger.error("PredictWorker error: %s", e, exc_info=True)
            self.error.emit(str(e))


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
        self._reclass_worker = None
        self._align_worker = None
        self._train_worker = None
        self._predict_worker = None

        self._init_parsers()
        self._init_ui()
        self._init_menu()
        self._connect_signals()
        self._init_auto_panel()
        self._init_eval_panel()

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
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Tab widget верхнього рівня ──
        from PyQt6.QtWidgets import QTabWidget
        self.top_tabs = QTabWidget()
        self.top_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: #1e1e24;
            }
            QTabBar::tab {
                background: #2b2b36;
                color: #8b8ba3;
                border: none;
                padding: 8px 22px;
                font-size: 11px;
                font-weight: bold;
                min-width: 90px;
            }
            QTabBar::tab:selected {
                background: #1e1e24;
                color: #a29bfe;
                border-bottom: 2px solid #a29bfe;
            }
            QTabBar::tab:hover:!selected { background: #35354a; }
        """)
        root_layout.addWidget(self.top_tabs)

        # ── Вкладка 1: Пошук / Новини ──
        news_tab = QWidget()
        main_layout = QVBoxLayout(news_tab)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Search panel (top)
        self.search_panel = SearchPanel()
        main_layout.addWidget(self.search_panel)

        # Splitter — news list (left) + preview (right)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.news_panel = NewsPanel()
        self.preview_panel = PreviewPanel()
        self.preview_panel.set_database(self.db)

        self.splitter.addWidget(self.news_panel)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setStretchFactor(0, 45)
        self.splitter.setStretchFactor(1, 55)

        main_layout.addWidget(self.splitter, 1)
        self.top_tabs.addTab(news_tab, "🔍  Пошук новин")

        # ── Вкладка 2: Авто-навчання — буде додана в _init_auto_panel() ──

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

    # ── Auto train panel init ──────────────────────────────────────
    def _init_auto_panel(self):
        """Create and add the AutoTrainPanel as the second top-level tab."""
        self.auto_panel = AutoTrainPanel(parsers=self._parsers, db=self.db)
        self.auto_panel.training_finished.connect(self._on_auto_training_finished)
        self.top_tabs.addTab(self.auto_panel, "🤖  Авто")

    def _init_eval_panel(self):
        """Create and add the ModelEvalPanel as the third top-level tab."""
        self.eval_panel = ModelEvalPanel(db=self.db)
        self.top_tabs.addTab(self.eval_panel, "📊  Оцінка моделі")

    def _on_auto_training_finished(self):
        """Called when the auto-train cycle completes — refresh news panel."""
        self._refresh_from_db()
        # Auto-refresh the evaluation panel after training
        if hasattr(self, 'eval_panel'):
            self.eval_panel.refresh()
        self.status_label.setText("Авто-навчання завершено. Список новин оновлено.")

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

        # ── Neural Network Menu ──
        nn_menu = menubar.addMenu("Нейромережа")
        reclassify_action = QAction("Перерахувати релевантність новин", self)
        reclassify_action.triggered.connect(self._reclassify_database)
        nn_menu.addAction(reclassify_action)

        nn_menu.addSeparator()

        align_prices_action = QAction("Зіставити новини з котируваннями акцій", self)
        align_prices_action.triggered.connect(self._align_prices_database)
        nn_menu.addAction(align_prices_action)

        train_predictor_action = QAction("Навчити модель прогнозування (PyTorch)", self)
        train_predictor_action.triggered.connect(self._train_predictor_model)
        nn_menu.addAction(train_predictor_action)

        run_prediction_action = QAction("Спрогнозувати рух акцій", self)
        run_prediction_action.triggered.connect(self._run_predictor_model)
        nn_menu.addAction(run_prediction_action)

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

        self._progress.canceled.connect(self._fetch_worker.requestInterruption)

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

    def _refresh_from_db(self, select_article_id: Optional[str] = None):
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
        
        if select_article_id:
            self.news_panel.select_article_by_id(select_article_id)
            selected_article = next((a for a in articles if a.id == select_article_id), None)
            if selected_article:
                self.preview_panel.show_article(selected_article)
            else:
                self.preview_panel.clear()
        else:
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
    def _reclassify_database(self):
        """Apply the Zero-Shot neural network model to all news in the database."""
        if self._reclass_worker and self._reclass_worker.isRunning():
            QMessageBox.warning(self, "Зайнято", "Перекласифікація вже виконується.")
            return

        reply = QMessageBox.question(
            self, "Перерахунок релевантності",
            "Ви впевнені, що хочете перерахувати релевантність для ВСІХ новин у базі даних за допомогою готової Zero-Shot нейромережі (mDeBERTa)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Progress dialog
        self._reclass_progress = QProgressDialog(
            "Ініціалізація моделі...", "Скасувати", 0, 0, self
        )
        self._reclass_progress.setWindowTitle("Перекласифікація")
        self._reclass_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._reclass_progress.setMinimumDuration(0)
        self._reclass_progress.show()
        
        # Create and start worker
        self._reclass_worker = ReclassifyWorker(self.db, self)
        self._reclass_worker.progress.connect(self._on_reclass_progress)
        self._reclass_worker.finished.connect(self._on_reclass_finished)
        self._reclass_worker.error.connect(self._on_reclass_error)
        
        self._reclass_progress.canceled.connect(self._reclass_worker.requestInterruption)
        
        self._reclass_worker.start()
        self.status_label.setText("Перерахунок релевантності...")

    def _on_reclass_progress(self, message: str):
        if hasattr(self, '_reclass_progress') and self._reclass_progress:
            self._reclass_progress.setLabelText(message)
        self.status_label.setText(message)

    def _on_reclass_finished(self, count: int):
        if hasattr(self, '_reclass_progress') and self._reclass_progress:
            self._reclass_progress.close()
            self._reclass_progress = None
            
        QMessageBox.information(
            self, "Успіх",
            f"Перекласифіковано {count} новин за допомогою Zero-Shot моделі."
        )
        self.status_label.setText(f"Перекласифіковано {count} новин.")
        self._refresh_from_db()

    def _on_reclass_error(self, error_msg: str):
        if hasattr(self, '_reclass_progress') and self._reclass_progress:
            self._reclass_progress.close()
            self._reclass_progress = None
            
        self.status_label.setText(f"Помилка: {error_msg}")
        QMessageBox.critical(self, "Помилка класифікації", error_msg)

    def _align_prices_database(self):
        """Fetch stock prices and align return labels for database news."""
        if self._align_worker and self._align_worker.isRunning():
            QMessageBox.warning(self, "Зайнято", "Зіставлення цін вже виконується.")
            return

        reply = QMessageBox.question(
            self, "Зіставлення котирувань",
            "Ви впевнені, що хочете завантажити ціни акцій та зіставити їх з новинами в базі даних?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._align_progress = QProgressDialog(
            "Підготовка зіставлення...", "Скасувати", 0, 0, self
        )
        self._align_progress.setWindowTitle("Зіставлення цін")
        self._align_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._align_progress.setMinimumDuration(0)
        self._align_progress.show()

        self._align_worker = AlignPricesWorker(self.db, self)
        self._align_worker.progress.connect(self._on_align_progress)
        self._align_worker.finished.connect(self._on_align_finished)
        self._align_worker.error.connect(self._on_align_error)

        self._align_progress.canceled.connect(self._align_worker.requestInterruption)
        self._align_worker.start()
        self.status_label.setText("Завантаження цін та зіставлення...")

    def _on_align_progress(self, message: str):
        if hasattr(self, '_align_progress') and self._align_progress:
            self._align_progress.setLabelText(message)
        self.status_label.setText(message)

    def _on_align_finished(self, count: int):
        if hasattr(self, '_align_progress') and self._align_progress:
            self._align_progress.close()
            self._align_progress = None
        QMessageBox.information(
            self, "Успіх",
            f"Зіставлено {count} новин з реальними цінами акцій та розраховано прибутковість."
        )
        self.status_label.setText(f"Зіставлено {count} новин.")
        self._refresh_from_db()

    def _on_align_error(self, error_msg: str):
        if hasattr(self, '_align_progress') and self._align_progress:
            self._align_progress.close()
            self._align_progress = None
        self.status_label.setText(f"Помилка: {error_msg}")
        QMessageBox.critical(self, "Помилка зіставлення", error_msg)

    def _train_predictor_model(self):
        """Train the PyTorch neural network return predictor model."""
        if self._train_worker and self._train_worker.isRunning():
            QMessageBox.warning(self, "Зайнято", "Навчання моделі вже виконується.")
            return

        reply = QMessageBox.question(
            self, "Навчання моделі",
            "Ви впевнені, що хочете запустити навчання нейромережі на зіставлених даних?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._train_progress = QProgressDialog(
            "Ініціалізація навчання...", "Скасувати", 0, 0, self
        )
        self._train_progress.setWindowTitle("Навчання моделі")
        self._train_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._train_progress.setMinimumDuration(0)
        self._train_progress.show()

        self._train_worker = TrainPredictorWorker(self.db, self)
        self._train_worker.progress.connect(self._on_train_progress)
        self._train_worker.finished.connect(self._on_train_finished)
        self._train_worker.error.connect(self._on_train_error)

        self._train_progress.canceled.connect(self._train_worker.requestInterruption)
        self._train_worker.start()
        self.status_label.setText("Навчання моделі прогнозування...")

    def _on_train_progress(self, message: str):
        if hasattr(self, '_train_progress') and self._train_progress:
            self._train_progress.setLabelText(message)
        self.status_label.setText(message)

    def _on_train_finished(self, summary: str):
        if hasattr(self, '_train_progress') and self._train_progress:
            self._train_progress.close()
            self._train_progress = None
        QMessageBox.information(self, "Навчання завершено", summary)
        self.status_label.setText("Навчання завершено.")
        self._refresh_from_db()

    def _on_train_error(self, error_msg: str):
        if hasattr(self, '_train_progress') and self._train_progress:
            self._train_progress.close()
            self._train_progress = None
        self.status_label.setText(f"Помилка: {error_msg}")
        QMessageBox.critical(self, "Помилка навчання", error_msg)

    def _run_predictor_model(self):
        """Run the stock return predictor on all database news."""
        if self._predict_worker and self._predict_worker.isRunning():
            QMessageBox.warning(self, "Зайнято", "Прогнозування вже виконується.")
            return

        self._predict_progress = QProgressDialog(
            "Підготовка прогнозування...", "Скасувати", 0, 0, self
        )
        self._predict_progress.setWindowTitle("Прогнозування")
        self._predict_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._predict_progress.setMinimumDuration(0)
        self._predict_progress.show()

        self._predict_worker = PredictWorker(self.db, self)
        self._predict_worker.progress.connect(self._on_predict_progress)
        self._predict_worker.finished.connect(self._on_predict_finished)
        self._predict_worker.error.connect(self._on_predict_error)

        self._predict_progress.canceled.connect(self._predict_worker.requestInterruption)
        self._predict_worker.start()
        self.status_label.setText("Прогнозування...")

    def _on_predict_progress(self, message: str):
        if hasattr(self, '_predict_progress') and self._predict_progress:
            self._predict_progress.setLabelText(message)
        self.status_label.setText(message)

    def _on_predict_finished(self, count: int):
        if hasattr(self, '_predict_progress') and self._predict_progress:
            self._predict_progress.close()
            self._predict_progress = None
        QMessageBox.information(
            self, "Успіх",
            f"Спрогнозовано зміни цін для {count} новин."
        )
        self.status_label.setText(f"Спрогнозовано {count} новин.")
        self._refresh_from_db()

    def _on_predict_error(self, error_msg: str):
        if hasattr(self, '_predict_progress') and self._predict_progress:
            self._predict_progress.close()
            self._predict_progress = None
        self.status_label.setText(f"Помилка: {error_msg}")
        QMessageBox.critical(self, "Помилка прогнозування", error_msg)

    def closeEvent(self, event):
        """Ensure background threads are gracefully stopped on exit."""
        # Зупиняємо воркер авто-панелі
        if hasattr(self, 'auto_panel') and self.auto_panel._worker and self.auto_panel._worker.isRunning():
            self.auto_panel._worker.requestInterruption()
            self.auto_panel._worker.wait(5000)

        for worker_name in ['_fetch_worker', '_reclass_worker', '_align_worker', '_train_worker', '_predict_worker']:
            worker = getattr(self, worker_name, None)
            if worker and worker.isRunning():
                worker.requestInterruption()
                if not worker.wait(5000):
                    logger.warning("Worker %s did not stop in time, forcing terminate.", worker_name)
                    worker.terminate()
                    worker.wait(2000)
        self.db.close()
        event.accept()
