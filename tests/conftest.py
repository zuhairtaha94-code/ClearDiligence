"""Keep offline tests isolated from the user's real API credentials."""
import dotenv
import pytest


@pytest.fixture(autouse=True)
def isolated_provider_environment(monkeypatch):
    for key in ("LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_FALLBACK_MODEL", "GEMINI_FALLBACK_MODELS", "GEMINI_BACKUP_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "TAVILY_API_KEY", "OPENCORPORATES_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
