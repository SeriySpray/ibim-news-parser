"""
IBIM News Parser — Data models.

Core dataclass representing a news article with serialisation helpers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import json
import uuid


@dataclass
class NewsArticle:
    """A single news article about a company."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_ticker: str = ""
    company_name: str = ""
    title: str = ""
    content: str = ""
    summary: str = ""
    source: str = ""
    source_url: str = ""
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = field(default_factory=datetime.utcnow)
    sentiment: str = ""          # positive | negative | neutral | ""
    tags: str = ""               # JSON-encoded list (for DB storage)
    user_notes: str = ""
    is_edited: bool = False
    is_starred: bool = False
    relevance: float = 0.0
    impact: float = 0.0

    # ── Tag helpers ────────────────────────────────────────────────
    @property
    def tags_list(self) -> List[str]:
        """Return tags as a Python list."""
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except (json.JSONDecodeError, TypeError):
            return []

    @tags_list.setter
    def tags_list(self, value: List[str]):
        """Set tags from a Python list."""
        self.tags = json.dumps(value, ensure_ascii=False)

    # ── Serialisation ──────────────────────────────────────────────
    def to_dict(self) -> dict:
        """Convert to a plain dictionary (for JSON export)."""
        return {
            "id": self.id,
            "company_ticker": self.company_ticker,
            "company_name": self.company_name,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "source": self.source,
            "source_url": self.source_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "sentiment": self.sentiment,
            "tags": self.tags_list,
            "user_notes": self.user_notes,
            "is_edited": self.is_edited,
            "is_starred": self.is_starred,
            "relevance": self.relevance,
            "impact": self.impact,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NewsArticle":
        """Create a NewsArticle from a dictionary."""
        article = cls()
        article.id = data.get("id", str(uuid.uuid4()))
        article.company_ticker = data.get("company_ticker", "")
        article.company_name = data.get("company_name", "")
        article.title = data.get("title", "")
        article.content = data.get("content", "")
        article.summary = data.get("summary", "")
        article.source = data.get("source", "")
        article.source_url = data.get("source_url", "")

        # Parse published_at
        pub_at = data.get("published_at")
        if isinstance(pub_at, str):
            try:
                article.published_at = datetime.fromisoformat(pub_at)
            except ValueError:
                article.published_at = None
        elif isinstance(pub_at, datetime):
            article.published_at = pub_at

        # Parse fetched_at
        fetch_at = data.get("fetched_at")
        if isinstance(fetch_at, str):
            try:
                article.fetched_at = datetime.fromisoformat(fetch_at)
            except ValueError:
                article.fetched_at = datetime.utcnow()
        elif isinstance(fetch_at, datetime):
            article.fetched_at = fetch_at

        article.sentiment = data.get("sentiment", "")

        tags = data.get("tags", [])
        if isinstance(tags, list):
            article.tags_list = tags
        elif isinstance(tags, str):
            article.tags = tags

        article.user_notes = data.get("user_notes", "")
        article.is_edited = data.get("is_edited", False)
        article.is_starred = data.get("is_starred", False)
        article.relevance = float(data.get("relevance", 0.0))
        article.impact = float(data.get("impact", 0.0))

        return article

    def __str__(self):
        date_str = self.published_at.strftime("%Y-%m-%d") if self.published_at else "N/A"
        return f"[{date_str}] {self.title} ({self.source})"
