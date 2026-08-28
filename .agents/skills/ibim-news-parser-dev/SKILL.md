---
name: ibim-news-parser-dev
description: Development guidelines, debugging history, and technical constraints for the IBIM News Parser project to prevent known crashes.
---

# IBIM News Parser — Development Guide & Constraints

This custom skill provides critical developer constraints and guidelines for the **IBIM News Parser** project to avoid repeating known crash-causing mistakes (such as thread-safety violations and heap corruption).

## 🛠 Project Stack
- **Backend/Logic**: Python 3.14+, SQLite, PyTorch, FinBERT (ProsusAI), mDeBERTa (News Classification).
- **GUI**: PyQt6.
- **Data & Logs**:
  - Main Log: `data/app.log` (with instant-flush handler)
  - C-Level Crash Log: `data/crash.log` (via `faulthandler`)
  - DB: `data/news.db`

---

## ⚠️ Critical Known Issues & Solutions (DO NOT REPEAT)

### 1. Heap Corruption (Windows Exception Code `0xc0000374`)
This project utilizes complex C-level and Rust-native libraries (PyTorch, Intel OpenMP, MKL, tokenizers, numpy) inside a PyQt6 environment on Windows, which makes it highly sensitive to thread scheduling and memory layout issues.

#### A. OpenMP, MKL, and Linear Algebra Thread Conflicts
- **Cause**: Both `numpy` and `torch` load `libiomp5md.dll` (Intel OpenMP) and perform parallel computations. When combined with PyQt6's event loop, concurrent thread pool allocations cause fatal heap corruption crashes.
- **Fix**: The following environment variables **must** be set at the absolute top of `main.py` before *any* other module is imported to restrict operations to single-threaded executions:
  ```python
  os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
  os.environ["OMP_NUM_THREADS"] = "1"
  os.environ["MKL_NUM_THREADS"] = "1"
  os.environ["OPENBLAS_NUM_THREADS"] = "1"
  os.environ["NUMEXPR_NUM_THREADS"] = "1"
  ```

#### B. Rust `tokenizers` Parallelism Conflict
- **Cause**: Hugging Face's `tokenizers` library uses Rust multi-threading (`Rayon`) for parallel processing. In a PyQt application with multiple Python threads, this causes deadlocks, race conditions, or memory corruption.
- **Fix**: Set `os.environ["TOKENIZERS_PARALLELISM"] = "false"` at startup in `main.py`.

#### C. `tqdm` Monitor Thread Crash
- **Cause**: `tqdm` automatically starts a background monitoring thread (`tqdm/_monitor.py`) when progress bars are used. This thread accesses PyTorch tensors or resources after they are freed at the end of training/validation loops, leading to a fatal memory access violation.
- **Fix**: 
  1. Set `os.environ["TQDM_DISABLE"] = "1"` at module level in `main.py`.
  2. Глобально вимкнути tqdm monitor при старті: `import tqdm; tqdm.tqdm.monitor_interval = 0`.
  3. Явно очищати тензори в `core/predictor.py` після завершення тренування перед поверненням в Qt (`del X_tensor, y_tensor, model, optimizer, criterion; gc.collect(); torch.cuda.empty_cache()`).

---

### 2. Thread-Safety & Qt GUI Access
- **Constraint**: PyQt6 strictly forbids updating UI widgets (e.g. changing labels, loading items into tables, updating progress bars) from background threads. Doing so causes silent segment faults or immediate process termination.
- **Rule**: All long-running tasks (scraping, database inserts, PyTorch model training) must run inside a subclass of `QThread`. Communication back to the main thread **must** happen exclusively through Qt signals (`pyqtSignal`).
- **Signal Hookup Example**:
  ```python
  self._worker = AutoTrainWorker(...)
  self._worker.finished.connect(self._on_finished) # safely executed in the main thread
  self._worker.start()
  ```

---

### 3. SQLite Database Thread Concurrency
- **Constraint**: SQLite connections are not thread-safe and cannot be shared across multiple active threads.
- **Rule**: Do **NOT** share a single `Database` instance or its `connection` attribute across the GUI thread and background `QThread` workers. Every thread must instantiate its own thread-local `Database()` instance (which creates a thread-isolated SQLite connection).

### 4. Neural Network Embedding Extraction Bottleneck
- **Cause**: BERT/FinBERT inference on CPU is extremely heavy. Running it sequentially on CPU for thousands of articles during training causes the app to feel frozen (up to 10 minutes) and uses excessive CPU, making users think it crashed.
- **Fix**: 
  1. We implemented a SQLite-backed caching table (`embedding_cache`) in `core/predictor.py` mapping MD5 text hashes to their float32 binary embeddings. On cache hits, retrieval takes <0.1ms, speeding up subsequent training iterations to under 1 second.
  2. We added an optional `progress_callback` to `train_predictor_model` to report embedding progress and epoch loss statistics to UI widgets in real-time (e.g. `🔬 Векторизація текстів: 100/2327 (4.3%)`).

---

## 📁 Key File Structure
- [main.py](file:///C:/Users/zalla/PycharmProjects/Hueta/ibim-news-parser/main.py): Entry point. Configures critical environment variables, logger, `sys.excepthook`, `faulthandler`, and launches `QApplication`.
- [core/database.py](file:///C:/Users/zalla/PycharmProjects/Hueta/ibim-news-parser/core/database.py): Handles database schema and SQLite interaction.
- [core/predictor.py](file:///C:/Users/zalla/PycharmProjects/Hueta/ibim-news-parser/core/predictor.py): Contains the PyTorch neural network for return prediction. Implements explicit GC cleanup of tensors.
- [ui/auto_train_panel.py](file:///C:/Users/zalla/PycharmProjects/Hueta/ibim-news-parser/ui/auto_train_panel.py): The "Auto" tab layout. Orchestrates `AutoTrainWorker` cycles and handles thread-safe logging.
- [ui/main_window.py](file:///C:/Users/zalla/PycharmProjects/Hueta/ibim-news-parser/ui/main_window.py): Coordinates the main layout, tabs, menus, and thread-safe data refreshes.
