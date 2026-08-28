"""
IBIM News Parser — Market Data Integration.

Fetches historical stock prices using yfinance and stores them in the database.
Provides alignment helpers to match news articles with stock returns.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_and_store_stock_prices(
    db,
    ticker: str,
    start_date: datetime,
    end_date: datetime
) -> int:
    """Fetch daily stock prices for a ticker from yfinance and store them in the database.

    Args:
        db: Database instance.
        ticker: Stock ticker symbol (e.g. 'AAPL').
        start_date: Start date for fetching.
        end_date: End date for fetching.

    Returns:
        Number of price records inserted or updated.
    """
    ticker_clean = ticker.upper().strip()
    if not ticker_clean:
        return 0

    # Map name/incorrect ticker to yfinance ticker
    ticker_mapping = {
        "NVIDIA": "NVDA",
        "GOOGLE": "GOOGL",
        "APPLE": "AAPL",
        "MICROSOFT": "MSFT",
        "AMAZON": "AMZN",
        "FACEBOOK": "META",
        "TESLA": "TSLA",
    }
    fetch_ticker = ticker_mapping.get(ticker_clean, ticker_clean)

    # Expand the range slightly to ensure we have boundary data for alignment
    expanded_start = start_date - timedelta(days=5)
    expanded_end = end_date + timedelta(days=5)

    start_str = expanded_start.strftime("%Y-%m-%d")
    end_str = expanded_end.strftime("%Y-%m-%d")

    logger.info("Fetching stock prices for %s (yfinance: %s) from %s to %s...", ticker_clean, fetch_ticker, start_str, end_str)

    try:
        # Download historical daily data
        stock = yf.Ticker(fetch_ticker)
        df = stock.history(start=start_str, end=end_str, interval="1d")

        if df.empty:
            logger.warning("No stock data returned from yfinance for %s (yfinance: %s)", ticker_clean, fetch_ticker)
            return 0

        conn = db._connect()
        cursor = conn.cursor()

        records_inserted = 0
        for index, row in df.iterrows():
            date_str = index.strftime("%Y-%m-%d")
            open_val = float(row["Open"])
            high_val = float(row["High"])
            low_val = float(row["Low"])
            close_val = float(row["Close"])
            volume_val = int(row["Volume"])

            try:
                cursor.execute(
                    """
                    INSERT INTO stock_prices (ticker, date, open, close, high, low, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, date) DO UPDATE SET
                        open = excluded.open,
                        close = excluded.close,
                        high = excluded.high,
                        low = excluded.low,
                        volume = excluded.volume
                    """,
                    (ticker_clean, date_str, open_val, close_val, high_val, low_val, volume_val)
                )
                records_inserted += 1
            except Exception as e:
                logger.error("Failed to insert price record for %s on %s: %s", ticker_clean, date_str, e)

        conn.commit()
        logger.info("Successfully stored %d price records for %s", records_inserted, ticker_clean)
        return records_inserted

    except Exception as exc:
        logger.error("Failed to fetch stock prices for %s: %s", ticker_clean, exc)
        return 0


def align_article_with_return(db, article_id: str) -> Optional[float]:
    """Find corresponding stock prices and calculate the stock percentage return for the article.

    Calculates next-day return: return = ((Close_{t+1} - Close_{t}) / Close_{t}) * 100
    If next-day return is not yet available (e.g. over the weekend), falls back to:
    news-day return: return = ((Close_{t} - Close_{t-1}) / Close_{t-1}) * 100
    or intraday return: return = ((Close_{t} - Open_{t}) / Open_{t}) * 100

    where t is the first trading day on or after the article's publication date.

    Args:
        db: Database instance.
        article_id: The article's unique ID.

    Returns:
        The percentage return (float) if calculated successfully, or None.
    """
    article = db.get_article(article_id)
    if not article or not article.company_ticker or not article.published_at:
        return None

    ticker = article.company_ticker.upper().strip()
    pub_date = article.published_at.date()
    pub_date_str = pub_date.strftime("%Y-%m-%d")

    conn = db._connect()
    cursor = conn.cursor()

    # Query available prices around the publication date
    cursor.execute(
        """
        SELECT date, open, close FROM stock_prices
        WHERE ticker = ? AND date >= date(?, '-5 days') AND date <= date(?, '+10 days')
        ORDER BY date ASC
        """,
        (ticker, pub_date_str, pub_date_str)
    )
    rows = cursor.fetchall()

    if not rows or len(rows) < 3:
        # Fetch prices from yfinance to ensure we have data
        start = article.published_at - timedelta(days=7)
        end = article.published_at + timedelta(days=12)
        fetch_and_store_stock_prices(db, ticker, start, end)

        # Re-query
        cursor.execute(
            """
            SELECT date, open, close FROM stock_prices
            WHERE ticker = ? AND date >= date(?, '-5 days') AND date <= date(?, '+10 days')
            ORDER BY date ASC
            """,
            (ticker, pub_date_str, pub_date_str)
        )
        rows = cursor.fetchall()

    if not rows:
        logger.warning("No stock prices found at all for %s around %s", ticker, pub_date_str)
        return None

    # Find the trading day in stock_prices closest to the publication date
    closest_idx = -1
    min_diff = timedelta(days=9999)
    for i, r in enumerate(rows):
        r_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
        diff = abs(r_date - pub_date)
        if diff < min_diff:
            min_diff = diff
            closest_idx = i

    if closest_idx == -1:
        logger.warning("Could not find any close trading day for ticker %s near %s", ticker, pub_date_str)
        return None

    pct_return = None
    calc_method = ""
    used_date = rows[closest_idx]["date"]

    # Option 1: Next-day return if available (Close_t+1 vs Close_t)
    # Only if the article day itself or the closest day is on or after the pub date, and we have the next day
    if rows[closest_idx]["date"] >= pub_date_str and closest_idx + 1 < len(rows):
        day_t_close = rows[closest_idx]["close"]
        day_t1_close = rows[closest_idx + 1]["close"]
        if day_t_close > 0:
            pct_return = ((day_t1_close - day_t_close) / day_t_close) * 100.0
            calc_method = f"next-day ({rows[closest_idx]['date']} close to {rows[closest_idx + 1]['date']} close)"

    # Option 2: Preceding-day return fallback (Close_t vs Close_t-1)
    if pct_return is None and closest_idx > 0:
        day_prev_close = rows[closest_idx - 1]["close"]
        day_t_close = rows[closest_idx]["close"]
        if day_prev_close > 0:
            pct_return = ((day_t_close - day_prev_close) / day_prev_close) * 100.0
            calc_method = f"day-of-news/preceding ({rows[closest_idx - 1]['date']} close to {rows[closest_idx]['date']} close)"

    # Option 3: Intraday return fallback (Close_t vs Open_t)
    if pct_return is None:
        day_t_open = rows[closest_idx]["open"]
        day_t_close = rows[closest_idx]["close"]
        if day_t_open > 0:
            pct_return = ((day_t_close - day_t_open) / day_t_open) * 100.0
            calc_method = f"intraday ({rows[closest_idx]['date']} open to close)"

    if pct_return is None:
        logger.warning("Could not calculate return for article %s (%s) using any method", article_id, ticker)
        return None

    pct_return = round(pct_return, 4)

    # Save to the database
    try:
        cursor.execute(
            "UPDATE articles SET real_stock_return = ? WHERE id = ?",
            (pct_return, article_id)
        )
        conn.commit()
        logger.info(
            "Aligned article %s: date=%s return=%.2f%% via %s",
            article_id, used_date, pct_return, calc_method
        )
        return pct_return
    except Exception as e:
        logger.error("Failed to save real return for article %s: %s", article_id, e)
        return None
