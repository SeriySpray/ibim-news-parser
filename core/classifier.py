import os
import logging

logger = logging.getLogger(__name__)


class NewsClassifierZeroShot:
    """Zero-shot classifier that requires NO manual training.
    Uses 'MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7' to evaluate relevance on the fly.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.pipeline = None
        return cls._instance

    def _lazy_init(self):
        """Lazy initialization of the Hugging Face zero-shot classification pipeline."""
        if self.pipeline is None:
            logger.info("Initializing Zero-Shot classifier model (mDeBERTa)...")
            from transformers import pipeline
            model_name = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
            
            # CPU only execution to prevent issues on standard PCs without CUDA GPU
            self.pipeline = pipeline(
                "zero-shot-classification",
                model=model_name,
                device=-1  # CPU only
            )
            logger.info("Zero-Shot classifier loaded successfully.")

    def predict(self, title: str, content: str, company_name: str) -> float:
        """Evaluate how relevant the news article is to the company.
        Returns a relevance score from 0.0 to 1.0.
        """
        text = f"{(title or '').strip()} {(content or '').strip()}".strip()
        if not text:
            return 0.0

        try:
            self._lazy_init()
            # Truncate text to fit typical limits (rough estimation for CPU friendly execution)
            text_truncated = text[:1000]
            
            # Construct candidate labels in Ukrainian
            candidate_labels = [
                f"фінансова новина про компанію {company_name or 'бізнес'}",
                "реклама, спам, загальні новини або інші теми"
            ]
            
            # Predict
            result = self.pipeline(
                text_truncated,
                candidate_labels=candidate_labels,
                multi_label=False
            )
            
            if not result or 'scores' not in result or 'labels' not in result:
                return 0.0
                
            # Find score of the relevant label
            relevant_label = candidate_labels[0]
            for label, score in zip(result['labels'], result['scores']):
                if label == relevant_label:
                    return round(score, 4)
            return 0.0
        except Exception as e:
            logger.error("Failed to run Zero-Shot relevance analysis: %s", e)
            return 0.0
