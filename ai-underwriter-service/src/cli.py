"""CLI entrypoint — the always-working demo path.

    python -m src.cli run APP-001
    python -m src.cli run APP-001 --kill-after compute_metrics   # simulate a mid-run crash
    python -m src.cli resume APP-001:run_20260703T120000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from src.graph.build_graph import DEFAULT_CHECKPOINT_DB, compile_graph
from src.inputs import resolve_input_paths


def _new_run_id() -> str:
    return "run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _print_summary(final_state: dict) -> None:
    status = final_state.get("run_status")
    print(f"\nrun_status: {status}")
    if status == "failed_input":
        print("errors:", json.dumps(final_state.get("errors", []), indent=2))
        return

    policy_result = final_state.get("policy_result", {})
    print(f"decision: {policy_result.get('decision', '?').upper()}")
    for rule in policy_result.get("fired_rules", []):
        if rule["fired"]:
            print(f"  - ({rule['rule_id']}) {rule['message']}")
    decision = final_state.get("decision", {})
    if decision.get("rationale_text"):
        print(f"\nrationale: {decision['rationale_text']}")

    outputs = final_state.get("outputs", {})
    if outputs:
        print("\noutputs:")
        for k, v in outputs.items():
            print(f"  {k}: {v}")

    usage = final_state.get("token_usage", [])
    total_cost = sum(u.get("cost_usd", 0.0) for u in usage)
    total_tokens = sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usage)
    print(f"\ntokens: {total_tokens}  cost_usd: {total_cost:.4f}")


def cmd_run(application_id: str, kill_after: str | None) -> int:
    run_id = _new_run_id()
    thread_id = f"{application_id}:{run_id}"
    graph = compile_graph(DEFAULT_CHECKPOINT_DB)
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "application_id": application_id,
        "run_id": run_id,
        "thread_id": thread_id,
        "input_paths": resolve_input_paths(application_id),
    }

    print(f"Starting run {thread_id}")
    print(f"Trace this run any time with: python -m src.cli resume {thread_id}")

    if kill_after:
        for update in graph.stream(initial_state, config=config, stream_mode="updates"):
            node_name = next(iter(update))
            print(f"  [node completed] {node_name}")
            if node_name == kill_after:
                print(f"\n--kill-after={kill_after}: simulating a crash right after this node.")
                print(f"Resume with: python -m src.cli resume {thread_id}")
                return 1
        final_state = graph.get_state(config).values
    else:
        final_state = graph.invoke(initial_state, config=config)

    _print_summary(final_state)
    return 0 if final_state.get("run_status") == "completed" else 1


def cmd_resume(thread_id: str) -> int:
    graph = compile_graph(DEFAULT_CHECKPOINT_DB)
    config = {"configurable": {"thread_id": thread_id}}

    existing = graph.get_state(config)
    if not existing.values:
        print(f"No checkpoint found for thread_id {thread_id!r}", file=sys.stderr)
        return 2

    completed = [n for n, s in existing.values.get("step_status", {}).items() if s.get("status") == "done"]
    print(f"Resuming {thread_id} — already completed: {completed or '(none)'}")

    final_state = graph.invoke(None, config=config)  # None input -> LangGraph resumes from the last checkpoint
    _print_summary(final_state)
    return 0 if final_state.get("run_status") == "completed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Underwriting Analyst CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run a single application through the pipeline")
    run_parser.add_argument("application_id")
    run_parser.add_argument("--kill-after", default=None, help="Debug: stop right after this node completes")

    resume_parser = sub.add_parser("resume", help="Resume an interrupted run")
    resume_parser.add_argument("thread_id", help="e.g. APP-001:run_20260703T120000Z")

    args = parser.parse_args()
    if args.command == "run":
        return cmd_run(args.application_id, args.kill_after)
    if args.command == "resume":
        return cmd_resume(args.thread_id)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
