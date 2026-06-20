"""
IBIM News Parser — RSS feed parser.

Aggregates financial news from predefined RSS feeds using the
``feedparser`` library.  No API key is required.

Supported feeds:
- Yahoo Finance (per-ticker)
- Google News (company name search)
- Seeking Alpha (per-ticker)
"""

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import sys

import feedparser

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import NewsArticle
from parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)

# ── HTML-stripping helper ──────────────────────────────────────────
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from *text* using a simple regex."""
    return _HTML_TAG_RE.sub("", text).strip()


# ── Feed definitions ───────────────────────────────────────────────
def _build_feed_urls(ticker: str, company_name: str) -> Dict[str, str]:
    """Return ``{feed_name: url}`` for the supported RSS sources."""
    return {
        "Yahoo Finance": (
            f"https://feeds.finance.yahoo.com/rss/2.0/headline"
            f"?s={ticker}&region=US&lang=en-US"
        ),
        "Google News": (
            f"https://news.google.com/rss/search"
            f"?q={company_name}+stock&hl=en-US&gl=US&ceid=US:en"
        ),
        "Seeking Alpha": (
            f"https://seekingalpha.com/api/sa/combined/{ticker}.xml"
        ),
    }


class RSSParser(BaseParser):
    """Parser that aggregates articles from several public RSS feeds.

    This parser requires no API key and is therefore always considered
    configured.  Individual feed failures are logged as warnings and
    silently skipped so the parser never raises.
    """

    # ── BaseParser interface ──────────────────────────────────────

    def is_configured(self) -> bool:
        """RSS feeds are public — always returns ``True``."""
        return True

    def get_source_name(self) -> str:
        return "RSS Feeds"

    def fetch_news(
        self,
        ticker: str,
        company_name: str,
        date_from: datetime,
        date_to: datetime,
    ) -> List[NewsArticle]:
        """Fetch and aggregate articles from all RSS feeds.

        Entries whose ``published`` date falls outside *date_from* / *date_to*
        are silently filtered out.
        """
        feeds = _build_feed_urls(ticker.upper(), company_name)
        articles: List[NewsArticle] = []

        for feed_name, feed_url in feeds.items():
            try:
                feed_articles = self._parse_feed(
                    feed_name=feed_name,
                    feed_url=feed_url,
                    ticker=ticker,
                    company_name=company_name,
                    date_from=date_from,
                    date_to=date_to,
                )
                articles.extend(feed_articles)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "RSS feed '%s' (%s) failed: %s",
                    feed_name,
                    feed_url,
                    exc,
                )

        logger.info(
            "RSS returned %d articles for %s (%s – %s).",
            len(articles),
            ticker,
            date_from.strftime("%Y-%m-%d"),
            date_to.strftime("%Y-%m-%d"),
        )
        return articles

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _parse_published(entry) -> "datetime | None":
        """Extract the published datetime from a feedparser entry.

        ``feedparser`` exposes ``published_parsed`` as a ``time.struct_time``
        when it can parse the date.  Fall back to string parsing if needed.
        """
        # Prefer the struct_time tuple provided by feedparser
        parsed = entry.get("published_parsed")
        if parsed:
            try:
                return datetime(*parsed[:6])
            except (TypeError, ValueError):
                pass

        # Fallback: raw string
        raw = entry.get("published", "")
        if raw:
            for fmt in (
                "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue

        return None

    def _parse_feed(
        self,
        feed_name: str,
        feed_url: str,
        ticker: str,
        company_name: str,
        date_from: datetime,
        date_to: datetime,
    ) -> List[NewsArticle]:
        """Parse a single RSS feed and return matching ``NewsArticle`` objects."""
        feed = feedparser.parse(feed_url)

        if feed.bozo and not feed.entries:
            logger.warning(
                "RSS feed '%s' returned a bozo error: %s",
                feed_name,
                feed.bozo_exception,
            )
            return []

        articles: List[NewsArticle] = []

        for entry in feed.entries:
            published_at = self._parse_published(entry)

            # ── Date filtering ────────────────────────────────────
            if published_at is not None:
                # Compare as naive datetimes (strip tzinfo if present)
                pub_naive = published_at.replace(tzinfo=None)
                from_naive = date_from.replace(tzinfo=None)
                to_naive = date_to.replace(tzinfo=None)
                if pub_naive < from_naive or pub_naive > to_naive:
                    continue

            # ── Extract text ──────────────────────────────────────
            title = (entry.get("title") or "").strip()
            raw_summary = entry.get("summary") or entry.get("description") or ""
            content = _strip_html(raw_summary)

            link = entry.get("link", "")

            article = NewsArticle(
                company_ticker=ticker.upper(),
                company_name=company_name,
                title=title,
                content=content,
                summary=content,
                source=f"RSS: {feed_name}",
                source_url=link,
                published_at=published_at,
                sentiment="",
            )
            articles.append(article)

        return articles
