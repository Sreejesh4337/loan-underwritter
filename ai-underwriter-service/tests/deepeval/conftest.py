import json
import os
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

# Ensure environment variables are loaded so OPENAI_API_KEY is available
load_dotenv()

from src.graph.build_graph import run_underwriting
from src.inputs import resolve_input_paths
from src.policy_engine.loader import DEFAULT_POLICY_PATH

# ---------------------------------------------------------------------------
# DeepEval Setup
# ---------------------------------------------------------------------------

# Make sure we use the configured model, defaulting to gpt-4o
os.environ["DEEPEVAL_EVALUATOR_MODEL"] = os.environ.get("DEEPEVAL_JUDGE_MODEL", "gpt-4o")

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "fixtures"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _load_fixture(app_id: str) -> dict | None:
    path = FIXTURES_DIR / f"{app_id}.expected.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)

def _get_app_ids():
    return sorted(p.stem.replace(".expected", "") for p in FIXTURES_DIR.glob("APP-*.expected.yaml"))

@pytest.fixture(scope="session")
def app_ids():
    return _get_app_ids()

@pytest.fixture(scope="session")
def ground_truth_fixtures():
    """Load all APP-*.expected.yaml ground truth files into a dictionary."""
    fixtures = {}
    for app_id in _get_app_ids():
        fixture = _load_fixture(app_id)
        if fixture:
            fixtures[app_id] = fixture
    return fixtures

@pytest.fixture(scope="session")
def pipeline_results(app_ids):
    """
    Run the pipeline for each application once per test session.
    This avoids re-running the heavy graph nodes multiple times across different test files.
    """
    results = {}
    run_id = "deepeval-test-run"
    
    for app_id in app_ids:
        # Resolve inputs
        input_paths = resolve_input_paths(app_id)
        
        # Run graph
        final_state = run_underwriting(app_id, run_id, input_paths)
        results[app_id] = final_state
        
    return results

@pytest.fixture(scope="session")
def policy_yaml_text():
    """Read the lending policy YAML content for testing."""
    return DEFAULT_POLICY_PATH.read_text(encoding="utf-8")
