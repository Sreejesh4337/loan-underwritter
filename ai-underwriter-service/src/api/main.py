"""FastAPI service — deliberately thin (filesystem-backed, BackgroundTasks,
no queue/database): this is a demo service wrapping the LangGraph pipeline,
not a production system. Run with: uvicorn src.api.main:app --reload
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.api.runs_store import append_run, get_run, list_runs
from src.api.schemas import RunCreateResponse, RunStatusResponse
from src.graph.build_graph import DEFAULT_CHECKPOINT_DB, compile_graph
from src.inputs import resolve_input_paths

app = FastAPI(title="AI Underwriting Analyst", description="Sandboxed loan underwriting recommendation service — read-only, never acts.")

# Demo-scoped: the local Vite dev server runs on a different port than
# uvicorn. Not hardened for production multi-tenant deployment.
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
                "input_paths": resolve_input_paths(application_id),
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


@app.post("/applications/{application_id}/runs", response_model=RunCreateResponse)
def create_run(application_id: str, background_tasks: BackgroundTasks) -> RunCreateResponse:
    app_dir = Path(resolve_input_paths(application_id)["bank_statement"]).parent
    if not app_dir.is_dir():
        raise HTTPException(404, f"unknown application_id {application_id!r}")

    run_id = _new_run_id()
    thread_id = f"{application_id}:{run_id}"
    append_run(
        {"run_id": run_id, "application_id": application_id, "thread_id": thread_id, "status": "queued", "created_at": _now()}
    )
    background_tasks.add_task(_execute, application_id, run_id, thread_id, False)
    return RunCreateResponse(run_id=run_id, thread_id=thread_id, status="queued")


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


def _run_output_path(run_id: str, filename: str) -> Path:
    record = get_run(run_id)
    if record is None:
        raise HTTPException(404, f"unknown run_id {run_id!r}")
    path = Path("data/runs") / record["application_id"] / run_id / "outputs" / filename
    if not path.exists():
        raise HTTPException(404, f"{filename} not yet available for run {run_id!r} (status={record.get('status')})")
    return path


@app.get("/runs/{run_id}/decision")
def get_decision(run_id: str) -> dict:
    path = _run_output_path(run_id, "decision.json")
    return json.loads(path.read_text())


@app.get("/runs/{run_id}/memo")
def get_memo(run_id: str) -> FileResponse:
    return FileResponse(_run_output_path(run_id, "memo.pdf"), media_type="application/pdf")


@app.get("/runs/{run_id}/cashflow")
def get_cashflow(run_id: str) -> FileResponse:
    return FileResponse(
        _run_output_path(run_id, "cashflow.xlsx"),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/eval/run")
def trigger_eval(apps: str = "all", min_accuracy: float = 1.0) -> dict:
    from eval.run_eval import evaluate_one, summarize

    app_ids = (
        sorted(p.stem.replace(".expected", "") for p in Path("eval/fixtures").glob("APP-*.expected.yaml"))
        if apps == "all"
        else apps.split(",")
    )
    run_id = "eval-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = [evaluate_one(app_id, run_id) for app_id in app_ids]
    summary = summarize(results)

    report_path = Path("eval/reports") / f"run_{run_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str))

    return {"report_id": run_id, "summary": summary, "passed": summary["decision_accuracy"] >= min_accuracy}


@app.get("/eval/latest")
def get_latest_eval() -> dict:
    reports = sorted(Path("eval/reports").glob("run_*.json"))
    if not reports:
        raise HTTPException(404, "no eval reports yet — trigger one with POST /eval/run")
    return json.loads(reports[-1].read_text())
