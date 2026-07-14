"""SQLite database wrapper for runs, documents, and outputs.
Replaces the local filesystem JSONL registry and blob storage.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path("data/underwriter.db")
_lock = threading.Lock()


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    application_id TEXT,
                    thread_id TEXT,
                    status TEXT,
                    error TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    application_id TEXT,
                    doc_type TEXT,
                    content BLOB,
                    PRIMARY KEY (application_id, doc_type)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outputs (
                    run_id TEXT,
                    output_type TEXT,
                    content BLOB,
                    PRIMARY KEY (run_id, output_type)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS applicant_profiles (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                    application_id TEXT NOT NULL,
                    applicant_id TEXT,
                    full_name TEXT,
                    date_of_birth TEXT,
                    pan_masked TEXT,
                    mobile_masked TEXT,
                    employment_type TEXT,
                    employer_or_business TEXT,
                    address TEXT,
                    city TEXT,
                    state TEXT,
                    product TEXT,
                    requested_amount REAL,
                    tenor_months INTEGER,
                    indicative_rate_pct REAL,
                    credit_score INTEGER,
                    active_loans INTEGER,
                    delinquencies_12m INTEGER,
                    enquiries_6m INTEGER,
                    net_monthly_income REAL,
                    net_monthly_income_source TEXT,
                    foir_pct REAL,
                    avg_bank_balance REAL,
                    vintage_months INTEGER,
                    payment_returns_count INTEGER,
                    raw_json TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_applicant_profiles_application_id
                ON applicant_profiles(application_id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS salary_credits (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    txn_date TEXT NOT NULL,
                    description TEXT,
                    credit_amount REAL,
                    balance REAL,
                    PRIMARY KEY (run_id, txn_date, credit_amount)
                )
                """
            )
            conn.commit()


_init_db()


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def save_run(record: dict[str, Any]) -> None:
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, application_id, thread_id, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    error=excluded.error
                """,
                (
                    record["run_id"],
                    record["application_id"],
                    record["thread_id"],
                    record["status"],
                    record.get("error"),
                    record["created_at"],
                ),
            )
            conn.commit()


def get_run(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)


def list_runs() -> list[dict[str, Any]]:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM runs ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]


def save_document(application_id: str, doc_type: str, content: bytes) -> None:
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO documents (application_id, doc_type, content)
                VALUES (?, ?, ?)
                ON CONFLICT(application_id, doc_type) DO UPDATE SET content=excluded.content
                """,
                (application_id, doc_type, content),
            )
            conn.commit()


def get_document(application_id: str, doc_type: str) -> bytes | None:
    with get_conn() as conn:
        cur = conn.execute("SELECT content FROM documents WHERE application_id = ? AND doc_type = ?", (application_id, doc_type))
        row = cur.fetchone()
        return row[0] if row else None


def save_output(run_id: str, output_type: str, content: bytes) -> None:
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO outputs (run_id, output_type, content)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id, output_type) DO UPDATE SET content=excluded.content
                """,
                (run_id, output_type, content),
            )
            conn.commit()


def get_output(run_id: str, output_type: str) -> bytes | None:
    with get_conn() as conn:
        cur = conn.execute("SELECT content FROM outputs WHERE run_id = ? AND output_type = ?", (run_id, output_type))
        row = cur.fetchone()
        return row[0] if row else None


def save_applicant_profile(record: dict[str, Any]) -> None:
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO applicant_profiles (
                    run_id, application_id, applicant_id, full_name, date_of_birth,
                    pan_masked, mobile_masked, employment_type, employer_or_business,
                    address, city, state, product, requested_amount, tenor_months,
                    indicative_rate_pct, credit_score, active_loans, delinquencies_12m,
                    enquiries_6m, net_monthly_income, net_monthly_income_source,
                    foir_pct, avg_bank_balance, vintage_months, payment_returns_count,
                    raw_json, created_at
                ) VALUES (
                    :run_id, :application_id, :applicant_id, :full_name, :date_of_birth,
                    :pan_masked, :mobile_masked, :employment_type, :employer_or_business,
                    :address, :city, :state, :product, :requested_amount, :tenor_months,
                    :indicative_rate_pct, :credit_score, :active_loans, :delinquencies_12m,
                    :enquiries_6m, :net_monthly_income, :net_monthly_income_source,
                    :foir_pct, :avg_bank_balance, :vintage_months, :payment_returns_count,
                    :raw_json, :created_at
                )
                ON CONFLICT(run_id) DO UPDATE SET
                    application_id=excluded.application_id, applicant_id=excluded.applicant_id,
                    full_name=excluded.full_name, date_of_birth=excluded.date_of_birth,
                    pan_masked=excluded.pan_masked, mobile_masked=excluded.mobile_masked,
                    employment_type=excluded.employment_type, employer_or_business=excluded.employer_or_business,
                    address=excluded.address, city=excluded.city, state=excluded.state,
                    product=excluded.product, requested_amount=excluded.requested_amount,
                    tenor_months=excluded.tenor_months, indicative_rate_pct=excluded.indicative_rate_pct,
                    credit_score=excluded.credit_score, active_loans=excluded.active_loans,
                    delinquencies_12m=excluded.delinquencies_12m, enquiries_6m=excluded.enquiries_6m,
                    net_monthly_income=excluded.net_monthly_income,
                    net_monthly_income_source=excluded.net_monthly_income_source,
                    foir_pct=excluded.foir_pct, avg_bank_balance=excluded.avg_bank_balance,
                    vintage_months=excluded.vintage_months, payment_returns_count=excluded.payment_returns_count,
                    raw_json=excluded.raw_json
                """,
                record,
            )
            conn.commit()


def get_applicant_profile_by_run_id(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM applicant_profiles WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def save_salary_credits(run_id: str, credits: list[dict[str, Any]]) -> None:
    with _lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM salary_credits WHERE run_id = ?", (run_id,))
            conn.executemany(
                """
                INSERT INTO salary_credits (run_id, txn_date, description, credit_amount, balance)
                VALUES (:run_id, :txn_date, :description, :credit_amount, :balance)
                """,
                [{**c, "run_id": run_id} for c in credits],
            )
            conn.commit()


def get_salary_credits_by_run_id(run_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM salary_credits WHERE run_id = ? ORDER BY txn_date DESC", (run_id,)
        )
        return [dict(row) for row in cur.fetchall()]
