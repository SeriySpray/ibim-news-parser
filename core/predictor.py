"""
IBIM News Parser — Stock Price Predictor.

Trains and evaluates a PyTorch neural network that takes FinBERT text embeddings
and predicts the stock price return (percentage change).
"""

import os
import gc
import logging
import hashlib
import sqlite3
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path
from typing import List, Optional, Callable

# Вимикаємо tqdm monitor щоб уникнути heap corruption (0xc0000374)
# tqdm запускає фоновий потік що звертається до PyTorch-об'єктів після їх звільнення
try:
    from tqdm import TRMonitor
    TRMonitor.sleep_interval = 0  # вимикає monitor
except Exception:
    pass

from config import DB_FILE
from core.models import NewsArticle
from core.analyzer import FinancialAnalyzer

logger = logging.getLogger(__name__)

MODEL_PATH = DB_FILE.parent / "stock_predictor_model.pth"


class StockReturnPredictor(nn.Module):
    """Feedforward Neural Network for stock price return regression.

    Takes a 768-dimensional FinBERT embedding and outputs a single value:
    the predicted percentage stock price return.
    """

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(768, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1)
        )

    def forward(self, x):
        return self.net(x)


def get_finbert_embedding(text: str, db_path: Optional[str] = None) -> Optional[np.ndarray]:
    """Extract a 768-dimensional embedding from the BERT model inside FinancialAnalyzer.
    Uses a SQLite cache to avoid redundant model inference.
    """
    if not text or not text.strip():
        return None

    # Calculate hash of the text
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    
    # Check cache first
    actual_db_path = db_path or DB_FILE
    conn = None
    try:
        conn = sqlite3.connect(str(actual_db_path))
        conn.row_factory = sqlite3.Row
        # Create cache table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                text_hash TEXT PRIMARY KEY,
                embedding BLOB
            )
        """)
        cursor = conn.cursor()
        cursor.execute("SELECT embedding FROM embedding_cache WHERE text_hash = ?", (text_hash,))
        row = cursor.fetchone()
        if row is not None:
            # Cache hit!
            emb_bytes = row['embedding']
            conn.close()
            return np.frombuffer(emb_bytes, dtype=np.float32)
    except Exception as e:
        logger.warning("Cache lookup or creation failed: %s", e)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            conn = None

    # Cache miss - compute embedding using FinBERT
    try:
        analyzer = FinancialAnalyzer()
        analyzer._lazy_init()  # Ensure model and tokenizer are initialized
        
        tokenizer = analyzer.tokenizer
        model = analyzer.model

        # Truncate to match typical BERT context limits
        inputs = tokenizer(text[:1500], return_tensors="pt", max_length=512, truncation=True)
        
        # Disable gradient calculations for inference
        with torch.no_grad():
            if hasattr(model, 'bert'):
                # Extract BERT output (the classifier head is in sequence classification,
                # but we want raw CLS token representation)
                outputs = model.bert(**inputs)
                # last_hidden_state shape: [batch_size, seq_len, hidden_size]
                # CLS token is at index 0
                embeddings = outputs.last_hidden_state[:, 0, :].squeeze(0).cpu().numpy()
                
                # Save to cache
                if conn is not None:
                    try:
                        emb_bytes = embeddings.astype(np.float32).tobytes()
                        conn.execute(
                            "INSERT OR REPLACE INTO embedding_cache (text_hash, embedding) VALUES (?, ?)",
                            (text_hash, emb_bytes)
                        )
                        conn.commit()
                        conn.close()
                    except Exception as ce:
                        logger.warning("Failed to save embedding to cache: %s", ce)
                        try:
                            conn.close()
                        except Exception:
                            pass
                return embeddings
            else:
                logger.warning("FinBERT model does not have a 'bert' attribute to extract embeddings.")
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                return None

    except Exception as exc:
        logger.error("Failed to extract FinBERT embeddings: %s", exc)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        return None


def train_predictor_model(db, epochs: int = 50, lr: float = 0.001, batch_size: int = 8, progress_callback: Optional[Callable[[str], None]] = None) -> str:
    """Train the StockReturnPredictor model using articles containing real stock returns.

    Args:
        db: Database instance.
        epochs: Number of training epochs.
        lr: Learning rate.
        batch_size: Batch size.
        progress_callback: Optional callback to send status/progress messages back to UI.

    Returns:
        Status message summarizing training details.
    """
    msg = "Starting training of StockReturnPredictor..."
    logger.info(msg)
    if progress_callback:
        progress_callback(msg)

    # Fetch all articles that have a calculated real stock return
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT title, summary, content, real_stock_return FROM articles
        WHERE real_stock_return IS NOT NULL
        """
    )
    rows = cursor.fetchall()

    if not rows:
        msg = "No articles with 'real_stock_return' found. Fetch stock prices and align them first."
        logger.warning(msg)
        if progress_callback:
            progress_callback(msg)
        return msg

    msg = f"Found {len(rows)} articles with real return labels for training. Extracting embeddings..."
    logger.info(msg)
    if progress_callback:
        progress_callback(msg)

    X_list = []
    y_list = []
    total_rows = len(rows)

    for idx, row in enumerate(rows):
        title = row["title"] or ""
        body = row["summary"] or row["content"] or ""
        text = f"{title}. {body}".strip()
        
        real_ret = row["real_stock_return"]

        # Extract CLS embedding (using SQLite cache inside get_finbert_embedding)
        emb = get_finbert_embedding(text, db_path=db.db_path)
        if emb is not None:
            X_list.append(emb)
            y_list.append(real_ret)

        # Log progress every 100 articles
        if (idx + 1) % 100 == 0 or idx == 0 or idx == total_rows - 1:
            progress_msg = f"  🔬 Векторизація текстів: {idx + 1}/{total_rows} ({((idx + 1) / total_rows * 100):.1f}%)"
            logger.info(progress_msg)
            if progress_callback:
                progress_callback(progress_msg)

    if len(X_list) < 2:
        msg = f"Insufficient valid training data. Only {len(X_list)} samples successfully embedded."
        logger.warning(msg)
        if progress_callback:
            progress_callback(msg)
        return msg

    # Convert to PyTorch tensors
    X_tensor = torch.tensor(np.array(X_list), dtype=torch.float32)
    y_tensor = torch.tensor(np.array(y_list), dtype=torch.float32).unsqueeze(1)

    # Initialize model, loss function, and optimizer
    model = StockReturnPredictor()
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    # Training loop
    model.train()
    dataset_size = len(X_tensor)
    
    msg = f"Training neural network on {dataset_size} samples for {epochs} epochs..."
    logger.info(msg)
    if progress_callback:
        progress_callback(msg)
    
    for epoch in range(epochs):
        permutation = torch.randperm(dataset_size)
        epoch_loss = 0.0
        
        for i in range(0, dataset_size, batch_size):
            indices = permutation[i:i+batch_size]
            batch_x, batch_y = X_tensor[indices], y_tensor[indices]
            
            optimizer.zero_grad()
            predictions = model(batch_x)
            loss = criterion(predictions, batch_y)
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item() * len(indices)

        epoch_loss /= dataset_size
        if (epoch + 1) % 10 == 0 or epoch == 0 or epoch == epochs - 1:
            epoch_msg = f"  🏋️ Епоха {epoch + 1}/{epochs} — MSE Loss: {epoch_loss:.5f}"
            logger.info(epoch_msg)
            if progress_callback:
                progress_callback(epoch_msg)

    # Save model weights
    try:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), str(MODEL_PATH))
        msg = f"Model trained on {dataset_size} samples. Final MSE Loss: {epoch_loss:.4f}. Saved weights to {MODEL_PATH.name}."
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)
    except Exception as e:
        msg = f"Model trained, but failed to save weights: {e}"
        logger.error(msg)
        if progress_callback:
            progress_callback(msg)

    # Очищаємо пам'ять явно перед поверненням керування в Qt
    # Це запобігає heap corruption (code 0xc0000374) від tqdm monitor thread
    del X_tensor, y_tensor, model, optimizer, criterion
    gc.collect()
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass

    return msg


