"""Wires the graph topology together and exposes the entrypoints used by the
CLI, the FastAPI service, and the eval harness.

Graph topology (see the project plan for the full rationale):

    plan -> parse_documents -> [extract_kyc | extract_income | extract_bank_statement]
         -> merge_and_cross_check -> compute_metrics -> evaluate_policy -> decide
         -> generate_outputs -> done

with a conditional escape to handle_bad_input from `plan` or `parse_documents`
whenever a required file is missing/corrupt.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from src.graph import nodes
from src.graph.state import UnderwritingState

DEFAULT_CHECKPOINT_DB = Path("data/checkpoints.db")


def _build_graph() -> StateGraph:
    g = StateGraph(UnderwritingState)

    g.add_node("plan", nodes.plan_node)
    g.add_node("parse_documents", nodes.parse_documents_node)
    g.add_node("extract_kyc", nodes.extract_kyc_node)
    g.add_node("extract_income", nodes.extract_income_node)
    g.add_node("extract_bank_statement", nodes.extract_bank_statement_node)
    g.add_node("merge_and_cross_check", nodes.merge_and_cross_check_node)
    g.add_node("compute_metrics", nodes.compute_metrics_node)
    g.add_node("evaluate_policy", nodes.evaluate_policy_node)
    g.add_node("decide", nodes.decide_node)
    g.add_node("generate_outputs", nodes.generate_outputs_node)
    g.add_node("done", nodes.done_node)
    g.add_node("handle_bad_input", nodes.handle_bad_input_node)

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", nodes.route_after_plan, ["parse_documents", "handle_bad_input"])
    g.add_conditional_edges(
        "parse_documents",
        nodes.route_after_parse,
        ["extract_kyc", "extract_income", "extract_bank_statement", "handle_bad_input"],
    )
    g.add_edge("extract_kyc", "merge_and_cross_check")
    g.add_edge("extract_income", "merge_and_cross_check")
    g.add_edge("extract_bank_statement", "merge_and_cross_check")
    g.add_edge("merge_and_cross_check", "compute_metrics")
    g.add_edge("compute_metrics", "evaluate_policy")
    g.add_edge("evaluate_policy", "decide")
    g.add_edge("decide", "generate_outputs")
    g.add_edge("generate_outputs", "done")
    g.add_edge("done", END)
    g.add_edge("handle_bad_input", END)

    return g


def compile_graph(checkpoint_db_path: Path = DEFAULT_CHECKPOINT_DB):
    checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(checkpoint_db_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    return _build_graph().compile(checkpointer=saver)


def run_underwriting(
    application_id: str,
    run_id: str,
    input_paths: dict[str, str],
    checkpoint_db_path: Path = DEFAULT_CHECKPOINT_DB,
) -> dict:
    """Stable entrypoint used by the eval harness and the FastAPI service —
    invokes the graph and returns the final state dict (callers assemble a
    typed UnderwritingResult from state["outputs"]["decision_json"] or via
    the same construction nodes.generate_outputs_node uses internally)."""
    graph = compile_graph(checkpoint_db_path)
    thread_id = f"{application_id}:{run_id}"
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "application_id": application_id,
        "run_id": run_id,
        "thread_id": thread_id,
        "input_paths": input_paths,
    }
    return graph.invoke(initial_state, config=config)
