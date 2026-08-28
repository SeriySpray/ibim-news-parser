"""
IBIM News Parser — Панель оцінки навченої моделі.

Показує метрики якості, графіки (scatter, гістограма помилок),
та таблицю найкращих / найгірших прогнозів.
"""

import logging
import math
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
    QGroupBox, QGridLayout, QSplitter, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)


class ModelEvalPanel(QWidget):
    """Вкладка «📊 Оцінка моделі» — показує, чого навчилася нейромережа."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._init_ui()

    # ── UI ─────────────────────────────────────────────────────────────

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        title_lbl = QLabel("📊  Оцінка якості моделі")
        title_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #f0f0f5;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        self.refresh_btn = QPushButton("🔄 Оновити")
        self.refresh_btn.setFixedWidth(130)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background: #6c5ce7; color: white; border: none;
                padding: 8px 16px; border-radius: 6px; font-weight: bold;
            }
            QPushButton:hover { background: #7d6ff0; }
        """)
        self.refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(self.refresh_btn)
        root.addLayout(header_layout)

        # ── Info label (показується якщо немає даних) ──────────────────
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #8b8ba3; font-size: 12px;")
        self.info_label.setWordWrap(True)
        root.addWidget(self.info_label)

        # ── Metrics cards ─────────────────────────────────────────────
        self.metrics_group = QGroupBox("Метрики якості")
        self.metrics_group.setStyleSheet("""
            QGroupBox {
                color: #a29bfe; font-weight: bold; font-size: 12px;
                border: 1px solid #35354a; border-radius: 8px;
                margin-top: 6px; padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 12px; padding: 0 6px;
            }
        """)
        metrics_grid = QGridLayout(self.metrics_group)
        metrics_grid.setSpacing(12)

        self._metric_labels = {}
        metric_defs = [
            ("samples",   "📦 Зразків"),
            ("mae",       "📏 MAE"),
            ("rmse",      "📐 RMSE"),
            ("r2",        "📈 R²"),
            ("dir_acc",   "🎯 Напрямок"),
            ("corr",      "🔗 Кореляція"),
        ]
        for col, (key, caption) in enumerate(metric_defs):
            card = self._make_metric_card(caption)
            metrics_grid.addWidget(card, 0, col)
            # value label — third child in the card layout
            self._metric_labels[key] = card.findChild(QLabel, f"val_{key}")

        root.addWidget(self.metrics_group)

        # ── Charts + Table  ───────────────────────────────────────────
        body_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: charts (stacked vertically)
        charts_widget = QWidget()
        charts_layout = QVBoxLayout(charts_widget)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(4)

        # Scatter plot
        self.scatter_fig = Figure(facecolor="#1e1e24", layout="constrained")
        self.scatter_canvas = FigureCanvas(self.scatter_fig)
        self.scatter_ax = self.scatter_fig.add_subplot(111)
        charts_layout.addWidget(self.scatter_canvas, 1)

        # Error histogram
        self.hist_fig = Figure(facecolor="#1e1e24", layout="constrained")
        self.hist_canvas = FigureCanvas(self.hist_fig)
        self.hist_ax = self.hist_fig.add_subplot(111)
        charts_layout.addWidget(self.hist_canvas, 1)

        body_splitter.addWidget(charts_widget)

        # Right: table of predictions
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.setContentsMargins(0, 0, 0, 0)

        tbl_label = QLabel("Прогнози (сортовані за помилкою)")
        tbl_label.setStyleSheet("color: #a29bfe; font-weight: bold; font-size: 11px; padding: 4px;")
        table_layout.addWidget(tbl_label)

        self.pred_table = QTableWidget()
        self.pred_table.setColumnCount(5)
        self.pred_table.setHorizontalHeaderLabels([
            "Заголовок", "Реал. %", "Прогноз %", "Помилка", "Напрямок"
        ])
        self.pred_table.setColumnWidth(0, 260)
        self.pred_table.setColumnWidth(1, 75)
        self.pred_table.setColumnWidth(2, 85)
        self.pred_table.setColumnWidth(3, 75)
        self.pred_table.setColumnWidth(4, 80)
        header = self.pred_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        self.pred_table.setSortingEnabled(True)
        self.pred_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pred_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pred_table.setAlternatingRowColors(True)
        self.pred_table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.pred_table)

        body_splitter.addWidget(table_widget)
        body_splitter.setStretchFactor(0, 55)
        body_splitter.setStretchFactor(1, 45)

        root.addWidget(body_splitter, 1)

    # ── Metric card helper ────────────────────────────────────────────

    def _make_metric_card(self, caption: str) -> QFrame:
        """Create a styled metric card with a caption and value label."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #2b2b36; border-radius: 8px;
                padding: 8px;
            }
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)

        cap = QLabel(caption)
        cap.setStyleSheet("color: #8b8ba3; font-size: 10px;")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(cap)

        # Derive object name from caption defs in _init_ui
        key = [k for k, c in [
            ("samples", "📦 Зразків"), ("mae", "📏 MAE"), ("rmse", "📐 RMSE"),
            ("r2", "📈 R²"), ("dir_acc", "🎯 Напрямок"), ("corr", "🔗 Кореляція"),
        ] if c == caption]
        obj_name = f"val_{key[0]}" if key else "val_unknown"

        val = QLabel("—")
        val.setObjectName(obj_name)
        val.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        val.setStyleSheet("color: #f0f0f5;")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(val)

        return card

    # ── Refresh / compute ─────────────────────────────────────────────

    def refresh(self):
        """Reload data from DB and recompute all metrics and plots."""
        data = self._load_data()
        if not data:
            self._show_empty()
            return
        self._compute_and_display(data)

    def _load_data(self):
        """Fetch articles that have both real and predicted stock returns."""
        try:
            conn = self.db._connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, real_stock_return, predicted_stock_return
                FROM articles
                WHERE real_stock_return IS NOT NULL
                  AND predicted_stock_return IS NOT NULL
            """)
            rows = cursor.fetchall()
            if not rows:
                return None
            return [
                {
                    "title": r["title"],
                    "real": r["real_stock_return"],
                    "pred": r["predicted_stock_return"],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Failed to load evaluation data: %s", e)
            return None

    def _show_empty(self):
        """Display a message when no data is available."""
        self.info_label.setText(
            "⚠️  Немає статей з обома значеннями (реальна зміна та прогноз).\n"
            "Спочатку виконайте повний цикл:\n"
            "  1. Завантажте новини\n"
            "  2. Зіставте з котируваннями  (Нейромережа → Зіставити)\n"
            "  3. Навчіть модель  (Авто)\n"
            "  4. Запустіть прогноз  (Нейромережа → Прогноз)"
        )
        for lbl in self._metric_labels.values():
            lbl.setText("—")
        self.scatter_ax.clear()
        self.scatter_ax.set_facecolor("#1e1e24")
        self.scatter_ax.text(
            0.5, 0.5, "Немає даних", color="#8b8ba3",
            ha="center", va="center", transform=self.scatter_ax.transAxes, fontsize=12,
        )
        self.scatter_canvas.draw()
        self.hist_ax.clear()
        self.hist_ax.set_facecolor("#1e1e24")
        self.hist_canvas.draw()
        self.pred_table.setRowCount(0)

    # ── Core computation ──────────────────────────────────────────────

    def _compute_and_display(self, data: list):
        self.info_label.setText("")
        n = len(data)

        reals = [d["real"] for d in data]
        preds = [d["pred"] for d in data]
        errors = [p - r for r, p in zip(reals, preds)]
        abs_errors = [abs(e) for e in errors]

        # ── Metrics ───────────────────────────────────────────────────
        mae = sum(abs_errors) / n
        mse = sum(e ** 2 for e in errors) / n
        rmse = math.sqrt(mse)

        # R²
        mean_real = sum(reals) / n
        ss_res = sum((r - p) ** 2 for r, p in zip(reals, preds))
        ss_tot = sum((r - mean_real) ** 2 for r in reals)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # Direction accuracy (чи вгадав знак зміни)
        correct_dir = sum(
            1 for r, p in zip(reals, preds)
            if (r >= 0 and p >= 0) or (r < 0 and p < 0)
        )
        dir_acc = correct_dir / n * 100

        # Pearson correlation
        corr = self._pearson(reals, preds)

        # Update labels
        self._metric_labels["samples"].setText(str(n))
        self._metric_labels["mae"].setText(f"{mae:.3f}")
        self._metric_labels["rmse"].setText(f"{rmse:.3f}")

        r2_lbl = self._metric_labels["r2"]
        r2_lbl.setText(f"{r2:.3f}")
        if r2 > 0.3:
            r2_lbl.setStyleSheet("color: #00cec9; font-size: 16px;")
        elif r2 > 0.0:
            r2_lbl.setStyleSheet("color: #fdcb6e; font-size: 16px;")
        else:
            r2_lbl.setStyleSheet("color: #ff7675; font-size: 16px;")

        dir_lbl = self._metric_labels["dir_acc"]
        dir_lbl.setText(f"{dir_acc:.1f}%")
        if dir_acc >= 60:
            dir_lbl.setStyleSheet("color: #00cec9; font-size: 16px;")
        elif dir_acc >= 50:
            dir_lbl.setStyleSheet("color: #fdcb6e; font-size: 16px;")
        else:
            dir_lbl.setStyleSheet("color: #ff7675; font-size: 16px;")

        corr_lbl = self._metric_labels["corr"]
        corr_lbl.setText(f"{corr:.3f}")
        if abs(corr) > 0.3:
            corr_lbl.setStyleSheet("color: #00cec9; font-size: 16px;")
        else:
            corr_lbl.setStyleSheet("color: #fdcb6e; font-size: 16px;")

        # ── Scatter plot ──────────────────────────────────────────────
        self._draw_scatter(reals, preds)

        # ── Error histogram ───────────────────────────────────────────
        self._draw_histogram(errors)

        # ── Table ─────────────────────────────────────────────────────
        self._fill_table(data, errors)

    # ── Charts ────────────────────────────────────────────────────────

    def _draw_scatter(self, reals, preds):
        ax = self.scatter_ax
        ax.clear()
        ax.set_facecolor("#1e1e24")

        # Colour each point by direction correctness
        colors = []
        for r, p in zip(reals, preds):
            if (r >= 0 and p >= 0) or (r < 0 and p < 0):
                colors.append("#00cec9")   # correct direction
            else:
                colors.append("#ff7675")   # wrong direction

        ax.scatter(reals, preds, c=colors, alpha=0.65, s=28, edgecolors="none")

        # Ideal line y=x
        all_vals = reals + preds
        lo, hi = min(all_vals), max(all_vals)
        margin = (hi - lo) * 0.05 if hi != lo else 1
        ax.plot([lo - margin, hi + margin], [lo - margin, hi + margin],
                color="#a29bfe", linewidth=1.2, linestyle="--", alpha=0.6, label="Ідеал (y=x)")

        ax.set_xlabel("Реальна зміна %", color="#8b8ba3", fontsize=9)
        ax.set_ylabel("Прогноз %", color="#8b8ba3", fontsize=9)
        ax.set_title("Прогноз vs Реальність", color="#f0f0f5", fontsize=11, pad=8)
        ax.tick_params(colors="#8b8ba3", labelsize=8)
        ax.grid(True, color="#2b2b36", linestyle=":")
        ax.legend(fontsize=8, facecolor="#2b2b36", edgecolor="#55556a", labelcolor="#8b8ba3")

        for spine in ax.spines.values():
            spine.set_color("#55556a")
        self.scatter_canvas.draw()

    def _draw_histogram(self, errors):
        ax = self.hist_ax
        ax.clear()
        ax.set_facecolor("#1e1e24")

        n_bins = min(30, max(10, len(errors) // 5))
        ax.hist(errors, bins=n_bins, color="#6c5ce7", alpha=0.75, edgecolor="#1e1e24")

        ax.axvline(0, color="#a29bfe", linewidth=1.2, linestyle="--", alpha=0.7)
        ax.set_xlabel("Помилка прогнозу (pred − real) %", color="#8b8ba3", fontsize=9)
        ax.set_ylabel("Кількість", color="#8b8ba3", fontsize=9)
        ax.set_title("Розподіл помилок", color="#f0f0f5", fontsize=11, pad=8)
        ax.tick_params(colors="#8b8ba3", labelsize=8)
        ax.grid(True, color="#2b2b36", linestyle=":", axis="y")

        for spine in ax.spines.values():
            spine.set_color("#55556a")
        self.hist_canvas.draw()

    # ── Table ─────────────────────────────────────────────────────────

    def _fill_table(self, data, errors):
        """Fill the table sorted by absolute error (worst first)."""
        self.pred_table.setSortingEnabled(False)
        self.pred_table.clearContents()

        # Add error info to data
        items = []
        for d, err in zip(data, errors):
            items.append({**d, "error": err, "abs_error": abs(err)})

        # Sort by absolute error descending (worst predictions first)
        items.sort(key=lambda x: x["abs_error"], reverse=True)

        self.pred_table.setRowCount(len(items))
        for idx, item in enumerate(items):
            # Title
            title_item = QTableWidgetItem(item["title"][:120])
            self.pred_table.setItem(idx, 0, title_item)

            # Real %
            real_item = QTableWidgetItem(f"{item['real']:+.2f}")
            real_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if item["real"] >= 0:
                real_item.setForeground(QColor("#00cec9"))
            else:
                real_item.setForeground(QColor("#ff7675"))
            self.pred_table.setItem(idx, 1, real_item)

            # Predicted %
            pred_item = QTableWidgetItem(f"{item['pred']:+.2f}")
            pred_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if item["pred"] >= 0:
                pred_item.setForeground(QColor("#00cec9"))
            else:
                pred_item.setForeground(QColor("#ff7675"))
            self.pred_table.setItem(idx, 2, pred_item)

            # Error
            err_item = QTableWidgetItem(f"{item['error']:+.2f}")
            err_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            err_item.setForeground(QColor("#fdcb6e"))
            self.pred_table.setItem(idx, 3, err_item)

            # Direction
            r, p = item["real"], item["pred"]
            correct = (r >= 0 and p >= 0) or (r < 0 and p < 0)
            dir_item = QTableWidgetItem("✅" if correct else "❌")
            dir_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pred_table.setItem(idx, 4, dir_item)

        self.pred_table.setSortingEnabled(True)

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _pearson(x, y):
        """Compute Pearson correlation coefficient."""
        n = len(x)
        if n < 2:
            return 0.0
        mx = sum(x) / n
        my = sum(y) / n
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        den_x = math.sqrt(sum((xi - mx) ** 2 for xi in x))
        den_y = math.sqrt(sum((yi - my) ** 2 for yi in y))
        if den_x == 0 or den_y == 0:
            return 0.0
        return num / (den_x * den_y)