def predict_stock_return(title: str, summary: str, content: str) -> Optional[float]:
    """Load the trained predictor and calculate the predicted stock return for the given text.

    Args:
        title: Article title.
        summary: Article summary.
        content: Article full content.

    Returns:
        Predicted percentage change (float) if model is available, or None.
    """
    if not MODEL_PATH.exists():
        logger.debug("Trained stock return predictor weights not found at %s", MODEL_PATH)
        return None

    text = f"{title or ''}. {summary or content or ''}".strip()
    if not text:
        return None

    # Get embedding
    emb = get_finbert_embedding(text)
    if emb is None:
        return None

    try:
        model = StockReturnPredictor()
        # Force CPU loading
        model.load_state_dict(torch.load(str(MODEL_PATH), map_location=torch.device('cpu')))
        model.eval()

        x = torch.tensor(emb, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            pred = model(x).item()
        return round(pred, 4)

    except Exception as e:
        logger.error("Failed to run prediction: %s", e)
        return None


def predict_and_save_returns(db, articles: List[NewsArticle]) -> int:
    """Predict stock price return for a list of articles and update the DB.

    Args:
        db: Database instance.
        articles: List of articles to predict for.

    Returns:
        Number of articles updated with predictions.
    """
    if not MODEL_PATH.exists():
        logger.warning("No trained model weights found at %s. Prediction skipped.", MODEL_PATH)
        return 0

    conn = db._connect()
    cursor = conn.cursor()
    updated_count = 0

    for article in articles:
        pred_return = predict_stock_return(article.title, article.summary, article.content)
        if pred_return is not None:
            article.predicted_stock_return = pred_return
            try:
                cursor.execute(
                    "UPDATE articles SET predicted_stock_return = ? WHERE id = ?",
                    (pred_return, article.id)
                )
                updated_count += 1
            except Exception as e:
                logger.error("Failed to save prediction for article %s: %s", article.id, e)

    if updated_count > 0:
        conn.commit()
        logger.info("Successfully updated predictions for %d articles in the DB.", updated_count)

    return updated_count
