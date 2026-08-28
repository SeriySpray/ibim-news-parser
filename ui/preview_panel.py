"""
Панель попереднього перегляду статті та графіку акцій.

Відображає вміст статті та графік котирувань компанії на момент публікації.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser, QSizePolicy, QTabWidget
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt
from core.models import NewsArticle

# Matplotlib integration
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from datetime import datetime, timedelta


class StockChartWidget(QWidget):
    """Віджет для відображення графіка акцій навколо дати новини."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)

        # Matplotlib figure (Dark Theme style matching the app stylesheet)
        self.figure = Figure(facecolor="#1e1e24", layout="constrained")
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor("#1e1e24")
        self.ax.tick_params(colors="#8b8ba3", labelsize=9)
        self.ax.spines['bottom'].set_color('#55556a')
        self.ax.spines['top'].set_color('#55556a')
        self.ax.spines['left'].set_color('#55556a')
        self.ax.spines['right'].set_color('#55556a')

    def plot_stock_around_article(self, db, article):
        """Побудувати графік ціни акції навколо дати публікації статті."""
        self.ax.clear()
        self.ax.set_facecolor("#1e1e24")

        if not db or not article or not article.company_ticker or not article.published_at:
            self.ax.text(
                0.5, 0.5, "Оберіть новину для завантаження графіка котирувань",
                color="#8b8ba3", ha="center", va="center", transform=self.ax.transAxes,
                fontsize=11
            )
            self.canvas.draw()
            return

        ticker = article.company_ticker.upper().strip()
        pub_date = article.published_at.date()
        pub_date_str = pub_date.strftime("%Y-%m-%d")

        conn = db._connect()
        cursor = conn.cursor()

        # Отримуємо ціни за останні 10 днів до та після новини
        cursor.execute(
            """
            SELECT date, open, close, high, low FROM stock_prices
            WHERE ticker = ? AND date >= date(?, '-10 days') AND date <= date(?, '+10 days')
            ORDER BY date ASC
            """,
            (ticker, pub_date_str, pub_date_str)
        )
        rows = cursor.fetchall()

        if not rows:
            self.ax.text(
                0.5, 0.5, f"Немає завантажених котирувань для {ticker}.\n\n"
                          "Скористайтесь меню 'Нейромережа' ->\n"
                          "'Зіставити новини з котируваннями акцій', щоб підвантажити їх.",
                color="#8b8ba3", ha="center", va="center", transform=self.ax.transAxes,
                fontsize=10
            )
            self.canvas.draw()
            return

        dates = []
        closes = []
        opens = []
        for r in rows:
            dates.append(datetime.strptime(r["date"], "%Y-%m-%d").date())
            closes.append(r["close"])
            opens.append(r["open"])

        # Будуємо графік історичних котирувань (як фоновий орієнтир)
        self.ax.plot(
            dates, closes, color="#55557a", linewidth=1.5,
            linestyle=":", marker="o", markersize=3, alpha=0.6, label="Історія Close ($)"
        )

        # Визначаємо найближчу дату з наявних котирувань до дати публікації
        closest_date = min(dates, key=lambda d: abs(d - pub_date))
        closest_idx = dates.index(closest_date)
        closest_price = closes[closest_idx]

        # Підсвічуємо день виходу новини та день торгів на графіку
        if pub_date == closest_date:
            self.ax.axvline(x=pub_date, color="#55556a", linestyle="--", linewidth=1.0, label=f"День новини ({pub_date.strftime('%d.%m')})")
        else:
            # Якщо новина вийшла у вихідний/свято
            self.ax.axvline(x=pub_date, color="#55556a", linestyle=":", linewidth=1.0, label=f"Публікація ({pub_date.strftime('%d.%m')})")
            self.ax.axvline(x=closest_date, color="#55556a", linestyle="--", linewidth=1.0, label=f"Найближчі торги ({closest_date.strftime('%d.%m')})")
            # Малюємо лінію-зв'язку між датою публікації та торговою точкою
            self.ax.plot([pub_date, closest_date], [closest_price, closest_price], color="#ff7675", linestyle=":", alpha=0.5)

        # Визначаємо точки для відображення реальної зміни та прогнозу
        real_ret = getattr(article, "real_stock_return", None) or 0.0
        pred_ret = getattr(article, "predicted_stock_return", None) or 0.0

        base_date = None
        base_price = None
        target_date = None
        target_price = None

        if real_ret != 0.0:
            # Варіант 1: t та t+1 (Close to Close)
            if closest_idx + 1 < len(dates):
                calc_val = ((closes[closest_idx + 1] - closes[closest_idx]) / closes[closest_idx]) * 100.0
                if abs(calc_val - real_ret) < 0.05:
                    base_date = closest_date
                    base_price = closes[closest_idx]
                    target_date = dates[closest_idx + 1]
                    target_price = closes[closest_idx + 1]

            # Варіант 2: t-1 та t (Close to Close)
            if base_price is None and closest_idx > 0:
                calc_val = ((closes[closest_idx] - closes[closest_idx - 1]) / closes[closest_idx - 1]) * 100.0
                if abs(calc_val - real_ret) < 0.05:
                    base_date = dates[closest_idx - 1]
                    base_price = closes[closest_idx - 1]
                    target_date = closest_date
                    target_price = closes[closest_idx]

            # Варіант 3: t (Open to Close)
            if base_price is None:
                calc_val = ((closes[closest_idx] - opens[closest_idx]) / opens[closest_idx]) * 100.0
                if abs(calc_val - real_ret) < 0.05:
                    base_date = closest_date
                    base_price = opens[closest_idx]
                    target_date = closest_date
                    target_price = closes[closest_idx]

        # Резервний варіант, якщо не знайшли точного збігу або real_ret відсутній
        if base_price is None:
            base_date = closest_date
            base_price = closest_price
            if closest_idx + 1 < len(dates):
                target_date = dates[closest_idx + 1]
                target_price = closes[closest_idx + 1]
            elif closest_idx > 0:
                target_date = closest_date
                target_price = closest_price
                base_date = dates[closest_idx - 1]
                base_price = closes[closest_idx - 1]
            else:
                target_date = closest_date
                target_price = closest_price

        # Малюємо реальну зміну (жирна лінія з колірним кодуванням)
        real_color = "#00cec9" if real_ret >= 0.0 else "#ff7675"
        self.ax.plot(
            [base_date, target_date], [base_price, target_price],
            color=real_color, linewidth=3.5, marker="o", markersize=8,
            label=f"Реально: {real_ret:+.2f}%" if real_ret != 0.0 else "Реально (Close)"
        )

        # Малюємо прогнозовану зміну, якщо вона розрахована
        if pred_ret != 0.0:
            pred_price = base_price * (1.0 + pred_ret / 100.0)
            pred_color = "#fdcb6e"  # Теплий жовтий/золотий
            self.ax.plot(
                [base_date, target_date], [base_price, pred_price],
                color=pred_color, linestyle="--", linewidth=2.5, marker="X", markersize=8,
                label=f"Прогноз: {pred_ret:+.2f}%"
            )

        # Додаємо анотацію з початковою ціною виходу новини
        self.ax.plot(closest_date, closest_price, color="#ff7675", marker="*", markersize=12)
        self.ax.annotate(
            f"${closest_price:.2f}",
            xy=(closest_date, closest_price),
            xytext=(12, -8),
            textcoords="offset points",
            color="#ff7675",
            fontweight="bold",
            fontsize=10,
            bbox=dict(facecolor='#2b2b36', alpha=0.8, edgecolor='#ff7675', boxstyle='round,pad=0.2')
        )

        # Оформлення графіка
        self.ax.set_title(f"Динаміка акцій {ticker} навколо дати публікації", color="#f0f0f5", fontsize=11, pad=10)
        self.ax.set_ylabel("Ціна ($)", color="#8b8ba3", fontsize=9)
        self.ax.grid(True, color="#2b2b36", linestyle=":")

        # Форматування осі X
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
        self.ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
        
        # Налаштовуємо ліміти осі X так, щоб включати і дату публікації, і всі торгові дні
        all_dates = dates + [pub_date]
        self.ax.set_xlim(min(all_dates) - timedelta(days=1), max(all_dates) + timedelta(days=1))
        
        self.figure.autofmt_xdate()

        # Додавання інформації про релевантність, тональність та прогноз
        info_lines = []
        real_ret = getattr(article, "real_stock_return", None) or 0.0
        pred_ret = getattr(article, "predicted_stock_return", None) or 0.0
        impact = getattr(article, "impact", 0.0)

        info_lines.append(f"Вплив тональності (FinBERT): {impact:+.2f}")
        if real_ret != 0.0:
            info_lines.append(f"Реальна зміна акцій: {real_ret:+.2f}%")
        if pred_ret != 0.0:
            info_lines.append(f"Прогноз нейромережі: {pred_ret:+.2f}%")

        if pub_date != closest_date:
            info_lines.append(f"\n*Вихідний/свято ({pub_date.strftime('%d.%m')})")
            info_lines.append(f"Реакцію ринку взято за {closest_date.strftime('%d.%m')}")

        text_str = "\n".join(info_lines)
        self.ax.text(
            0.03, 0.97, text_str, color="#f0f0f5", fontsize=9,
            bbox=dict(facecolor='#2b2b36', alpha=0.9, edgecolor='#55556a', boxstyle='round,pad=0.6'),
            transform=self.ax.transAxes, verticalalignment='top'
        )

        self.ax.legend(facecolor="#2b2b36", edgecolor="#55556a", labelcolor="#f0f0f5", fontsize=9)
        self.canvas.draw()


