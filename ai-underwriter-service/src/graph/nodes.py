"""LangGraph node implementations.

Each node takes the full `UnderwritingState` and returns a partial-update
dict that LangGraph merges into state (with the `errors`/`token_usage`
reducers accumulating rather than overwriting). Nodes are pure orchestration
glue — the actual logic lives in src/parsers, src/extractors, src/analysis,
src/policy_engine, and src/skills, all independently unit-tested.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.cross_check import check_name_consistency, cross_check
from src.analysis.metrics import compute_metrics
from src.db import save_applicant_profile, save_salary_credits
from src.extractors.bank_statement_extractor import extract_bank_statement
from src.extractors.income_extractor import extract_income
from src.extractors.kyc_extractor import extract_kyc
from src.graph.state import UnderwritingState, new_step_status
from src.llm.models import get_strong_model
from src.llm.pricing import estimate_cost_usd
from src.parsers.bank_statement_parser import ParsedBankStatement
from src.parsers.base import ParserError
from src.parsers.income_parser import ParsedIncomeDocument
from src.parsers.kyc_parser import ParsedKycDocument
from src.parsers.registry import parse_bank_statement, parse_income, parse_kyc
from src.policy_engine.engine import evaluate as evaluate_policy
from src.policy_engine.loader import DEFAULT_POLICY_PATH, load_policy, policy_file_hash
from src.schemas.underwriting import (
    Applicant,
    CreditBureau,
    Decision,
    FiredRule,
    FinancialMetrics,
    LoanRequest,
    RunUsage,
    StepUsage,
    Transaction,
    TransactionCategory,
    UnderwritingResult,
)
from src.skills.cashflow_generator import generate_cashflow_excel
from src.skills.memo_generator import generate_underwriting_memo

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mark_running(state: UnderwritingState, node: str) -> dict:
    step_status = dict(state.get("step_status", {}))
    entry = dict(step_status.get(node, new_step_status()))
    entry["status"] = "running"
    entry["attempt_count"] = entry.get("attempt_count", 0) + 1
    entry["started_at"] = _now()
    step_status[node] = entry
    return step_status


def _mark_done(step_status: dict, node: str, error: str | None = None) -> dict:
    entry = dict(step_status.get(node, new_step_status()))
    entry["status"] = "failed" if error else "done"
    entry["finished_at"] = _now()
    entry["error"] = error
    step_status[node] = entry
    return step_status


def _content_hash(*paths: str) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------


def plan_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "plan")
    required = ("bank_statement", "kyc_and_credit", "income_details")
    plan_steps = []
    missing = []

    from src.db import get_document

    for doc_type in required:
        content = get_document(state["application_id"], doc_type)
        if not content:
            missing.append(doc_type)
        plan_steps.append({"node": f"parse[{doc_type}]", "reason": f"read the {doc_type} document into clean text"})

    plan_steps += [
        {"node": "extract_kyc / extract_income / extract_bank_statement", "reason": "pull structured fields per document (parallel, cheap model)"},
        {"node": "merge_and_cross_check", "reason": "reconcile documents, pick net-income source"},
        {"node": "compute_metrics", "reason": "EMI/FOIR/balance/etc — pure Python, no LLM"},
        {"node": "evaluate_policy", "reason": "apply lending_policy.yaml deterministically"},
        {"node": "decide", "reason": "author the rationale narrative (strong model)"},
        {"node": "generate_outputs", "reason": "memo PDF + cash-flow Excel + decision.json"},
    ]

    run_status = "failed_input" if missing else "running"
    step_status = _mark_done(step_status, "plan", error=f"missing input file(s): {missing}" if missing else None)

    return {
        "plan": plan_steps,
        "run_status": run_status,
        "step_status": step_status,
        "errors": [{"node": "plan", "message": f"missing input: {d}"} for d in missing],
        "created_at": state.get("created_at") or _now(),
        "updated_at": _now(),
    }


def route_after_plan(state: UnderwritingState) -> str:
    return "handle_bad_input" if state["run_status"] == "failed_input" else "parse_documents"


# --------------------------------------------------------------------------
# parse_documents
# --------------------------------------------------------------------------


import tempfile


def parse_documents_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "parse_documents")
    parsed: dict = {}
    errors = []

    from src.db import get_document

    def _parse_with_temp(doc_type: str, parse_fn) -> dict:
        content = get_document(state["application_id"], doc_type)
        if not content:
            raise ParserError(f"Document {doc_type} not found in database.")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf" if doc_type != "income_details" else ".xlsx") as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            return asdict(parse_fn(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)

    try:
        parsed["kyc"] = _parse_with_temp("kyc_and_credit", parse_kyc)
    except ParserError as exc:
        errors.append({"node": "parse_documents", "message": f"kyc: {exc}"})

    try:
        parsed["income"] = _parse_with_temp("income_details", parse_income)
    except ParserError as exc:
        errors.append({"node": "parse_documents", "message": f"income: {exc}"})

    try:
        parsed["bank_statement"] = _parse_with_temp("bank_statement", parse_bank_statement)
    except ParserError as exc:
        errors.append({"node": "parse_documents", "message": f"bank_statement: {exc}"})

    run_status = "failed_input" if errors else state["run_status"]
    step_status = _mark_done(step_status, "parse_documents", error="; ".join(e["message"] for e in errors) or None)

    return {
        "parsed": parsed,
        "run_status": run_status,
        "step_status": step_status,
        "errors": errors,
        "updated_at": _now(),
    }


def route_after_parse(state: UnderwritingState) -> str | list[str]:
    if state["run_status"] == "failed_input":
        return "handle_bad_input"
    return ["extract_kyc", "extract_income", "extract_bank_statement"]


# --------------------------------------------------------------------------
# extraction (parallel fan-out)
# --------------------------------------------------------------------------


def extract_kyc_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "extract_kyc")
    doc = ParsedKycDocument(**state["parsed"]["kyc"])
    applicant, loan_request, credit_bureau, usage = extract_kyc(doc, state["application_id"])

    extracted_kyc = {
        "applicant": applicant.model_dump(mode="json"),
        "loan_request": loan_request.model_dump(mode="json"),
        "credit_bureau": credit_bureau.model_dump(mode="json"),
    }
    step_status = _mark_done(step_status, "extract_kyc")
    return {
        "extracted_kyc": extracted_kyc,
        "step_status": step_status,
        "token_usage": [usage.model_dump()],
        "updated_at": _now(),
    }


def extract_income_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "extract_income")
    doc = ParsedIncomeDocument(**state["parsed"]["income"])
    income, usage = extract_income(doc)

    step_status = _mark_done(step_status, "extract_income")
    return {
        "extracted_income": income.model_dump(mode="json"),
        "step_status": step_status,
        "token_usage": [usage.model_dump()],
        "updated_at": _now(),
    }


def extract_bank_statement_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "extract_bank_statement")
    d = state["parsed"]["bank_statement"]
    doc = ParsedBankStatement(raw_text=d["raw_text"], source_file=d["source_file"])

    account_holder, account_type, transactions, usage = extract_bank_statement(doc)

    extracted_bank_statement = {
        "account_holder": account_holder,
        "account_type": account_type,
        "transactions": [t.model_dump(mode="json") for t in transactions],
    }
    step_status = _mark_done(step_status, "extract_bank_statement")
    return {
        "extracted_bank_statement": extracted_bank_statement,
        "step_status": step_status,
        "token_usage": [usage.model_dump()],
        "updated_at": _now(),
    }


# --------------------------------------------------------------------------
# merge_and_cross_check
# --------------------------------------------------------------------------


def merge_and_cross_check_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "merge_and_cross_check")

    applicant = Applicant(**state["extracted_kyc"]["applicant"])
    income = state["extracted_income"]
    bank_statement = state["extracted_bank_statement"]
    transactions = [Transaction(**t) for t in bank_statement["transactions"]]
    parsed_income = state["parsed"]["income"]
    tolerance_pct = load_policy(DEFAULT_POLICY_PATH)["thresholds"]["income_consistency"]["tolerance_pct"]

    result = cross_check(
        employment_type=applicant.employment_type,
        kyc_full_name=applicant.full_name,
        income_sheet_applicant_name=income["applicant_name"],
        bank_account_holder_name=bank_statement["account_holder"] or applicant.full_name,
        income_sheet_average_net_pay=income.get("average_net_pay"),
        transactions=transactions,
        monthly_table_header=parsed_income.get("monthly_table_header"),
        monthly_rows=parsed_income.get("monthly_rows"),
        tolerance_pct=tolerance_pct,
    )

    step_status = _mark_done(step_status, "merge_and_cross_check")
    return {
        "cross_check": {
            "net_monthly_income": result.net_monthly_income,
            "net_monthly_income_source": result.net_monthly_income_source,
            "name_consistency_ok": result.name_consistency_ok,
            "income_consistency_ok": result.income_consistency_ok,
            "warnings": result.warnings,
        },
        "step_status": step_status,
        "updated_at": _now(),
    }


# --------------------------------------------------------------------------
# compute_metrics (zero LLM calls)
# --------------------------------------------------------------------------


def compute_metrics_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "compute_metrics")
    applicant = Applicant(**state["extracted_kyc"]["applicant"])
    loan_request = LoanRequest(**state["extracted_kyc"]["loan_request"])
    credit_bureau = CreditBureau(**state["extracted_kyc"]["credit_bureau"])
    transactions = [Transaction(**t) for t in state["extracted_bank_statement"]["transactions"]]
    cc = state["cross_check"]

    metrics = compute_metrics(
        employment_type=applicant.employment_type,
        net_monthly_income=cc["net_monthly_income"],
        net_monthly_income_source=cc["net_monthly_income_source"],
        transactions=transactions,
        requested_amount=loan_request.requested_amount,
        tenor_months=loan_request.tenor_months,
        indicative_rate_pct=loan_request.indicative_rate_pct,
        vintage_months=state["extracted_income"]["vintage_months"],
        name_consistency_ok=cc["name_consistency_ok"],
        income_consistency_ok=cc["income_consistency_ok"],
    )

    try:
        save_applicant_profile({
            "run_id": state["run_id"],
            "application_id": state["application_id"],
            "applicant_id": applicant.applicant_id,
            "full_name": applicant.full_name,
            "date_of_birth": applicant.date_of_birth.isoformat() if applicant.date_of_birth else None,
            "pan_masked": applicant.pan_masked,
            "mobile_masked": applicant.mobile_masked,
            "employment_type": applicant.employment_type.value,
            "employer_or_business": applicant.employer_or_business,
            "address": applicant.address,
            "city": applicant.city,
            "state": applicant.state,
            "product": loan_request.product,
            "requested_amount": loan_request.requested_amount,
            "tenor_months": loan_request.tenor_months,
            "indicative_rate_pct": loan_request.indicative_rate_pct,
            "credit_score": credit_bureau.credit_score,
            "active_loans": credit_bureau.active_loans,
            "delinquencies_12m": credit_bureau.delinquencies_12m,
            "enquiries_6m": credit_bureau.enquiries_6m,
            "net_monthly_income": metrics.net_monthly_income,
            "net_monthly_income_source": metrics.net_monthly_income_source,
            "foir_pct": metrics.foir_pct,
            "avg_bank_balance": metrics.avg_bank_balance,
            "vintage_months": metrics.vintage_months,
            "payment_returns_count": metrics.payment_returns_count,
            "raw_json": json.dumps({
                "applicant": applicant.model_dump(mode="json"),
                "loan_request": loan_request.model_dump(mode="json"),
                "credit_bureau": credit_bureau.model_dump(mode="json"),
                "metrics": metrics.model_dump(mode="json"),
            }),
            "created_at": _now(),
        })
    except Exception as exc:
        logger.error(f"Failed to persist applicant profile for run {state['run_id']}: {exc}")

    try:
        salary_transactions = [t for t in transactions if t.category == TransactionCategory.SALARY]
        save_salary_credits(
            state["run_id"],
            [
                {
                    "txn_date": t.txn_date.isoformat(),
                    "description": t.description,
                    "credit_amount": t.credit,
                    "balance": t.balance,
                }
                for t in salary_transactions
            ],
        )
    except Exception as exc:
        logger.error(f"Failed to persist salary credits for run {state['run_id']}: {exc}")

    step_status = _mark_done(step_status, "compute_metrics")
    return {"metrics": metrics.model_dump(mode="json"), "step_status": step_status, "updated_at": _now()}


# --------------------------------------------------------------------------
# evaluate_policy (zero LLM calls)
# --------------------------------------------------------------------------


def evaluate_policy_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "evaluate_policy")
    metrics = FinancialMetrics(**state["metrics"])
    credit_score = state["extracted_kyc"]["credit_bureau"]["credit_score"]

    result = evaluate_policy(metrics, credit_score, DEFAULT_POLICY_PATH)

    step_status = _mark_done(step_status, "evaluate_policy")
    return {
        "policy_result": {
            "decision": result.decision.value,
            "fired_rules": [r.model_dump(mode="json") for r in result.fired_rules],
            "override_applied": result.override_applied,
            "policy_file_hash": policy_file_hash(),
        },
        "step_status": step_status,
        "updated_at": _now(),
    }


# --------------------------------------------------------------------------
# decide (strong model) — narrative + advisory notes only, never the decision
# --------------------------------------------------------------------------


def decide_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "decide")
    policy_result = state["policy_result"]
    decision = policy_result["decision"]
    fired_rules = policy_result["fired_rules"]

    model = get_strong_model()
    prompt = (
        "You are writing the rationale section of an underwriting memo. The decision "
        f"has ALREADY been made by a deterministic policy engine: {decision.upper()}. "
        "Do not propose a different decision. Write 2-4 sentences explaining the "
        "decision in plain English, citing the rule IDs and figures below, plus up to "
        "3 short advisory notes (qualitative observations, not new rules).\n\n"
        "CRITICAL: Format all currency values using 'INR' (e.g., INR 150,000). Never use the $ or ₹ symbols.\n\n"
        f"Metrics: {json.dumps(state['metrics'])}\n"
        f"Fired rules: {json.dumps(fired_rules)}\n"
        f"Cross-check: {json.dumps(state['cross_check'])}\n\n"
        'Respond as JSON: {"rationale_text": "...", "advisory_notes": ["...", ...]}'
    )
    response = model.invoke(prompt)
    usage_meta = getattr(response, "usage_metadata", None) or {}
    input_tokens = usage_meta.get("input_tokens", 0)
    output_tokens = usage_meta.get("output_tokens", 0)

    # Safely strip markdown code blocks before JSON parsing
    content = response.content.strip()
    if content.startswith("```json"):
        content = content.split("```json", 1)[1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse LLM JSON decision: {exc}. Content was: {content}")
        payload = {}

    rationale_text = payload.get("rationale_text", f"Recommendation is {decision.upper()}")
    advisory_notes = payload.get("advisory_notes", [])
    from src.llm.models import STRONG_MODEL_NAME

    usage = StepUsage(
        step="decide",
        model=STRONG_MODEL_NAME,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(STRONG_MODEL_NAME, input_tokens, output_tokens),
    )

    step_status = _mark_done(step_status, "decide")
    return {
        "decision": {"rationale_text": rationale_text, "advisory_notes": advisory_notes},
        "step_status": step_status,
        "token_usage": [usage.model_dump()],
        "updated_at": _now(),
    }


# --------------------------------------------------------------------------
# generate_outputs
# --------------------------------------------------------------------------


def _assemble_result(state: UnderwritingState) -> UnderwritingResult:
    token_usage = state.get("token_usage", [])
    usage = RunUsage(
        total_input_tokens=sum(u.get("input_tokens", 0) for u in token_usage),
        total_output_tokens=sum(u.get("output_tokens", 0) for u in token_usage),
        total_cost_usd=sum(u.get("cost_usd", 0.0) for u in token_usage),
        per_step=[StepUsage(**u) for u in token_usage],
    )
    return UnderwritingResult(
        application_id=state["application_id"],
        run_id=state["run_id"],
        thread_id=state["thread_id"],
        applicant=Applicant(**state["extracted_kyc"]["applicant"]),
        loan_request=LoanRequest(**state["extracted_kyc"]["loan_request"]),
        credit_bureau=CreditBureau(**state["extracted_kyc"]["credit_bureau"]),
        metrics=FinancialMetrics(**state["metrics"]),
        transactions=[Transaction(**t) for t in state["extracted_bank_statement"]["transactions"]],
        decision=Decision(state["policy_result"]["decision"]),
        fired_rules=[FiredRule(**r) for r in state["policy_result"]["fired_rules"]],
        rationale_text=state["decision"]["rationale_text"],
        advisory_notes=state["decision"]["advisory_notes"],
        generated_at=datetime.now(timezone.utc),
        usage=usage,
    )


def generate_outputs_node(state: UnderwritingState) -> dict:
    step_status = _mark_running(state, "generate_outputs")
    result = _assemble_result(state)

    from src.db import save_output

    outputs: dict[str, str] = {}
    errors = []
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_memo:
        tmp_memo_path = Path(tmp_memo.name)
    try:
        generate_underwriting_memo(result, tmp_memo_path)
        save_output(state["run_id"], "memo.pdf", tmp_memo_path.read_bytes())
        outputs["memo_pdf"] = "db://outputs/memo.pdf"
    except Exception as exc:
        errors.append({"node": "generate_outputs", "message": f"memo generation failed: {exc}"})
    finally:
        tmp_memo_path.unlink(missing_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_cashflow:
        tmp_cashflow_path = Path(tmp_cashflow.name)
    try:
        generate_cashflow_excel(result, tmp_cashflow_path)
        save_output(state["run_id"], "cashflow.xlsx", tmp_cashflow_path.read_bytes())
        outputs["cashflow_xlsx"] = "db://outputs/cashflow.xlsx"
    except Exception as exc:
        errors.append({"node": "generate_outputs", "message": f"cashflow generation failed: {exc}"})
    finally:
        tmp_cashflow_path.unlink(missing_ok=True)

    decision_json = result.model_dump_json(indent=2).encode("utf-8")
    save_output(state["run_id"], "decision.json", decision_json)
    outputs["decision_json"] = "db://outputs/decision.json"

    step_status = _mark_done(step_status, "generate_outputs", error="; ".join(e["message"] for e in errors) or None)
    return {"outputs": outputs, "step_status": step_status, "errors": errors, "updated_at": _now()}


# --------------------------------------------------------------------------
# done / handle_bad_input
# --------------------------------------------------------------------------


def done_node(state: UnderwritingState) -> dict:
    step_status = _mark_done(dict(state.get("step_status", {})), "done")
    return {"run_status": "completed", "step_status": step_status, "updated_at": _now()}


def handle_bad_input_node(state: UnderwritingState) -> dict:
    step_status = _mark_done(dict(state.get("step_status", {})), "handle_bad_input")
    return {"run_status": "failed_input", "step_status": step_status, "updated_at": _now()}
