import pytest


@pytest.fixture(autouse=True)
def _no_llm_by_default(monkeypatch):
    """The suite is documented (see test_extractors.py, test_graph.py module
    docstrings) to run in deterministic-fallback mode, i.e. llm_available()
    is False. src/cli.py and src/api/main.py call load_dotenv() on import, so
    a developer's real .env would otherwise leak OPENAI_API_KEY into the test
    process and flip extraction over to the real LLM path."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
