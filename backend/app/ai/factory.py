from app.ai.gemini_client import GeminiClient
from app.ai.llm_base import LLMClient
from app.ai.mock_llm import MockLLM
from app.config import Settings


def create_llm(settings: Settings) -> LLMClient:
    provider = settings.llm_provider
    if provider == "gemini" and not settings.gemini_api_key:
        raise RuntimeError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
    if provider == "gemini" or (provider == "auto" and settings.gemini_api_key):
        return GeminiClient(settings.gemini_api_key, settings.gemini_model, settings.llm_timeout_seconds,
                            settings.llm_max_retries, settings.max_email_chars)
    return MockLLM()
