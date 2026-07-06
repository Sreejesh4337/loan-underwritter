"""Integration test for the FastAPI service — exercises the full graph via
HTTP, so it's slower than the unit suite but validates the whole wiring
(background task execution, checkpointing, file serving)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_full_run_lifecycle():
    create_response = client.post("/applications/APP-001/runs")
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    # TestClient executes BackgroundTasks synchronously before returning,
    # so the run has already completed by the time we poll status.
    status_response = client.get(f"/runs/{run_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    decision_response = client.get(f"/runs/{run_id}/decision")
    assert decision_response.status_code == 200
    assert decision_response.json()["decision"] == "approve"

    memo_response = client.get(f"/runs/{run_id}/memo")
    assert memo_response.status_code == 200
    assert memo_response.headers["content-type"] == "application/pdf"

    cashflow_response = client.get(f"/runs/{run_id}/cashflow")
    assert cashflow_response.status_code == 200

    list_response = client.get("/runs")
    assert list_response.status_code == 200
    assert any(r["run_id"] == run_id for r in list_response.json())


def test_unknown_application_returns_404():
    response = client.post("/applications/APP-DOES-NOT-EXIST/runs")
    assert response.status_code == 404


def test_unknown_run_returns_404():
    response = client.get("/runs/does-not-exist")
    assert response.status_code == 404


def test_eval_endpoint():
    response = client.post("/eval/run", params={"apps": "APP-001,APP-010"})
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["decision_accuracy"] == 1.0
    assert body["passed"] is True

    latest_response = client.get("/eval/latest")
    assert latest_response.status_code == 200
