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
from src.api.schemas import RunCreateResponse, RunStatusResponse, UploadResponse
from src.graph.build_graph import DEFAULT_CHECKPOINT_DB, compile_graph
from src.db import save_document, get_output

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


def _execute(application_id: str, run_id: str, thread_id: str, resume: bool) -> None:
    graph = compile_graph(DEFAULT_CHECKPOINT_DB)
    config = {"configurable": {"thread_id": thread_id}}
    try:
        if resume:
            final_state = graph.invoke(None, config=config)
        else:
            initial_state = {
                "application_id": application_id,
                "run_id": run_id,
                "thread_id": thread_id,
                "input_paths": {}, # Removed logic expecting paths
            }
            final_state = graph.invoke(initial_state, config=config)
        append_run(
            {
                "run_id": run_id,
                "application_id": application_id,
                "thread_id": thread_id,
                "status": final_state.get("run_status", "failed"),
                "created_at": _now(),
            }
        )
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
    application_id = _next_application_id()

    save_document(application_id, "bank_statement", await bank_statement.read())
    save_document(application_id, "kyc_and_credit", await kyc_and_credit.read())
    save_document(application_id, "income_details", await income_details.read())

    # Create and queue a run
    run_id = _new_run_id()
    thread_id = f"{application_id}:{run_id}"
    append_run(
        {"run_id": run_id, "application_id": application_id, "thread_id": thread_id, "status": "queued", "created_at": _now()}
    )
    background_tasks.add_task(_execute, application_id, run_id, thread_id, False)
    return UploadResponse(application_id=application_id, run_id=run_id, thread_id=thread_id, status="queued")


@app.get("/runs", response_model=list[RunStatusResponse])
def get_all_runs() -> list[RunStatusResponse]:
    return [RunStatusResponse(**r) for r in list_runs()]


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

    append_run({**record, "status": "queued"})
    background_tasks.add_task(_execute, record["application_id"], run_id, record["thread_id"], True)
    return RunStatusResponse(**record, status="queued")


@app.get("/runs/{run_id}/decision")
def get_decision(run_id: str) -> dict:
    content = get_output(run_id, "decision.json")
    if not content:
        raise HTTPException(404, "Decision not yet available.")
    return json.loads(content.decode("utf-8"))


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
