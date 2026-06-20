"""
IBIM News Parser — Abstract base parser.

Defines the interface that every concrete news-source parser must implement.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List
import sys

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import NewsArticle


class BaseParser(ABC):
    """Abstract base for all news parsers.

    Subclasses must implement three methods:
    - ``fetch_news``   – pull articles for a given ticker & date range
    - ``is_configured`` – verify API credentials are present
    - ``get_source_name`` – human-readable source label
    """

    @abstractmethod
    def fetch_news(
        self,
        ticker: str,
        company_name: str,
        date_from: datetime,
        date_to: datetime,
    ) -> List[NewsArticle]:
        """Fetch news articles for a company within a date range.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol (e.g. ``"AAPL"``).
        company_name : str
            Full company name (e.g. ``"Apple Inc."``).
        date_from : datetime
            Start of the date window (inclusive).
        date_to : datetime
            End of the date window (inclusive).

        Returns
        -------
        List[NewsArticle]
            Parsed articles mapped to the common ``NewsArticle`` model.
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the parser has valid API credentials.

        Returns ``True`` when the parser can make requests without
        encountering authentication errors.
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the display name of this news source.

        Used in the UI and log messages.
        """
        pass
