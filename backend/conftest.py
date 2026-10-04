"""
Project-wide test isolation.

Local docker-compose passes the developer's real LLM keys (DeepSeek + OpenAI fallback) into the
container. Tests must never spend credit or depend on a live provider, so every test starts
exactly like CI: no LLM keys. Tests that need a client mock it (or set keys themselves).
"""
import pytest


@pytest.fixture(autouse=True)
def _no_live_llm(settings):
    settings.OPENAI_API_KEY = ''
    settings.OPENAI_BASE_URL = ''
    settings.LLM_FALLBACK_API_KEY = ''
    settings.OPENAI_IMAGES_API_KEY = ''
