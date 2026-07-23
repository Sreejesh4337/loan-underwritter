"""FastAPI service — wraps the LangGraph pipeline with a file-upload API.
Run with: uvicorn src.api.main:app --reload
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.runs_store import append_run, get_run, list_runs
from src.api.schemas import (
    ApplicantProfileResponse,
    RunCreateResponse,
    RunStatusResponse,
    SalaryCreditResponse,
    UploadResponse,
)
from src.graph.build_graph import DEFAULT_CHECKPOINT_DB, compile_graph
from src.db import (
    save_document,
    get_document,
    get_output,
    get_applicant_profile_by_run_id,
    get_salary_credits_by_run_id,
    save_document_fingerprint,
)
from src.schemas.underwriting import DocumentType
from src.validation.document_validator import validate_document
from src.validation.document_dedup import check_duplicates, compute_file_hash

EXPECTED_SLOT_TYPES: dict[str, DocumentType] = {
    "bank_statement": DocumentType.BANK_STATEMENT,
    "kyc_and_credit": DocumentType.KYC_AND_CREDIT,
    "income_details": DocumentType.INCOME_DETAILS,
}

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="AI Underwriting Analyst", description="Loan underwriting recommendation service — upload documents, get AI-powered risk assessment.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def _new_run_id() -> str:
    return "run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_application_id() -> str:
    """Auto-generate the next APP-XXX id based on db."""
    runs = list_runs()
    existing = []
    for r in runs:
        if r["application_id"].startswith("APP-"):
            try:
                existing.append(int(r["application_id"].split("-")[1]))
            except ValueError:
                pass
    next_num = max(existing, default=0) + 1
    return f"APP-{next_num:03d}"


from langfuse.langchain import CallbackHandler
from langfuse import propagate_attributes, get_client

def _execute(application_id: str, run_id: str, thread_id: str, resume: bool, doc_hashes: dict[str, str] | None = None) -> None:
    try:
        langfuse_handler = CallbackHandler()
    except Exception as e:
        print(f"Warning: Langfuse init failed (check API keys): {e}")
        langfuse_handler = None

    graph = compile_graph(DEFAULT_CHECKPOINT_DB)
    
    config = {"configurable": {"thread_id": thread_id}}
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]

    try:
        def _invoke_graph():
            if resume:
                return graph.invoke(None, config=config)
            else:
                initial_state = {
                    "application_id": application_id,
                    "run_id": run_id,
                    "thread_id": thread_id,
                    "input_paths": {}, # Removed logic expecting paths
                }
                return graph.invoke(initial_state, config=config)

        if langfuse_handler:
            with propagate_attributes(session_id=application_id, tags=["underwriting-pipeline"]):
                final_state = _invoke_graph()
        else:
            final_state = _invoke_graph()

        status = final_state.get("run_status", "failed")
        run_error = None
        if status == "failed_input":
            messages = [e.get("message", "") for e in final_state.get("errors") or [] if e.get("message")]
            run_error = "; ".join(messages) or None
        append_run(
            {
                "run_id": run_id,
                "application_id": application_id,
                "thread_id": thread_id,
                "status": status,
                "error": run_error,
                "created_at": _now(),
            }
        )

        # Save document fingerprints only on successful completion
        if status == "completed" and doc_hashes:
            for doc_type, file_hash in doc_hashes.items():
                try:
                    save_document_fingerprint(file_hash, doc_type, application_id, run_id)
                except Exception as fp_exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Failed to save fingerprint for %s in run %s: %s",
                        doc_type, run_id, fp_exc,
                    )

        if langfuse_handler:
            langfuse_client = get_client()
            if langfuse_client:
                langfuse_client.flush()

    except Exception as exc:
        append_run(
            {
                "run_id": run_id,
                "application_id": application_id,
                "thread_id": thread_id,
                "status": "failed",
                "error": str(exc),
                "created_at": _now(),
            }
        )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/applications/upload", response_model=UploadResponse)
async def upload_and_run(
    background_tasks: BackgroundTasks,
    bank_statement: UploadFile = File(..., description="Bank statement PDF"),
    kyc_and_credit: UploadFile = File(..., description="KYC & Credit PDF"),
    income_details: UploadFile = File(..., description="Income details XLSX"),
) -> UploadResponse:
    """Accept 3 uploaded documents, save them to DB, and trigger the underwriting pipeline."""
    contents = {
        "bank_statement": await bank_statement.read(),
        "kyc_and_credit": await kyc_and_credit.read(),
        "income_details": await income_details.read(),
    }

    errors: dict[str, str] = {}
    for field_name, expected_type in EXPECTED_SLOT_TYPES.items():
        message = validate_document(expected_type, contents[field_name])
        if message:
            errors[field_name] = message

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Document validation failed.", "errors": errors},
        )

    # ── Deduplication check: block entire upload if ANY document is in cooldown ──
    duplicates = check_duplicates(contents)
    if duplicates:
        dup_detail = {
            doc_type: {
                "previous_application_id": info.previous_application_id,
                "processed_at": info.processed_at,
                "cooldown_until": info.cooldown_until,
                "days_remaining": info.days_remaining,
            }
            for doc_type, info in duplicates.items()
        }
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Document(s) already processed within the cooldown period.",
                "duplicates": dup_detail,
            },
        )

    application_id = _next_application_id()

    # Compute hashes now so we can save them after the pipeline succeeds
    doc_hashes = {doc_type: compute_file_hash(data) for doc_type, data in contents.items()}

    save_document(application_id, "bank_statement", contents["bank_statement"])
    save_document(application_id, "kyc_and_credit", contents["kyc_and_credit"])
    save_document(application_id, "income_details", contents["income_details"])

    # Create and queue a run
    run_id = _new_run_id()
    thread_id = f"{application_id}:{run_id}"
    append_run(
        {"run_id": run_id, "application_id": application_id, "thread_id": thread_id, "status": "queued", "created_at": _now()}
    )
    background_tasks.add_task(_execute, application_id, run_id, thread_id, False, doc_hashes)
    return UploadResponse(application_id=application_id, run_id=run_id, thread_id=thread_id, status="queued")

#get function
@app.get("/runs", response_model=list[RunStatusResponse])
def get_all_runs() -> list[RunStatusResponse]:
    runs = []
    for r in list_runs():
        applicant_name = None
        decision = None
        
        # Stale run cleanup: Mark runs older than 10 minutes that are still processing as failed.
        if r.get("status") in ("queued", "running"):
            try:
                created_at = datetime.fromisoformat(r["created_at"])
                if (datetime.now(timezone.utc) - created_at).total_seconds() > 600:
                    r["status"] = "failed"
                    r["error"] = "Processing timed out after 10 minutes due to unexpected error or server restart."
                    append_run(r)
            except Exception:
                pass

        if r.get("status") == "completed":
            content = get_output(r["run_id"], "decision.json")
            if content:
                try:
                    decision_data = json.loads(content.decode("utf-8"))
                    applicant_name = decision_data.get("applicant", {}).get("full_name")
                    decision = decision_data.get("decision")
                except Exception:
                    pass
        runs.append(RunStatusResponse(**r, applicant_name=applicant_name, decision=decision))
    return runs


@app.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run_status(run_id: str) -> RunStatusResponse:
    record = get_run(run_id)
    if record is None:
        raise HTTPException(404, f"unknown run_id {run_id!r}")

    current_step = None
    step_status: dict = {}
    try:
        graph = compile_graph(DEFAULT_CHECKPOINT_DB)
        state = graph.get_state({"configurable": {"thread_id": record["thread_id"]}})
        step_status = state.values.get("step_status", {})
        running = [n for n, s in step_status.items() if s.get("status") == "running"]
        current_step = running[0] if running else None
    except Exception:
        pass

    return RunStatusResponse(**record, current_step=current_step, step_status=step_status)


@app.post("/runs/{run_id}/resume", response_model=RunStatusResponse)
def resume_run(run_id: str, background_tasks: BackgroundTasks) -> RunStatusResponse:
    record = get_run(run_id)
    if record is None:
        raise HTTPException(404, f"unknown run_id {run_id!r}")

    record["error"] = None
    append_run({**record, "status": "queued"})
    background_tasks.add_task(_execute, record["application_id"], run_id, record["thread_id"], True)
    return RunStatusResponse(**record, status="queued")


@app.get("/runs/{run_id}/decision")
def get_decision(run_id: str) -> dict:
    content = get_output(run_id, "decision.json")
    if not content:
        raise HTTPException(404, "Decision not yet available.")
    return json.loads(content.decode("utf-8"))


@app.get("/runs/{run_id}/profile", response_model=ApplicantProfileResponse)
def get_applicant_profile(run_id: str) -> ApplicantProfileResponse:
    profile = get_applicant_profile_by_run_id(run_id)
    if not profile:
        raise HTTPException(404, "Applicant profile not yet available.")
    profile.pop("raw_json", None)
    return ApplicantProfileResponse(**profile)


@app.get("/runs/{run_id}/salary-credits", response_model=list[SalaryCreditResponse])
def get_salary_credits(run_id: str) -> list[SalaryCreditResponse]:
    return [SalaryCreditResponse(**row) for row in get_salary_credits_by_run_id(run_id)]


@app.get("/runs/{run_id}/memo")
def get_memo(run_id: str) -> Response:
    content = get_output(run_id, "memo.pdf")
    if not content:
        raise HTTPException(404, "Memo not yet available.")
    return Response(content=content, media_type="application/pdf")


@app.get("/runs/{run_id}/cashflow")
def get_cashflow(run_id: str) -> Response:
    content = get_output(run_id, "cashflow.xlsx")
    if not content:
        raise HTTPException(404, "Cashflow not yet available.")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
