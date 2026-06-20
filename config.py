"""
IBIM News Parser — Configuration module.

Manages API keys, application settings, and file paths.
Configuration is stored as a JSON file in the data/ directory.
"""

import json
import os
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = DATA_DIR / "config.json"
DB_FILE = DATA_DIR / "news.db"
EXPORTS_DIR = DATA_DIR / "exports"

# ── Defaults ───────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "api_keys": {
        "finnhub": "",
        "newsapi": "",
    },
    "default_period_days": 30,
    "max_articles_per_request": 100,
}


class Config:
    """Singleton configuration manager.

    Reads/writes a JSON config file and provides typed accessors
    for API keys and application settings.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = None
        return cls._instance

    # ── I/O ────────────────────────────────────────────────────────
    def load(self):
        """Load config from disk, creating defaults if needed."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            # Merge any new default keys that might have been added
            for key, value in DEFAULT_CONFIG.items():
                if key not in self._data:
                    self._data[key] = value
        else:
            self._data = DEFAULT_CONFIG.copy()
            self.save()

    def save(self):
        """Persist current config to disk."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ── Generic accessors ──────────────────────────────────────────
    def get(self, key, default=None):
        if self._data is None:
            self.load()
        return self._data.get(key, default)

    def set(self, key, value):
        if self._data is None:
            self.load()
        self._data[key] = value
        self.save()

    # ── API key helpers ────────────────────────────────────────────
    def get_api_key(self, service: str) -> str:
        if self._data is None:
            self.load()
        return self._data.get("api_keys", {}).get(service, "")

    def set_api_key(self, service: str, key: str):
        if self._data is None:
            self.load()
        if "api_keys" not in self._data:
            self._data["api_keys"] = {}
        self._data["api_keys"][service] = key
        self.save()