class PreviewPanel(QWidget):
    """Панель перегляду обраної статті та вкладкою з графіком акцій."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_article = None
        self.db = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Заголовок
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(14)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #f0f0f5;")
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

        # 3. Вкладки (Вміст новини та Графік акцій)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::panel {
                border: 1px solid #55556a;
                background-color: #1e1e24;
            }
            QTabBar::tab {
                background-color: #2b2b36;
                color: #8b8ba3;
                border: 1px solid #55556a;
                padding: 6px 14px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e24;
                color: #f0f0f5;
                border-bottom-color: #1e1e24;
            }
        """)

        # Вкладка 1: Текстовий переглядач
        self.content_browser = QTextBrowser()
        self.content_browser.setOpenExternalLinks(True)
        self.content_browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tabs.addTab(self.content_browser, "Вміст новини")

        # Вкладка 2: Графік акцій
        self.chart_widget = StockChartWidget(self)
        self.tabs.addTab(self.chart_widget, "Динаміка акцій")

        layout.addWidget(self.tabs)

        # Початковий стан — заповнювач
        self.clear()

    def set_database(self, db):
        """Зберегти посилання на базу даних для роботи з котируваннями."""
        self.db = db

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
        """Відобразити обрану статтю та її графік."""
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

        # Побудова графіка
        if self.db:
            self.chart_widget.plot_stock_around_article(self.db, article)
        else:
            self.chart_widget.plot_stock_around_article(None, None)

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
            'Оберіть новину для перегляду</p>'
        )
        self.chart_widget.plot_stock_around_article(None, None)
