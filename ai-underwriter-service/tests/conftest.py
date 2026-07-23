import pytest


@pytest.fixture(autouse=True)
def _no_llm_by_default(request, monkeypatch):
    """The suite is documented (see test_extractors.py, test_graph.py module
    docstrings) to run in deterministic-fallback mode, i.e. llm_available()
    is False. src/cli.py and src/api/main.py call load_dotenv() on import, so
    a developer's real .env would otherwise leak OPENAI_API_KEY into the test
    process and flip extraction over to the real LLM path.
    
    EXCEPTION: DeepEval tests require the LLM to act as a judge, so we preserve
    the API key for tests in the tests/deepeval directory.
    """
    if "deepeval" not in request.node.nodeid:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

