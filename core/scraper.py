"""
IBIM News Parser — Web Scraper for Full Articles.

Fetches and extracts raw text articles from public URLs, filtering out HTML
boilerplate, navigation, scripts, and layout elements.
"""

import re
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def scrape_article_text(url: str) -> str:
    """Fetch the target HTML page and extract main article text body.

    Returns the parsed article text as a clean string if successful,
    or an empty string otherwise.
    """
    if not url or not url.startswith("http"):
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Cache-Control": "max-age=0",
    }

    try:
        response = requests.get(url, headers=headers, timeout=8)
        response.raise_for_status()
        
        # Ensure correct text encoding for Cyrillic/Ukrainian characters
        response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, "html.parser")

        # Decompose non-content layout elements
        for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "iframe"]):
            element.decompose()

        # Try to locate the article body by typical tags
        article_elem = soup.find("article")
        
        if not article_elem:
            # Look for common article div container classes
            article_elem = soup.find(
                "div",
                class_=re.compile(r"article-body|post-body|content-body|entry-content|story-content|article-content", re.I)
            )

        # Fallback to main content wrappers
        if not article_elem:
            article_elem = soup.find("main")

        target = article_elem if article_elem else soup

        # Extract text from paragraph tags
        paragraphs = []
        for p in target.find_all("p"):
            text = p.get_text().strip()
            # Simple heuristic: ignore short lines, cookie consent, or signup prompts
            if len(text) > 40 and not any(
                phrase in text.lower()
                for phrase in [
                    "cookie", "privacy policy", "terms of use", "subscribe",
                    "newsletter", "sign in", "create account", "all rights reserved",
                    "follow us on", "terms of service", "copyright"
                ]
            ):
                paragraphs.append(text)

        # We verify we have a substantial article (at least 2 paragraphs)
        if len(paragraphs) >= 2:
            full_text = "\n\n".join(paragraphs)
            return full_text

    except Exception as exc:
        logger.debug("Failed to scrape article from %s: %s", url, exc)

    return ""
