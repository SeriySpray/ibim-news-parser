"""
IBIM News Parser — Панель автоматичного навчання.

Дозволяє вибрати випадкову або задану компанію та часовий діапазон,
а потім автоматично виконати весь цикл:
  1. Завантаження новин (всі парсери)
  2. Зіставлення котирувань (Yahoo Finance)
  3. Навчання нейромережі
"""

import logging
import random
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QComboBox, QSpinBox, QGroupBox, QGridLayout,
    QProgressBar, QCheckBox, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QFont, QColor

logger = logging.getLogger(__name__)

# ── Список популярних компаній для випадкового вибору ──────────────
POPULAR_COMPANIES = [
    ("AAPL",  "Apple"),
    ("MSFT",  "Microsoft"),
    ("GOOGL", "Alphabet"),
    ("AMZN",  "Amazon"),
    ("TSLA",  "Tesla"),
    ("NVDA",  "NVIDIA"),
    ("META",  "Meta Platforms"),
    ("NFLX",  "Netflix"),
    ("AMD",   "AMD"),
    ("INTC",  "Intel"),
    ("BABA",  "Alibaba"),
    ("ORCL",  "Oracle"),
    ("SHOP",  "Shopify"),
    ("UBER",  "Uber"),
    ("SNAP",  "Snap"),
    ("COIN",  "Coinbase"),
    ("PLTR",  "Palantir"),
    ("RBLX",  "Roblox"),
    ("SPOT",  "Spotify"),
    ("SQ",    "Block"),
]


