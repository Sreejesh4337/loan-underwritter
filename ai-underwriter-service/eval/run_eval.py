"""Scored test harness — the week-3 "make tests a gate" deliverable.

    python -m eval.run_eval --apps all
    python -m eval.run_eval --apps APP-001,APP-013 --min-accuracy 1.0

Compares each application's actual pipeline output against its
eval/fixtures/APP-*.expected.yaml ground truth (see
scripts/derive_ground_truth.py for how those were derived), and reports
decision accuracy, metric error, memo/Excel quality proxies, and
tokens/cost/duration per application. Exits non-zero if decision_accuracy
falls below --min-accuracy, which is what turns this into a CI-style gate.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from eval.checks import metric_within_tolerance, score_excel_quality, score_memo_quality
from src.graph.build_graph import run_underwriting
from src.inputs import resolve_input_paths

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"

console = Console()


def _load_fixture(app_id: str) -> dict | None:
    path = FIXTURES_DIR / f"{app_id}.expected.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def evaluate_one(app_id: str, run_id: str) -> dict:
    fixture = _load_fixture(app_id)
    if fixture is None:
        return {"app_id": app_id, "skipped": True, "reason": "no ground-truth fixture"}

    start = time.perf_counter()
    final_state = run_underwriting(app_id, run_id, resolve_input_paths(app_id))
    duration_s = time.perf_counter() - start

    if final_state.get("run_status") != "completed":
        return {"app_id": app_id, "skipped": False, "error": f"run_status={final_state.get('run_status')}"}

    actual_decision = final_state["policy_result"]["decision"]
    decision_correct = actual_decision == fixture["expected_decision"]

    metric_results = {}
    metrics = final_state["metrics"]
    # credit_score lives on CreditBureau (extracted from the KYC document), not
    # on FinancialMetrics (which holds only values computed from the loan/statement).
    credit_bureau = final_state["extracted_kyc"]["credit_bureau"]
    metric_sources = {**metrics, "credit_score": credit_bureau["credit_score"]}
    for field, expected in fixture.get("expected_metrics", {}).items():
        actual_value = metric_sources.get(field)
        if actual_value is None:
            metric_results[field] = {"ok": False, "delta": None}
            continue
        ok, delta = metric_within_tolerance(actual_value, expected)
        metric_results[field] = {"ok": ok, "delta": delta, "actual": actual_value, "expected": expected["value"]}

    applicant_name = final_state["extracted_kyc"]["applicant"]["full_name"]
    fired_rules = final_state["policy_result"]["fired_rules"]
    memo_score, memo_failed = score_memo_quality(
        final_state["outputs"]["memo_pdf"], applicant_name, actual_decision, any(r["fired"] for r in fired_rules)
    )
    excel_score, excel_failed = score_excel_quality(final_state["outputs"]["cashflow_xlsx"])

    token_usage = final_state.get("token_usage", [])
    total_tokens = sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in token_usage)
    total_cost = sum(u.get("cost_usd", 0.0) for u in token_usage)

    return {
        "app_id": app_id,
        "skipped": False,
        "confidence": fixture.get("confidence", "draft"),
        "decision_correct": decision_correct,
        "actual_decision": actual_decision,
        "expected_decision": fixture["expected_decision"],
        "metrics": metric_results,
        "memo_score": memo_score,
        "memo_failed_checks": memo_failed,
        "excel_score": excel_score,
        "excel_failed_checks": excel_failed,
        "tokens": total_tokens,
        "cost_usd": total_cost,
        "duration_s": duration_s,
    }


def print_report(results: list[dict]) -> None:
    table = Table(title="Underwriting Eval Report")
    for col in ("App", "Decision", "Expected", "OK", "Metrics OK", "Memo", "Excel", "Tokens", "Cost $", "Time (s)"):
        table.add_column(col)

    for r in results:
        if r.get("skipped"):
            table.add_row(r["app_id"], "-", "-", "SKIPPED", r.get("reason", ""), "-", "-", "-", "-", "-")
            continue
        if "error" in r:
            table.add_row(r["app_id"], "-", "-", "ERROR", r["error"], "-", "-", "-", "-", "-")
            continue
        metrics_ok = f"{sum(1 for m in r['metrics'].values() if m['ok'])}/{len(r['metrics'])}"
        table.add_row(
            r["app_id"],
            r["actual_decision"],
            r["expected_decision"],
            "✓" if r["decision_correct"] else "✗",
            metrics_ok,
            f"{r['memo_score']:.2f}",
            f"{r['excel_score']:.2f}",
            str(r["tokens"]),
            f"{r['cost_usd']:.4f}",
            f"{r['duration_s']:.2f}",
        )
    console.print(table)


def summarize(results: list[dict]) -> dict:
    scored = [r for r in results if not r.get("skipped") and "error" not in r]
    if not scored:
        return {"decision_accuracy": 0.0, "n_scored": 0}

    return {
        "n_scored": len(scored),
        "n_skipped": sum(1 for r in results if r.get("skipped")),
        "n_errored": sum(1 for r in results if "error" in r),
        "decision_accuracy": sum(1 for r in scored if r["decision_correct"]) / len(scored),
        "mean_memo_score": sum(r["memo_score"] for r in scored) / len(scored),
        "mean_excel_score": sum(r["excel_score"] for r in scored) / len(scored),
        "total_tokens": sum(r["tokens"] for r in scored),
        "total_cost_usd": sum(r["cost_usd"] for r in scored),
        "mean_duration_s": sum(r["duration_s"] for r in scored) / len(scored),
        "failing_apps": [r["app_id"] for r in scored if not r["decision_correct"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the underwriting eval harness")
    parser.add_argument("--apps", default="all", help='"all" or a comma-separated list, e.g. APP-001,APP-013')
    parser.add_argument("--min-accuracy", type=float, default=1.0)
    args = parser.parse_args()

    if args.apps == "all":
        app_ids = sorted(p.stem.replace(".expected", "") for p in FIXTURES_DIR.glob("APP-*.expected.yaml"))
    else:
        app_ids = args.apps.split(",")

    run_id = "eval-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = [evaluate_one(app_id, run_id) for app_id in app_ids]

    print_report(results)
    summary = summarize(results)
    console.print(summary)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"run_{run_id}.json"
    report_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str))
    console.print(f"Full report written to {report_path}")

    if summary["decision_accuracy"] < args.min_accuracy:
        console.print(
            f"[red]FAIL[/red]: decision_accuracy {summary['decision_accuracy']:.2f} < --min-accuracy {args.min_accuracy}"
        )
        return 1
    console.print("[green]PASS[/green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
