"""
Stock Portfolio Intelligence Platform - Configuration Management
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


# Well-known browser/frontend origins that are ALWAYS allowed regardless of
# environment: local development on localhost plus the production Vercel
# frontend. These are merged with any additional origins from the
# CORS_ORIGINS environment variable. Keeping the production origin here means
# the frontend -> backend connection works from code without relying on manual
# Render environment-variable edits. These are frontend/browser origins only —
# the backend URL intentionally is NOT listed.
ALWAYS_ALLOWED_CORS_ORIGINS: tuple = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://stock-portfolio-frontend-tau.vercel.app",
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Optional[Path] = None
    UPLOAD_DIR: Optional[Path] = None

    # Database
    DATABASE_URL: str = "sqlite:///./data/portfolio.db"

    # Server
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"

    # Cache TTL (seconds)
    PRICE_CACHE_TTL: int = 300          # 5 minutes
    FUNDAMENTALS_CACHE_TTL: int = 86400  # 24 hours
    NEWS_CACHE_TTL: int = 1800           # 30 minutes
    TECHNICAL_CACHE_TTL: int = 900       # 15 minutes
    ANALYSIS_CACHE_TTL: int = 3600       # 1 hour
    STOCK_INFO_CACHE_TTL: int = 43200    # 12 hours

    # Optional API Keys
    FINNHUB_API_KEY: Optional[str] = None

    # LLM Configuration
    LLM_PROVIDER: str = "none"  # none | openai | anthropic | ollama
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # CORS (comma-separated browser/frontend origins). These are ADDITIONAL
    # custom origins merged on top of the always-allowed well-known frontends
    # (local dev + production Vercel, see ALWAYS_ALLOWED_CORS_ORIGINS below).
    # Keep browser/frontend origins here only — never the backend URL.
    CORS_ORIGINS: str = ""

    # Data Settings
    MAX_CONCURRENT_REQUESTS: int = 5
    DATA_REFRESH_INTERVAL: int = 30  # minutes

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = {
        "env_file": str(Path(__file__).resolve().parent.parent.parent / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def model_post_init(self, __context) -> None:
        if self.DATA_DIR is None:
            self.DATA_DIR = self.BASE_DIR / "data"
        if self.UPLOAD_DIR is None:
            self.UPLOAD_DIR = self.DATA_DIR / "uploads"
        # Ensure directories exist
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# Singleton settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
