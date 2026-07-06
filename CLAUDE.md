# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

An **AI Underwriting Analyst**: a LangGraph agent that reviews a personal-loan application (bank statement PDF,
KYC/credit PDF, income Excel), checks it against a lending policy, and recommends **approve / refer / decline**.
Sandboxed: the agent only reads and recommends, it never approves, sends, or changes anything, and a human always
reviews the result. Stack: FastAPI + LangGraph + LangChain (OpenAI) + Python backend, thin React (Vite) frontend.

Source documents: `docs/ai-underwriter-team-brief.pdf` (project brief), `docs/LENDING_POLICY.pdf` (the policy,
externalized as `ai-underwriter-service/policy/lending_policy.yaml`), `docs/applications/APP-001..015/` (15 sample
packets used as the fixed eval set).

Full architecture/design rationale: `/home/sreejeshmk/.claude/plans/sequential-crafting-acorn.md`.

## Build / run / test commands

All commands run from `ai-underwriter-service/` with the venv active (`source .venv/bin/activate`; venv created
with `uv venv` + `uv pip install -r requirements.txt`, not raw `pip`, since the system Python is externally managed).

```bash
# Run a single application through the pipeline
python -m src.cli run APP-001
python -m src.cli run APP-001 --kill-after compute_metrics   # simulate a mid-run crash
python -m src.cli resume APP-001:<run_id>                    # resume from the last checkpoint

# Unit + integration tests (105 tests)
python -m pytest tests/ -v

# Score against the fixed 15-app eval set (decision accuracy, metric tolerance, memo/excel quality, tokens/cost)
python -m eval.run_eval --apps all --min-accuracy 1.0
python -m eval.compare_runs eval/reports/run_A.json eval/reports/run_B.json   # before/after diff

# Regenerate eval/fixtures/*.expected.yaml from the sample docs (independent regex extraction, not the
# production LLM/deterministic-fallback extractors — see the script's docstring for why)
python -m scripts.derive_ground_truth

# API service
uvicorn src.api.main:app --reload   # http://localhost:8000, see /docs for OpenAPI

# Frontend (separate terminal, from repo root's frontend/)
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies /api/* to :8000
```

No `OPENAI_API_KEY` is required to run any of the above — every LLM-calling step (the three document extractors,
the decision-narrative step) has a deterministic fallback that activates automatically when the key is unset, so
the pipeline is fully exercised in this sandbox without real API calls (`src/llm/models.py:llm_available()`).

## Architecture

```
plan → parse_documents → [extract_kyc | extract_income | extract_bank_statement]  (parallel)
     → merge_and_cross_check → compute_metrics → evaluate_policy → decide
     → generate_outputs → done
```
(`src/graph/build_graph.py`; conditional escape to `handle_bad_input` from `plan`/`parse_documents` on missing files.)

- **`src/schemas/underwriting.py`** — the shared Pydantic contract (`Applicant`, `FinancialMetrics`, `FiredRule`,
  `UnderwritingResult`, etc.) used by every layer below.
- **`src/parsers/`** — deterministic, no LLM. `pdfplumber` text-mode for the KYC PDF; `pdfplumber` word-position
  table parsing for the bank statement (handles wrapped dates and per-page repeated headers — see the module
  docstring); `openpyxl` direct read for the income sheet (two layouts: salaried vs self-employed).
- **`src/extractors/`** — cheap-model (`gpt-4o-mini`) structured-output extraction per document, with a
  deterministic fallback (used in this sandbox). Bank-statement extraction is deliberately narrow: transaction
  rows are parsed 100% in code; the LLM call (when available) only handles the header block and batched
  classification of any unmatched transaction description.
- **`src/analysis/`** — pure Python: `metrics.py` (EMI/FOIR/balance/counts — zero LLM calls, ever),
  `categorize.py` (regex transaction categorization), `cross_check.py` (net-income source selection).
- **`src/policy_engine/`** — loads `policy/lending_policy.yaml` and evaluates decline → refer → approve rules in
  order, including the high-income override (which neutralizes only the credit-score-band refer rule — other
  refer rules still fire independently). Changing a threshold means editing the YAML, never this code.
- **`src/skills/`** — `memo_generator.py` (ReportLab PDF) and `cashflow_generator.py` (openpyxl, with the
  Summary sheet's ratio cells as formulas referencing a Monthly Trend sheet, which is itself formulas over the
  raw Transactions sheet — the workbook is self-auditable, not a static report). Deterministic, no LLM.
- **`src/graph/`** — `state.py` (the `UnderwritingState` TypedDict + reducers for fields written by the parallel
  extract_* nodes), `nodes.py`, `build_graph.py` (checkpointed via `langgraph-checkpoint-sqlite`, one
  `data/checkpoints.db`, `thread_id = f"{application_id}:{run_id}"`).
- **`src/api/`** — thin FastAPI wrapper (`BackgroundTasks`, a JSONL run registry, no queue/DB).
- **`eval/`** — `fixtures/APP-*.expected.yaml` (ground truth, each tagged `confidence: draft|reviewed`),
  `run_eval.py` (the scoring gate), `checks.py` (tolerance comparison + memo/Excel quality proxies — deliberately
  not an LLM-judge call).
- **`scripts/`** — one-off dev tools (`derive_ground_truth.py`, `score_parsers.py`), not shipped code.

### Scoping decisions (deliberate, not oversights — see the plan doc for full rationale)

- The `decide` node (strong model, `gpt-4o`) authors the rationale narrative only; it cannot override the
  deterministic policy engine's decision. This keeps `decision_accuracy` scoring reproducible.
- Bank-statement transaction extraction is code-primary; KYC/income extraction are LLM-primary — both documents
  are small enough that this doesn't conflict with the token-minimization goal, and it's what the brief's
  "helper agent per document" ask actually calls for.
- Transaction categorization is regex-based against the sample data's fixed vocabulary (`Salary Credit -
  EMP PAYROLL`, `ECS RETURN CHARGES - INSUFF FUNDS`, etc.), with an LLM classification fallback for anything
  unmatched — not claimed as general-purpose robustness.
