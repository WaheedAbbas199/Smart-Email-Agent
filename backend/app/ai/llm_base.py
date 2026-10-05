"""LLM provider abstraction. Swap providers by implementing this interface."""
from abc import ABC, abstractmethod
from datetime import date

from app.ai.schemas import EmailAnalysisResult


class LLMError(Exception):
    """Provider/network failure."""


class LLMOutputError(LLMError):
    """Provider returned invalid/unparseable structured output."""


class LLMClient(ABC):
    name: str = "llm"

    @abstractmethod
    def analyze_email(self, payload: dict, preferences: dict, today: date) -> EmailAnalysisResult: ...

    @abstractmethod
    def draft_reply(self, payload: dict, analysis: dict, instructions: str | None = None) -> str: ...
