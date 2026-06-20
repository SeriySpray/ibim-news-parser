"""
IBIM News Parser — Finnhub parser.

Fetches company news via the Finnhub REST API and maps results to
``NewsArticle`` instances.

API docs: https://finnhub.io/docs/api/company-news
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List
import sys

import requests

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from core.models import NewsArticle
from parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────
FINNHUB_BASE_URL = "https://finnhub.io/api/v1/company-news"
RATE_LIMIT_SLEEP = 1  # seconds between requests


class FinnhubParser(BaseParser):
    """Parser that pulls company news from the Finnhub API.

    The free tier returns headline, summary, source, and URL but does *not*
    provide the full article body.  ``content`` is therefore set to the same
    value as ``summary``.
    """

    def __init__(self):
        self._api_key: str = Config().get_api_key("finnhub")

    # ── BaseParser interface ──────────────────────────────────────

    def is_configured(self) -> bool:
        """Return ``True`` when a non-empty Finnhub API key is available."""
        return bool(self._api_key)

    def get_source_name(self) -> str:
        return "Finnhub"

    def fetch_news(
        self,
        ticker: str,
        company_name: str,
        date_from: datetime,
        date_to: datetime,
    ) -> List[NewsArticle]:
        """Fetch company news from Finnhub for *ticker* between *date_from* and *date_to*.

        Returns an empty list when the API key is missing or a request fails.
        """
        if not self.is_configured():
            logger.warning("Finnhub API key is not configured — skipping.")
            return []

        params = {
            "symbol": ticker.upper(),
            "from": date_from.strftime("%Y-%m-%d"),
            "to": date_to.strftime("%Y-%m-%d"),
            "token": self._api_key,
        }

        articles: List[NewsArticle] = []

        try:
            # Respect rate limits
            time.sleep(RATE_LIMIT_SLEEP)

            response = requests.get(FINNHUB_BASE_URL, params=params, timeout=30)

            if response.status_code == 429:
                logger.warning("Finnhub rate limit hit. Sleeping 5 s and retrying …")
                time.sleep(5)
                response = requests.get(FINNHUB_BASE_URL, params=params, timeout=30)

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                logger.error("Unexpected Finnhub response format: %s", type(data))
                return []

            for item in data:
                article = self._map_to_article(item, ticker, company_name)
                if article is not None:
                    articles.append(article)

            logger.info(
                "Finnhub returned %d articles for %s (%s – %s).",
                len(articles),
                ticker,
                date_from.strftime("%Y-%m-%d"),
                date_to.strftime("%Y-%m-%d"),
            )

        except requests.exceptions.HTTPError as exc:
            logger.error("Finnhub HTTP error: %s", exc)
        except requests.exceptions.ConnectionError as exc:
            logger.error("Finnhub connection error: %s", exc)
        except requests.exceptions.Timeout:
            logger.error("Finnhub request timed out.")
        except requests.exceptions.RequestException as exc:
            logger.error("Finnhub request failed: %s", exc)
        except (ValueError, KeyError) as exc:
            logger.error("Error parsing Finnhub response: %s", exc)

        return articles

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _map_to_article(
        item: dict,
        ticker: str,
        company_name: str,
    ) -> "NewsArticle | None":
        """Convert a single Finnhub JSON object to a ``NewsArticle``."""
        try:
            headline = item.get("headline", "").strip()
            summary = item.get("summary", "").strip()
            source_field = item.get("source", "Unknown")
            url = item.get("url", "")
            ts = item.get("datetime")

            published_at = datetime.fromtimestamp(ts) if ts else None

            return NewsArticle(
                company_ticker=ticker.upper(),
                company_name=company_name,
                title=headline,
                content=summary,       # Finnhub only provides summary
                summary=summary,
                source=f"Finnhub: {source_field}",
                source_url=url,
                published_at=published_at,
                sentiment="",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed Finnhub item: %s", exc)
            return None
