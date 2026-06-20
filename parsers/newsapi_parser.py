"""
IBIM News Parser — NewsAPI parser.

Fetches articles via the NewsAPI ``/v2/everything`` endpoint and maps
them to ``NewsArticle`` instances.

API docs: https://newsapi.org/docs/endpoints/everything
"""

import logging
import math
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
NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"
PAGE_SIZE = 100  # max allowed by NewsAPI


class NewsAPIParser(BaseParser):
    """Parser that pulls articles from NewsAPI.

    The free plan returns truncated ``content``; when that happens the
    ``description`` field is used as a fallback.
    """

    def __init__(self):
        self._api_key: str = Config().get_api_key("newsapi")

    # ── BaseParser interface ──────────────────────────────────────

    def is_configured(self) -> bool:
        """Return ``True`` when a non-empty NewsAPI key is available."""
        return bool(self._api_key)

    def get_source_name(self) -> str:
        return "NewsAPI"

    def fetch_news(
        self,
        ticker: str,
        company_name: str,
        date_from: datetime,
        date_to: datetime,
    ) -> List[NewsArticle]:
        """Fetch articles from NewsAPI for *company_name* / *ticker*.

        Automatically paginates when ``totalResults`` exceeds the page size.
        Returns an empty list on missing API key or request failure.
        """
        if not self.is_configured():
            logger.warning("NewsAPI key is not configured — skipping.")
            return []

        # Build search query: combine company name and ticker
        query = f"{company_name} OR {ticker}"

        articles: List[NewsArticle] = []
        page = 1

        try:
            while True:
                params = {
                    "q": query,
                    "from": date_from.strftime("%Y-%m-%d"),
                    "to": date_to.strftime("%Y-%m-%d"),
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": PAGE_SIZE,
                    "page": page,
                    "apiKey": self._api_key,
                }

                response = requests.get(NEWSAPI_BASE_URL, params=params, timeout=30)

                if response.status_code == 429:
                    logger.warning("NewsAPI rate limit hit on page %d.", page)
                    break

                response.raise_for_status()
                data = response.json()

                if data.get("status") != "ok":
                    error_msg = data.get("message", "Unknown error")
                    logger.error("NewsAPI error: %s", error_msg)
                    break

                raw_articles = data.get("articles", [])
                total_results = data.get("totalResults", 0)

                for item in raw_articles:
                    article = self._map_to_article(item, ticker, company_name)
                    if article is not None:
                        articles.append(article)

                # Pagination: determine if there are more pages
                total_pages = math.ceil(total_results / PAGE_SIZE) if total_results else 1
                if page >= total_pages or not raw_articles:
                    break

                page += 1

            logger.info(
                "NewsAPI returned %d articles for '%s' (%s – %s).",
                len(articles),
                query,
                date_from.strftime("%Y-%m-%d"),
                date_to.strftime("%Y-%m-%d"),
            )

        except requests.exceptions.HTTPError as exc:
            logger.error("NewsAPI HTTP error: %s", exc)
        except requests.exceptions.ConnectionError as exc:
            logger.error("NewsAPI connection error: %s", exc)
        except requests.exceptions.Timeout:
            logger.error("NewsAPI request timed out.")
        except requests.exceptions.RequestException as exc:
            logger.error("NewsAPI request failed: %s", exc)
        except (ValueError, KeyError) as exc:
            logger.error("Error parsing NewsAPI response: %s", exc)

        return articles

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _map_to_article(
        item: dict,
        ticker: str,
        company_name: str,
    ) -> "NewsArticle | None":
        """Convert a single NewsAPI article object to a ``NewsArticle``."""
        try:
            title = (item.get("title") or "").strip()
            description = (item.get("description") or "").strip()
            content = (item.get("content") or "").strip()
            url = item.get("url", "")

            # Source name is nested: {"source": {"id": ..., "name": "..."}}
            source_obj = item.get("source") or {}
            source_name = source_obj.get("name", "Unknown")

            # Parse ISO-8601 published date
            published_at = None
            pub_str = item.get("publishedAt")
            if pub_str:
                try:
                    published_at = datetime.fromisoformat(
                        pub_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    logger.debug("Could not parse publishedAt: %s", pub_str)

            return NewsArticle(
                company_ticker=ticker.upper(),
                company_name=company_name,
                title=title,
                content=content or description,
                summary=description,
                source=f"NewsAPI: {source_name}",
                source_url=url,
                published_at=published_at,
                sentiment="",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed NewsAPI item: %s", exc)
            return None