class AutoTrainWorker(QThread):
    """Фоновий потік повного циклу автоматичного навчання."""

    log_message = pyqtSignal(str)     # рядок логу
    stage_changed = pyqtSignal(int)   # 0-3: поточний етап
    finished = pyqtSignal(bool, str)  # success, summary
    progress_val = pyqtSignal(int)    # 0..100

    def __init__(self, parsers, ticker: str, company_name: str,
                 date_from: datetime, date_to: datetime,
                 run_align: bool, run_train: bool, parent=None):
        super().__init__(parent)
        self.parsers = parsers
        self.ticker = ticker
        self.company_name = company_name
        self.date_from = date_from
        self.date_to = date_to
        self.run_align = run_align
        self.run_train = run_train

    def _log(self, msg: str):
        logger.info(msg)
        self.log_message.emit(msg)

    def run(self):
        try:
            from core.database import Database
            from core.scraper import scrape_article_text
            from core.analyzer import FinancialAnalyzer
            from core.classifier import NewsClassifierZeroShot

            db = Database()

            # ── Етап 1: Завантаження новин ─────────────────────────
            self.stage_changed.emit(1)
            self._log(f"━━━ Етап 1/3: Завантаження новин ({self.ticker} / {self.company_name}) ━━━")
            self._log(f"  Діапазон: {self.date_from.strftime('%d.%m.%Y')} – {self.date_to.strftime('%d.%m.%Y')}")

            all_articles = []
            for parser in self.parsers:
                if self.isInterruptionRequested():
                    self.finished.emit(False, "Скасовано користувачем.")
                    return
                source_name = parser.get_source_name()
                if not parser.is_configured():
                    self._log(f"  ⏭ {source_name}: не налаштовано, пропускаємо")
                    continue
                try:
                    self._log(f"  🔄 {source_name}…")
                    articles = parser.fetch_news(
                        self.ticker, self.company_name,
                        self.date_from, self.date_to
                    )
                    all_articles.extend(articles)
                    self._log(f"  ✅ {source_name}: {len(articles)} новин")
                except Exception as e:
                    self._log(f"  ❌ {source_name}: {e}")

            if not all_articles:
                self.finished.emit(False, "Парсери не повернули жодної новини. Перевірте API-ключі або спробуйте іншу компанію.")
                return

            self._log(f"\n  📰 Всього знайдено: {len(all_articles)} новин. Скрапінг тексту…")
            self.progress_val.emit(15)

            scraped = []
            for i, article in enumerate(all_articles):
                if self.isInterruptionRequested():
                    self.finished.emit(False, "Скасовано користувачем.")
                    return
                try:
                    text = scrape_article_text(article.source_url)
                    if text and len(text) > len(article.content or ""):
                        article.content = text
                except Exception:
                    pass
                scraped.append(article)
                if (i + 1) % 5 == 0:
                    self._log(f"  🌐 Скрапінг: {i + 1}/{len(all_articles)}")
            all_articles = scraped
            self.progress_val.emit(30)

            # ── Аналіз тональності та релевантності ────────────────
            self._log("\n  🧠 Підготовка AI-моделей (перше завантаження може зайняти 2–10 хв)…")

            # Ініціалізуємо FinBERT окремо з явним повідомленням
            analyzer = FinancialAnalyzer()
            try:
                self._log("  ⏳ Завантаження FinBERT (ProsusAI/finbert)…")
                analyzer._lazy_init()
                self._log("  ✅ FinBERT готовий.")
            except Exception as e:
                self._log(f"  ❌ FinBERT не вдалося завантажити: {e}. Тональність буде 0.")
                analyzer = None

            if self.isInterruptionRequested():
                self.finished.emit(False, "Скасовано користувачем.")
                return

            # Ініціалізуємо Zero-Shot (mDeBERTa) окремо з явним повідомленням
            zeroshot = NewsClassifierZeroShot()
            use_zeroshot = False
            try:
                self._log("  ⏳ Завантаження Zero-Shot класифікатора (mDeBERTa, ~1 ГБ)…")
                zeroshot._lazy_init()
                use_zeroshot = True
                self._log("  ✅ mDeBERTa готовий.")
            except Exception as e:
                self._log(f"  ⚠️ mDeBERTa не вдалося завантажити: {e}. Релевантність буде розрахована локально.")

            if self.isInterruptionRequested():
                self.finished.emit(False, "Скасовано користувачем.")
                return

            total_art = len(all_articles)
            self._log(f"\n  📊 Аналіз {total_art} статей…")
            for i, article in enumerate(all_articles):
                if self.isInterruptionRequested():
                    self.finished.emit(False, "Скасовано користувачем.")
                    return

                # Прогрес кожну статтю
                pct = 30 + int(20 * (i + 1) / max(total_art, 1))
                self.progress_val.emit(pct)
                self._log(f"  🔬 [{i + 1}/{total_art}] {article.title[:60]}…")

                # Релевантність
                if use_zeroshot:
                    try:
                        article.relevance = zeroshot.predict(
                            article.title,
                            article.content or article.summary or "",
                            self.company_name or self.ticker
                        )
                    except Exception as e:
                        logger.warning("Zero-shot failed for article %d: %s", i, e)
                else:
                    # Локальний fallback
                    try:
                        from core.analyzer import calculate_relevance
                        article.relevance = calculate_relevance(
                            article.title, article.content or article.summary or "",
                            self.ticker, self.company_name
                        )
                    except Exception:
                        pass

                # Тональність
                if analyzer is not None:
                    try:
                        text_sent = (article.title or "") + ". " + (article.summary or article.content or "")
                        article.impact = analyzer.analyze_sentiment(text_sent)
                    except Exception as e:
                        logger.warning("FinBERT failed for article %d: %s", i, e)

            self._log(f"  ✅ Аналіз завершено: {total_art} статей.")

            # ── Збереження в БД ─────────────────────────────────────
            self._log("\n  💾 Збереження новин у базу даних…")
            new_count = 0
            for article in all_articles:
                # ⚠️ Обов'язково проставляємо тікер та назву компанії перед збереженням
                article.company_ticker = self.ticker.upper()
                article.company_name = self.company_name
                # Скидаємо real_stock_return до None щоб запит зіставлення знайшов статтю
                article.real_stock_return = None
                if not db.article_exists(article.source_url):
                    if db.insert_article(article):
                        new_count += 1
                else:
                    # Оновлюємо тікер на випадок, якщо стаття вже є в БД без нього
                    try:
                        conn_upd = db._connect()
                        conn_upd.execute(
                            "UPDATE articles SET company_ticker = ?, company_name = ? WHERE source_url = ? AND (company_ticker = '' OR company_ticker IS NULL)",
                            (self.ticker.upper(), self.company_name, article.source_url)
                        )
                        conn_upd.commit()
                    except Exception as e:
                        logger.warning("Failed to update ticker on existing article: %s", e)
            self._log(f"  ✅ Збережено {new_count} нових / {len(all_articles)} всього")
            self.progress_val.emit(60)

            if new_count == 0 and not self.run_align:
                self.finished.emit(True, f"Всі {len(all_articles)} новин вже були в базі. Нових немає.")
                return

            # ── Етап 2: Зіставлення котирувань ──────────────────────
            if self.run_align:
                self.stage_changed.emit(2)
                self._log(f"\n━━━ Етап 2/3: Зіставлення котирувань ({self.ticker}) ━━━")
                from core.market_data import align_article_with_return

                conn = db._connect()
                cursor = conn.cursor()
                # Шукаємо статті цього тікера, у яких ще не зіставлені котирування.
                # real_stock_return IS NULL — нові статті (після нашого виправлення)
                # real_stock_return = 0.0  — старі статті збережені зі значенням за замовчуванням
                cursor.execute(
                    """
                    SELECT id FROM articles
                    WHERE UPPER(company_ticker) = UPPER(?)
                      AND (real_stock_return IS NULL OR real_stock_return = 0.0)
                    """,
                    (self.ticker,)
                )
                ids_to_align = [row["id"] for row in cursor.fetchall()]
                self._log(f"  📈 Статей для зіставлення: {len(ids_to_align)}")

                aligned = 0
                for i, art_id in enumerate(ids_to_align):
                    if self.isInterruptionRequested():
                        self.finished.emit(False, "Скасовано користувачем.")
                        return
                    try:
                        res = align_article_with_return(db, art_id)
                        if res is not None:
                            aligned += 1
                    except Exception as e:
                        logger.warning("Align failed for %s: %s", art_id, e)
                    if (i + 1) % 10 == 0:
                        self._log(f"  📈 Зіставлено: {i + 1}/{len(ids_to_align)}")

                self._log(f"  ✅ Зіставлено котирувань: {aligned}/{len(ids_to_align)}")
                self.progress_val.emit(80)
            else:
                self._log("\n  ⏭ Зіставлення котирувань пропущено (вимкнено)")
                self.progress_val.emit(80)

            # ── Етап 3: Навчання моделі ──────────────────────────────
            if self.run_train:
                self.stage_changed.emit(3)
                self._log(f"\n━━━ Етап 3/3: Навчання нейромережі (PyTorch) ━━━")
                from core.predictor import train_predictor_model
                result = train_predictor_model(db, progress_callback=self._log)
                self._log(f"  🤖 {result}")
                self.progress_val.emit(100)
            else:
                self._log("\n  ⏭ Навчання моделі пропущено (вимкнено)")
                self.progress_val.emit(100)

            summary = (
                f"✅ Завершено!\n"
                f"  Компанія: {self.ticker} / {self.company_name}\n"
                f"  Новин збережено: {new_count}\n"
            )
            self.finished.emit(True, summary)

        except Exception as e:
            logger.error("AutoTrainWorker critical error: %s", e, exc_info=True)
            self.finished.emit(False, f"Критична помилка: {e}")


