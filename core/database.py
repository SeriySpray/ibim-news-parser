"""
IBIM News Parser — Database manager.

SQLite-backed storage for news articles with full CRUD support,
flexible multi-filter search, and duplicate detection by source URL.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import DB_FILE
from core.models import NewsArticle

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for news articles.

    Provides insert / update / delete / search operations on the
    ``articles`` table.  Datetime values are persisted as ISO-8601
    strings; booleans as INTEGER 0/1; tags as a JSON-encoded string.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialise the database connection.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to ``config.DB_FILE`` when *None*.
        """
        self.db_path = Path(db_path) if db_path else DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection: Optional[sqlite3.Connection] = None

    # ── Connection helpers ────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """Return an open connection, creating one if necessary."""
        if self.connection is None:
            self.connection = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            self.connection.row_factory = sqlite3.Row
        return self.connection

    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    # ── Schema ────────────────────────────────────────────────────────

    def initialize(self):
        """Create the ``articles`` table if it does not already exist."""
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id              TEXT PRIMARY KEY,
                    company_ticker  TEXT NOT NULL DEFAULT '',
                    company_name    TEXT NOT NULL DEFAULT '',
                    title           TEXT NOT NULL DEFAULT '',
                    content         TEXT NOT NULL DEFAULT '',
                    summary         TEXT NOT NULL DEFAULT '',
                    source          TEXT NOT NULL DEFAULT '',
                    source_url      TEXT NOT NULL DEFAULT '' UNIQUE,
                    published_at    TEXT,
                    fetched_at      TEXT,
                    sentiment       TEXT NOT NULL DEFAULT '',
                    tags            TEXT NOT NULL DEFAULT '',
                    user_notes      TEXT NOT NULL DEFAULT '',
                    is_edited       INTEGER NOT NULL DEFAULT 0,
                    is_starred      INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_ticker
                ON articles (company_ticker)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_source
                ON articles (source)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_published
                ON articles (published_at)
            """)
            
            # Check and add new columns dynamically if they don't exist
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(articles)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'relevance' not in columns:
                conn.execute("ALTER TABLE articles ADD COLUMN relevance REAL DEFAULT 0.0")
            if 'impact' not in columns:
                conn.execute("ALTER TABLE articles ADD COLUMN impact REAL DEFAULT 0.0")
                
            conn.commit()
            logger.info("Database initialised at %s", self.db_path)
        except sqlite3.Error as exc:
            logger.error("Failed to initialise database: %s", exc)
            raise

    # ── Row ↔ Model conversion ────────────────────────────────────────

    @staticmethod
    def _row_to_article(row: sqlite3.Row) -> NewsArticle:
        """Convert a database row to a ``NewsArticle`` instance."""
        article = NewsArticle()
        article.id = row["id"]
        article.company_ticker = row["company_ticker"]
        article.company_name = row["company_name"]
        article.title = row["title"]
        article.content = row["content"]
        article.summary = row["summary"]
        article.source = row["source"]
        article.source_url = row["source_url"]

        pub = row["published_at"]
        if pub:
            try:
                article.published_at = datetime.fromisoformat(pub)
            except (ValueError, TypeError):
                article.published_at = None
        else:
            article.published_at = None

        fetch = row["fetched_at"]
        if fetch:
            try:
                article.fetched_at = datetime.fromisoformat(fetch)
            except (ValueError, TypeError):
                article.fetched_at = None
        else:
            article.fetched_at = None

        article.sentiment = row["sentiment"]
        article.tags = row["tags"]
        article.user_notes = row["user_notes"]
        article.is_edited = bool(row["is_edited"])
        article.is_starred = bool(row["is_starred"])
        article.relevance = row["relevance"] if "relevance" in row.keys() else 0.0
        article.impact = row["impact"] if "impact" in row.keys() else 0.0
        return article

    # ── CRUD ──────────────────────────────────────────────────────────

    def insert_article(self, article: NewsArticle) -> bool:
        """Insert a single article into the database.

        Args:
            article: The article to insert.

        Returns:
            ``True`` on success, ``False`` if a duplicate ``source_url``
            already exists or another error occurs.
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO articles (
                    id, company_ticker, company_name, title, content,
                    summary, source, source_url, published_at, fetched_at,
                    sentiment, tags, user_notes, is_edited, is_starred,
                    relevance, impact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.id,
                    article.company_ticker,
                    article.company_name,
                    article.title,
                    article.content,
                    article.summary,
                    article.source,
                    article.source_url,
                    article.published_at.isoformat() if article.published_at else None,
                    article.fetched_at.isoformat() if article.fetched_at else None,
                    article.sentiment,
                    article.tags,
                    article.user_notes,
                    int(article.is_edited),
                    int(article.is_starred),
                    article.relevance,
                    article.impact,
                ),
            )
            conn.commit()
            logger.debug("Inserted article %s", article.id)
            return True
        except sqlite3.IntegrityError:
            logger.debug(
                "Duplicate article skipped (source_url=%s)", article.source_url
            )
            return False
        except sqlite3.Error as exc:
            logger.error("Insert failed for article %s: %s", article.id, exc)
            return False

    def insert_articles(self, articles: List[NewsArticle]) -> int:
        """Batch-insert multiple articles, skipping duplicates.

        Args:
            articles: List of articles to insert.

        Returns:
            The number of articles successfully inserted.
        """
        inserted = 0
        for article in articles:
            if self.insert_article(article):
                inserted += 1
        return inserted

    def update_article(self, article: NewsArticle) -> bool:
        """Update an existing article (matched by ``id``).

        Args:
            article: Article with updated field values.

        Returns:
            ``True`` if a row was updated, ``False`` otherwise.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                UPDATE articles SET
                    company_ticker = ?,
                    company_name   = ?,
                    title          = ?,
                    content        = ?,
                    summary        = ?,
                    source         = ?,
                    source_url     = ?,
                    published_at   = ?,
                    fetched_at     = ?,
                    sentiment      = ?,
                    tags           = ?,
                    user_notes     = ?,
                    is_edited      = ?,
                    is_starred     = ?,
                    relevance      = ?,
                    impact         = ?
                WHERE id = ?
                """,
                (
                    article.company_ticker,
                    article.company_name,
                    article.title,
                    article.content,
                    article.summary,
                    article.source,
                    article.source_url,
                    article.published_at.isoformat() if article.published_at else None,
                    article.fetched_at.isoformat() if article.fetched_at else None,
                    article.sentiment,
                    article.tags,
                    article.user_notes,
                    int(article.is_edited),
                    int(article.is_starred),
                    article.relevance,
                    article.impact,
                    article.id,
                ),
            )
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.debug("Updated article %s", article.id)
            else:
                logger.warning("No article found with id %s", article.id)
            return updated
        except sqlite3.Error as exc:
            logger.error("Update failed for article %s: %s", article.id, exc)
            return False

    def delete_article(self, article_id: str) -> bool:
        """Delete an article by its ID.

        Args:
            article_id: UUID of the article to delete.

        Returns:
            ``True`` if a row was deleted, ``False`` otherwise.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM articles WHERE id = ?", (article_id,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug("Deleted article %s", article_id)
            else:
                logger.warning("No article found with id %s", article_id)
            return deleted
        except sqlite3.Error as exc:
            logger.error("Delete failed for article %s: %s", article_id, exc)
            return False

    # ── Queries ───────────────────────────────────────────────────────

    def get_article(self, article_id: str) -> Optional[NewsArticle]:
        """Retrieve a single article by ID.

        Args:
            article_id: UUID of the article.

        Returns:
            A ``NewsArticle`` or ``None`` if not found.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM articles WHERE id = ?", (article_id,)
            )
            row = cursor.fetchone()
            return self._row_to_article(row) if row else None
        except sqlite3.Error as exc:
            logger.error("Fetch failed for article %s: %s", article_id, exc)
            return None

    def search_articles(
        self,
        ticker: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        source: Optional[str] = None,
        sentiment: Optional[str] = None,
        is_starred: Optional[bool] = None,
        search_text: Optional[str] = None,
        min_relevance: Optional[float] = None,
        min_impact: Optional[float] = None,
    ) -> List[NewsArticle]:
        """Flexible article search with optional filters.

        All parameters are optional; omitting a parameter means it will
        not be used to filter results.  Filters are combined with AND.

        Args:
            ticker:      Filter by ``company_ticker`` (case-insensitive).
            date_from:   Include articles published on or after this date.
            date_to:     Include articles published on or before this date.
            source:      Filter by news source (case-insensitive).
            sentiment:   Filter by sentiment label.
            is_starred:  Filter by starred status.
            search_text: Free-text search across title, content, and summary.
            min_relevance: Minimum relevance score (0.0 to 1.0).
            min_impact:  Minimum absolute stock price impact (0.0 to 1.0).

        Returns:
            List of matching ``NewsArticle`` objects ordered by
            ``published_at`` descending.
        """
        conn = self._connect()
        clauses: List[str] = []
        params: list = []

        if ticker is not None:
            clauses.append("UPPER(company_ticker) = UPPER(?)")
            params.append(ticker)

        if date_from is not None:
            clauses.append("published_at >= ?")
            params.append(date_from.isoformat())

        if date_to is not None:
            clauses.append("published_at <= ?")
            params.append(date_to.isoformat())

        if source is not None:
            clauses.append("UPPER(source) = UPPER(?)")
            params.append(source)

        if sentiment is not None:
            clauses.append("sentiment = ?")
            params.append(sentiment)

        if is_starred is not None:
            clauses.append("is_starred = ?")
            params.append(int(is_starred))

        if min_relevance is not None:
            clauses.append("relevance >= ?")
            params.append(min_relevance)

        if min_impact is not None:
            clauses.append("ABS(impact) >= ?")
            params.append(min_impact)

        if search_text is not None:
            clauses.append(
                "(title LIKE ? OR content LIKE ? OR summary LIKE ?)"
            )
            like = f"%{search_text}%"
            params.extend([like, like, like])

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM articles{where} ORDER BY published_at DESC"

        try:
            cursor = conn.execute(query, params)
            return [self._row_to_article(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("Search query failed: %s", exc)
            return []

    def get_all_tickers(self) -> List[str]:
        """Return a sorted list of distinct company tickers in the DB."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT DISTINCT company_ticker FROM articles "
                "WHERE company_ticker != '' ORDER BY company_ticker"
            )
            return [row["company_ticker"] for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("Failed to fetch tickers: %s", exc)
            return []

    def get_all_sources(self) -> List[str]:
        """Return a sorted list of distinct news sources in the DB."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT DISTINCT source FROM articles "
                "WHERE source != '' ORDER BY source"
            )
            return [row["source"] for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("Failed to fetch sources: %s", exc)
            return []

    def article_exists(self, source_url: str) -> bool:
        """Check whether an article with the given source URL exists.

        Args:
            source_url: The URL to look up.

        Returns:
            ``True`` if a matching article is found.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT 1 FROM articles WHERE source_url = ? LIMIT 1",
                (source_url,),
            )
            return cursor.fetchone() is not None
        except sqlite3.Error as exc:
            logger.error("Existence check failed: %s", exc)
            return False

    def get_article_count(self) -> int:
        """Return the total number of articles stored in the database."""
        conn = self._connect()
        try:
            cursor = conn.execute("SELECT COUNT(*) AS cnt FROM articles")
            row = cursor.fetchone()
            return row["cnt"] if row else 0
        except sqlite3.Error as exc:
            logger.error("Count query failed: %s", exc)
            return 0
