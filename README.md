1. Backend (FastAPI + LangGraph pipeline)
 
  cd ai-underwriter-service
  source .venv/bin/activate      # venv already set up with all deps installed
  uvicorn src.api.main:app --reload
 
  This starts the API on http://localhost:8000 (interactive docs at /docs).
 
  If you want to use real LLM calls instead of the deterministic fallback, first add your key:
  cp .env.example .env   # then edit .env and set OPENAI_API_KEY=sk-...
  (Not required — the system runs fully without it.)
 
  2. Frontend (React demo UI)
 
  In a second terminal:
  cd frontend
  npm install    # first time only
  npm run dev
 
  Open http://localhost:5173 — pick an application (APP-001 through APP-015), click Run, watch the per-node progress, and see the
  decision + download links.
