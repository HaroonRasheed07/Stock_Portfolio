"""
Abstract LLM provider interface and package init.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class LLMProvider(ABC):
    """Abstract interface for optional LLM providers (OpenAI, Claude, Ollama)."""

    @abstractmethod
    async def generate_explanation(self, prompt: str, context: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    async def summarize_news(self, news_items: list) -> str:
        pass
