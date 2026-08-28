"""
IBIM News Parser — Entry point.

Launches the PyQt6 desktop application.
"""

import os
# ── КРИТИЧНО: встановити ДО будь-яких імпортів ───────────────────────
# PyTorch і numpy обидва тягнуть Intel OpenMP (libiomp5md.dll).
# Якщо вона завантажується двічі — heap corruption → Windows crash 0xc0000374.
# KMP_DUPLICATE_LIB_OK дозволяє двом копіям співіснувати без краша.
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"          # обмежуємо OpenMP потоки — менше конфліктів
os.environ["MKL_NUM_THREADS"] = "1"          # обмежуємо MKL потоки
os.environ["OPENBLAS_NUM_THREADS"] = "1"     # обмежуємо OpenBLAS потоки
os.environ["NUMEXPR_NUM_THREADS"] = "1"      # обмежуємо NumExpr потоки
os.environ["TOKENIZERS_PARALLELISM"] = "false" # вимикаємо фонові потоки Rust-токенізатора (часто веде до heap corruption у PyQt)
os.environ["TQDM_DISABLE"] = "1"             # вимикаємо tqdm monitor thread

# ── PyTorch: обмежуємо кількість потоків ДО першого імпорту torch ──
# set_num_interop_threads можна викликати лише ОДИН раз і ДО будь-якої
# паралельної роботи, тому робимо це тут, у точці входу.
import torch
torch.set_num_threads(1)
torch.set_num_interop_threads(1)

import sys
import logging
import traceback
import faulthandler
from pathlib import Path

# ── Crash-level log for C/segfaults ──────────────────────────────────
LOG_FILE = Path(__file__).resolve().parent / "data" / "app.log"
FAULT_FILE = Path(__file__).resolve().parent / "data" / "crash.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# faulthandler записує traceback навіть при SIGSEGV / OOM / C++ crash
_fault_fd = open(FAULT_FILE, "a", encoding="utf-8")
faulthandler.enable(file=_fault_fd)


class _FlushingFileHandler(logging.FileHandler):
    """FileHandler що робить flush() після кожного запису — лог ніколи не обривається при краші."""
    def emit(self, record):
        super().emit(record)
        self.flush()


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        _FlushingFileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

# ── Заглушуємо зайвий DEBUG-спам від сторонніх бібліотек ─────────────
for _noisy in (
    "matplotlib", "matplotlib.font_manager",
    "httpcore", "httpx", "urllib3",
    "transformers", "huggingface_hub",
    "PIL", "filelock",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger("main")


def _global_except_hook(exc_type, exc_value, exc_tb):
    """Перехоплює будь-який необроблений виняток та записує його в лог перед крешем."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("UNHANDLED EXCEPTION:\n%s", msg)
    try:
        from PyQt6.QtWidgets import QMessageBox, QApplication
        if QApplication.instance():
            QMessageBox.critical(
                None,
                "Критична помилка",
                f"Виникла необроблена помилка. Подробиці збережено у:\n{LOG_FILE}\n\n{exc_value}",
            )
    except Exception:
        pass


sys.excepthook = _global_except_hook


# ── Вимикаємо tqdm monitor глобально ─────────────────────────────────
# tqdm запускає фоновий потік-монітор який звертається до PyTorch-об'єктів
# після їх звільнення → heap corruption (Windows error 0xc0000374) → краш
# Вимикаємо через змінну середовища ДО завантаження будь-яких бібліотек
os.environ["TQDM_DISABLE"] = "1"
try:
    import tqdm
    tqdm.tqdm.monitor_interval = 0  # вимикає TRMonitor
    tqdm.monitor_interval = 0
except Exception:
    pass


def main():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont
    from PyQt6.QtCore import Qt
    from config import Config
    from core.database import Database
    from ui.main_window import MainWindow
    from ui.styles import get_stylesheet

    # Вмикаємо High-DPI масштабування до створення QApplication
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyleSheet(get_stylesheet())
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("IBIM News Parser")

    try:
        config = Config()
        config.load()

        db = Database()
        db.initialize()

        window = MainWindow(db)
        window.show()

        logger.info("Application started successfully.")
        sys.exit(app.exec())

    except Exception as exc:
        logger.critical("Fatal startup error: %s", exc, exc_info=True)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None,
            "Помилка запуску",
            f"Не вдалося запустити програму:\n\n{exc}\n\nДодаткові деталі: {LOG_FILE}",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
