"""Integration tests for the full LangGraph pipeline — the graph is compiled
and invoked end-to-end (deterministic-fallback extraction, since no
OPENAI_API_KEY is configured in test environments), exercising every real
node except the LLM call itself."""

from __future__ import annotations

import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from src.graph.build_graph import _build_graph
from src.inputs import resolve_input_paths


@pytest.fixture
def graph():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    return _build_graph().compile(checkpointer=SqliteSaver(conn))


def _initial_state(app_id: str, run_id: str) -> dict:
    return {
        "application_id": app_id,
        "run_id": run_id,
        "thread_id": f"{app_id}:{run_id}",
        "input_paths": resolve_input_paths(app_id),
    }


class TestFullRun:
    def test_app001_completes_with_approve(self, graph):
        config = {"configurable": {"thread_id": "APP-001:test1"}}
        final_state = graph.invoke(_initial_state("APP-001", "test1"), config=config)

        assert final_state["run_status"] == "completed"
        assert final_state["policy_result"]["decision"] == "approve"
        assert "memo_pdf" in final_state["outputs"]
        assert "cashflow_xlsx" in final_state["outputs"]

    def test_app012_declines_on_payment_returns(self, graph):
        config = {"configurable": {"thread_id": "APP-012:test1"}}
        final_state = graph.invoke(_initial_state("APP-012", "test1"), config=config)

        assert final_state["policy_result"]["decision"] == "decline"
        assert any(r["rule_id"] == "D3_PAYMENT_RETURNS" for r in final_state["policy_result"]["fired_rules"])

    def test_missing_input_file_routes_to_handle_bad_input_without_crashing(self, graph):
        state = _initial_state("APP-001", "test-missing")
        state["input_paths"]["bank_statement"] = "/nonexistent/file.pdf"
        config = {"configurable": {"thread_id": "APP-001:test-missing"}}

        final_state = graph.invoke(state, config=config)

        assert final_state["run_status"] == "failed_input"


class TestResume:
    def test_resume_after_simulated_interruption(self, graph):
        thread_id = "APP-013:test-resume"
        config = {"configurable": {"thread_id": thread_id}}

        # Simulate a partial run by stopping the stream after compute_metrics.
        for update in graph.stream(_initial_state("APP-013", "test-resume"), config=config, stream_mode="updates"):
            if "compute_metrics" in update:
                break

        partial_state = graph.get_state(config).values
        assert partial_state["step_status"]["compute_metrics"]["status"] == "done"
        assert "decide" not in partial_state.get("decision", {})

        final_state = graph.invoke(None, config=config)  # resume

        assert final_state["run_status"] == "completed"
        assert final_state["policy_result"]["decision"] == "approve"  # APP-013's high-income override
        assert final_state["policy_result"]["override_applied"] is True