# ════════════════════════════════════════════════════════════════════
#  AutoTrainPanel — вкладка «Авто»
# ════════════════════════════════════════════════════════════════════

class AutoTrainPanel(QWidget):
    """Панель автоматичного циклу: вибір компанії → навчання."""

    # Сигнал для оновлення головного вікна після завершення
    training_finished = pyqtSignal()

    def __init__(self, parsers: list, db, parent=None):
        super().__init__(parent)
        self.parsers = parsers
        self.db = db
        self._worker: AutoTrainWorker = None
        self._init_ui()

    # ── Побудова UI ────────────────────────────────────────────────

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ── Заголовок ──
        title = QLabel("🤖  Автоматичне навчання")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: #a29bfe;")
        root.addWidget(title)

        desc = QLabel(
            "Оберіть компанію та часовий діапазон — програма самостійно завантажить новини,\n"
            "зіставить котирування акцій та навчить нейромережу прогнозування."
        )
        desc.setStyleSheet("color: #8b8ba3; font-size: 10px;")
        root.addWidget(desc)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #55556a;")
        root.addWidget(separator)

        # ── Налаштування (сітка 2 колонки) ──
        cfg_group = QGroupBox("Налаштування циклу")
        cfg_group.setStyleSheet("""
            QGroupBox {
                color: #f0f0f5;
                border: 1px solid #55556a;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)
        grid = QGridLayout(cfg_group)
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        # Компанія
        grid.addWidget(self._lbl("Компанія:"), 0, 0)
        self.company_combo = QComboBox()
        self.company_combo.setEditable(True)
        self.company_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.company_combo.setPlaceholderText("Введіть тікер або оберіть зі списку…")
        for ticker, name in POPULAR_COMPANIES:
            self.company_combo.addItem(f"{ticker} — {name}", userData=(ticker, name))
        self.company_combo.setCurrentIndex(-1)
        self.company_combo.setStyleSheet(self._combo_style())
        grid.addWidget(self.company_combo, 0, 1)

        # Кнопка «Рандомна компанія»
        self.random_company_btn = QPushButton("🎲 Випадкова")
        self.random_company_btn.setToolTip("Обрати випадкову компанію зі списку")
        self.random_company_btn.setStyleSheet(self._btn_secondary_style())
        self.random_company_btn.clicked.connect(self._pick_random_company)
        grid.addWidget(self.random_company_btn, 0, 2)

        # Діапазон
        grid.addWidget(self._lbl("Діапазон:"), 1, 0)
        months_layout = QHBoxLayout()
        self.period_spin = QSpinBox()
        self.period_spin.setStyleSheet(self._spin_style())
        months_layout.addWidget(self.period_spin)

        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["дн.", "тиж.", "міс."])
        self.unit_combo.setStyleSheet(self._combo_style())
        self.unit_combo.setFixedWidth(80)
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        months_layout.addWidget(self.unit_combo)

        # Встановити за замовчуванням 1 місяць
        self.unit_combo.setCurrentIndex(2)
        self.period_spin.setValue(1)

        self.random_period_btn = QPushButton("🎲 Рандомний")
        self.random_period_btn.setToolTip("Обрати випадковий період за останній рік")
        self.random_period_btn.setStyleSheet(self._btn_secondary_style())
        self.random_period_btn.clicked.connect(self._pick_random_period)
        months_layout.addWidget(self.random_period_btn)
        months_layout.addStretch()
        months_container = QWidget()
        months_container.setLayout(months_layout)
        grid.addWidget(months_container, 1, 1, 1, 2)

        # Ітерацій
        grid.addWidget(self._lbl("Кількість ітерацій:"), 2, 0)
        iter_layout = QHBoxLayout()
        self.iters_spin = QSpinBox()
        self.iters_spin.setRange(1, 50)
        self.iters_spin.setValue(1)
        self.iters_spin.setSuffix(" шт.")
        self.iters_spin.setToolTip("Скільки разів поспіль запускати цикл (рандомна компанія/період щоразу)")
        self.iters_spin.setStyleSheet(self._spin_style())
        iter_layout.addWidget(self.iters_spin)
        iter_layout.addWidget(self._lbl("  (кожна ітерація — нова компанія/період)"))
        iter_layout.addStretch()
        iter_container = QWidget()
        iter_container.setLayout(iter_layout)
        grid.addWidget(iter_container, 2, 1, 1, 2)

        root.addWidget(cfg_group)

        # ── Чекбокси етапів ──
        steps_group = QGroupBox("Виконувані етапи")
        steps_group.setStyleSheet(cfg_group.styleSheet())
        steps_layout = QHBoxLayout(steps_group)
        steps_layout.setSpacing(24)

        self.cb_fetch = QCheckBox("📰 Завантажити новини")
        self.cb_fetch.setChecked(True)
        self.cb_fetch.setEnabled(False)  # завжди увімкнено
        self.cb_fetch.setStyleSheet("color: #f0f0f5;")

        self.cb_align = QCheckBox("📈 Зіставити котирування")
        self.cb_align.setChecked(True)
        self.cb_align.setStyleSheet("color: #f0f0f5;")

        self.cb_train = QCheckBox("🤖 Навчити нейромережу")
        self.cb_train.setChecked(True)
        self.cb_train.setStyleSheet("color: #f0f0f5;")

        steps_layout.addWidget(self.cb_fetch)
        steps_layout.addWidget(self.cb_align)
        steps_layout.addWidget(self.cb_train)
        steps_layout.addStretch()
        root.addWidget(steps_group)

        # ── Кнопки запуску ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.start_btn = QPushButton("▶  Запустити")
        self.start_btn.setFixedHeight(38)
        self.start_btn.setObjectName("accentButton")
        self.start_btn.clicked.connect(self._on_start)

        self.random_all_btn = QPushButton("🎲  Повністю рандомний запуск")
        self.random_all_btn.setFixedHeight(38)
        self.random_all_btn.setStyleSheet(self._btn_accent2_style())
        self.random_all_btn.setToolTip("Рандомна компанія + рандомний місяць, запустити одразу")
        self.random_all_btn.clicked.connect(self._on_random_all)

        self.stop_btn = QPushButton("⏹  Зупинити")
        self.stop_btn.setFixedHeight(38)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(self._btn_danger_style())
        self.stop_btn.clicked.connect(self._on_stop)

        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.random_all_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── Індикатор прогресу ──
        progress_row = QHBoxLayout()
        self.stage_label = QLabel("Очікування запуску…")
        self.stage_label.setStyleSheet("color: #8b8ba3; font-size: 10px;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2b2b36;
                border: 1px solid #55556a;
                border-radius: 4px;
                color: #f0f0f5;
                font-size: 9px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6c5ce7, stop:1 #a29bfe);
                border-radius: 3px;
            }
        """)

        progress_row.addWidget(self.stage_label, 1)
        progress_row.addWidget(self.progress_bar, 2)
        root.addLayout(progress_row)

        # ── Лог ──
        log_label = QLabel("Журнал виконання:")
        log_label.setStyleSheet("color: #8b8ba3; font-size: 10px; font-weight: bold;")
        root.addWidget(log_label)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Consolas", 9))
        self.log_box.setStyleSheet("""
            QTextEdit {
                background-color: #12121a;
                color: #c8c8e8;
                border: 1px solid #55556a;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        self.log_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.log_box, 1)

    # ── Хелпери стилів ────────────────────────────────────────────

    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #b2b2c8;")
        return lbl

    @staticmethod
    def _combo_style() -> str:
        return """
            QComboBox {
                background-color: #2b2b36;
                color: #f0f0f5;
                border: 1px solid #55556a;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #2b2b36;
                color: #f0f0f5;
                selection-background-color: #6c5ce7;
            }
        """

    @staticmethod
    def _spin_style() -> str:
        return """
            QSpinBox {
                background-color: #2b2b36;
                color: #f0f0f5;
                border: 1px solid #55556a;
                border-radius: 4px;
                padding: 3px 6px;
                min-width: 90px;
            }
        """

    @staticmethod
    def _btn_secondary_style() -> str:
        return """
            QPushButton {
                background-color: #2b2b36;
                color: #a29bfe;
                border: 1px solid #6c5ce7;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #3b3b50; }
            QPushButton:pressed { background-color: #6c5ce7; color: #fff; }
        """

    @staticmethod
    def _btn_accent2_style() -> str:
        return """
            QPushButton {
                background-color: #00b894;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 5px 16px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #00cec9; }
            QPushButton:pressed { background-color: #00a381; }
            QPushButton:disabled { background-color: #2b2b36; color: #55556a; }
        """

    @staticmethod
    def _btn_danger_style() -> str:
        return """
            QPushButton {
                background-color: #2b2b36;
                color: #ff7675;
                border: 1px solid #ff7675;
                border-radius: 4px;
                padding: 5px 14px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #3b2b2b; }
            QPushButton:pressed { background-color: #ff7675; color: #fff; }
            QPushButton:disabled { background-color: #2b2b36; color: #55556a; border-color: #55556a; }
        """

    def _on_unit_changed(self):
        unit = self.unit_combo.currentText()
        if unit == "дн.":
            self.period_spin.setRange(1, 365)
            self.period_spin.setSuffix(" дн.")
        elif unit == "тиж.":
            self.period_spin.setRange(1, 52)
            self.period_spin.setSuffix(" тиж.")
        else: # "міс."
            self.period_spin.setRange(1, 24)
            self.period_spin.setSuffix(" міс.")

    # ── Логіка рандомного вибору ───────────────────────────────────

    def _pick_random_company(self):
        idx = random.randint(0, len(POPULAR_COMPANIES) - 1)
        self.company_combo.setCurrentIndex(idx)
        ticker, name = POPULAR_COMPANIES[idx]
        self._append_log(f"🎲 Рандомна компанія: {ticker} — {name}")

    def _pick_random_period(self):
        """Вибрати рандомний період у межах останнього року."""
        unit_idx = random.choice([0, 1, 2]) # 0: дн., 1: тиж., 2: міс.
        self.unit_combo.setCurrentIndex(unit_idx)
        if unit_idx == 0:
            val = random.randint(3, 28)
            log_unit = "дн."
        elif unit_idx == 1:
            val = random.randint(1, 3)
            log_unit = "тиж."
        else:
            val = random.randint(1, 12)
            log_unit = "міс."
        self.period_spin.setValue(val)
        self._append_log(f"🎲 Рандомний діапазон: {val} {log_unit} тому")

    # ── Запуск ────────────────────────────────────────────────────

    def _get_ticker_name(self) -> tuple[str, str]:
        """Повернути (ticker, company_name) з поточного вибору."""
        idx = self.company_combo.currentIndex()
        if idx >= 0:
            data = self.company_combo.itemData(idx)
            if data:
                return data
        # Якщо введено вручну
        raw = self.company_combo.currentText().strip()
        if " — " in raw:
            parts = raw.split(" — ", 1)
            return parts[0].strip().upper(), parts[1].strip()
        return raw.upper(), raw

    def _get_date_range(self) -> tuple[datetime, datetime]:
        val = self.period_spin.value()
        unit = self.unit_combo.currentText()
        if unit == "дн.":
            days = val
        elif unit == "тиж.":
            days = val * 7
        else: # "міс."
            days = val * 30
        
        date_to = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)
        date_from = (date_to - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        return date_from, date_to

    def _on_random_all(self):
        self._pick_random_company()
        self._pick_random_period()
        self._on_start()

    def _on_start(self):
        if self._worker and self._worker.isRunning():
            self._append_log("⚠️ Цикл вже виконується. Зачекайте або зупиніть його.")
            return

        ticker, name = self._get_ticker_name()
        if not ticker:
            self._append_log("❌ Оберіть або введіть компанію.")
            return

        date_from, date_to = self._get_date_range()
        iters = self.iters_spin.value()

        self._append_log(
            f"\n{'═'*55}\n"
            f"🚀 ЗАПУСК АВТОЦИКЛУ\n"
            f"  Компанія : {ticker} — {name}\n"
            f"  Діапазон : {date_from.strftime('%d.%m.%Y')} – {date_to.strftime('%d.%m.%Y')}\n"
            f"  Ітерацій : {iters}\n"
            f"  Зіставлення: {'✅' if self.cb_align.isChecked() else '❌'}  "
            f"Навчання: {'✅' if self.cb_train.isChecked() else '❌'}\n"
            f"{'═'*55}"
        )

        self._current_iter = 0
        self._total_iters = iters
        self._base_ticker = ticker
        self._base_name = name
        self._base_date_from = date_from
        self._base_date_to = date_to

        self._launch_iteration(ticker, name, date_from, date_to)

    def _launch_iteration(self, ticker: str, name: str, date_from: datetime, date_to: datetime):
        self._worker = AutoTrainWorker(
            parsers=self.parsers,
            ticker=ticker,
            company_name=name,
            date_from=date_from,
            date_to=date_to,
            run_align=self.cb_align.isChecked(),
            run_train=self.cb_train.isChecked(),
        )
        self._worker.log_message.connect(self._append_log)
        self._worker.stage_changed.connect(self._on_stage_changed)
        self._worker.progress_val.connect(self.progress_bar.setValue)
        self._worker.finished.connect(self._on_iter_finished)

        self.start_btn.setEnabled(False)
        self.random_all_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)

        self._worker.start()

    def _on_iter_finished(self, success: bool, summary: str):
        self._current_iter += 1
        status = "✅" if success else "❌"
        self._append_log(f"\n{status} Ітерація {self._current_iter}/{self._total_iters}: {summary}")

        if self._current_iter < self._total_iters:
            # Наступна ітерація — рандомна компанія і рандомний період
            ticker, name = random.choice(POPULAR_COMPANIES)
            unit_type = random.choice(["days", "weeks", "months"])
            if unit_type == "days":
                val = random.randint(3, 28)
                days = val
                log_period = f"{val} дн."
            elif unit_type == "weeks":
                val = random.randint(1, 3)
                days = val * 7
                log_period = f"{val} тиж."
            else:
                val = random.randint(1, 12)
                days = val * 30
                log_period = f"{val} міс."
                
            date_to = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)
            date_from = (date_to - timedelta(days=days)).replace(hour=0, minute=0, second=0)
            self._append_log(
                f"\n--- Наступна ітерація: {ticker} ({name}), {log_period} тому ---"
            )
            self._launch_iteration(ticker, name, date_from, date_to)
        else:
            self._append_log(f"\n{'═'*55}\n🏁 Всі {self._total_iters} ітерацій завершено.\n{'═'*55}")
            self.start_btn.setEnabled(True)
            self.random_all_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.stage_label.setText("Завершено ✅")
            self.training_finished.emit()

    def _on_stage_changed(self, stage: int):
        labels = {
            1: "⏳ Етап 1/3: Завантаження новин…",
            2: "⏳ Етап 2/3: Зіставлення котирувань…",
            3: "⏳ Етап 3/3: Навчання нейромережі…",
        }
        self.stage_label.setText(labels.get(stage, ""))

    def _on_stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._append_log("\n⏹ Зупинка після поточної операції…")
            self.stop_btn.setEnabled(False)
            self._current_iter = self._total_iters  # не запускати наступних ітерацій

    def _append_log(self, text: str):
        self.log_box.append(text)
        # Авто-скрол вниз
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())
