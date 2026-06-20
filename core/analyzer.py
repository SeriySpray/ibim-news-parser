"""
IBIM News Parser — Financial News Analyzer.

Provides local evaluation of news relevance to a specific company and
stock price impact scoring using the FinBERT model.
"""

import re
import logging

logger = logging.getLogger(__name__)


def calculate_relevance(title: str, content: str, ticker: str, company_name: str) -> float:
    """Calculate local relevance score from 0.0 to 1.0.

    Uses mention density of ticker/company name with higher weight on the title.
    """
    if not ticker and not company_name:
        return 0.0

    title_text = (title or "").lower()
    content_text = (content or "").lower()

    # Weight title higher by duplicating it in the text body
    weighted_text = (title_text + " ") * 3 + content_text

    mentions = 0

    def count_word_mentions(term: str) -> int:
        if not term:
            return 0
        term_clean = term.lower().strip()
        try:
            # Match as whole word first
            pattern = r'\b' + re.escape(term_clean) + r'\b'
            count = len(re.findall(pattern, weighted_text))
            if count == 0:
                # Fallback to simple count if whole word misses (e.g. compound names)
                count = weighted_text.count(term_clean)
            return count
        except Exception:
            return weighted_text.count(term_clean)

    mentions += count_word_mentions(ticker)
    if company_name and company_name.lower().strip() != ticker.lower().strip():
        mentions += count_word_mentions(company_name)

    if mentions == 0:
        return 0.0

    # Base relevance if it exists in the title
    has_in_title = (ticker.lower().strip() in title_text) or (
        company_name and company_name.lower().strip() in title_text
    )

    if has_in_title:
        base_relevance = 0.7
    else:
        base_relevance = 0.2

    # Boost based on total count
    boost = min(0.3, 0.08 * mentions)
    return min(1.0, base_relevance + boost)


class FinancialAnalyzer:
    """Singleton analyzer utilizing the local ProsusAI/finbert model."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.tokenizer = None
            cls._instance.model = None
            cls._instance.pipeline = None
        return cls._instance

    def _lazy_init(self):
        """Lazy initialization of the Hugging Face pipelines to save startup time."""
        if self.pipeline is None:
            logger.info("Initializing FinBERT model and tokenizer...")
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

            model_name = "ProsusAI/finbert"

            # Force CPU execution to be friendly to standard PCs without CUDA GPU
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            # top_k=None is used to retrieve probabilities for all classes (pos/neg/neu)
            self.pipeline = pipeline(
                "sentiment-analysis",
                model=self.model,
                tokenizer=self.tokenizer,
                top_k=None,
                device=-1  # CPU only
            )
            logger.info("FinBERT model loaded successfully.")

    def analyze_sentiment(self, text: str) -> float:
        """Analyze financial sentiment of the text using FinBERT.

        Returns an impact score from -1.0 (pure negative) to 1.0 (pure positive).
        """
        if not text or not text.strip():
            return 0.0

        try:
            self._lazy_init()
            # Crop text to fit BERT's 512 token limit (roughly 1500 chars)
            results = self.pipeline(text[:1500], max_length=512, truncation=True)
            if not results:
                return 0.0

            # results looks like: [[{'label': 'positive', 'score': 0.95}, ...]]
            scores = {res['label'].lower(): res['score'] for res in results[0]}
            
            positive_prob = scores.get('positive', 0.0)
            negative_prob = scores.get('negative', 0.0)
            
            # Impact is the difference between positive and negative probabilities
            impact = positive_prob - negative_prob
            return round(impact, 4)

        except Exception as exc:
            logger.error("Failed to run FinBERT sentiment analysis: %s", exc)
            return 0.0
