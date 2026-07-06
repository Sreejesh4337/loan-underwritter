import { useEffect, useRef, useState } from "react";

const API_BASE = "/api";
const APPLICATION_IDS = Array.from({ length: 15 }, (_, i) => `APP-${String(i + 1).padStart(3, "0")}`);

// Mirrors the node order in src/graph/build_graph.py — this is a thin demo
// view, not a generic graph visualizer, so the order is hardcoded.
const NODE_ORDER = [
  "plan",
  "parse_documents",
  "extract_kyc",
  "extract_income",
  "extract_bank_statement",
  "merge_and_cross_check",
  "compute_metrics",
  "evaluate_policy",
  "decide",
  "generate_outputs",
  "done",
];

const DECISION_COLORS = { approve: "#1e7e34", refer: "#b8860b", decline: "#a71d2a" };
const STEP_COLORS = { done: "#1e7e34", running: "#0d6efd", failed: "#a71d2a", pending: "#ccc" };

async function api(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function StepStatusList({ stepStatus }) {
  return (
    <ul style={{ listStyle: "none", padding: 0, display: "flex", flexWrap: "wrap", gap: 8 }}>
      {NODE_ORDER.map((node) => {
        const status = stepStatus?.[node]?.status || "pending";
        return (
          <li
            key={node}
            style={{
              padding: "4px 10px",
              borderRadius: 12,
              background: STEP_COLORS[status],
              color: "white",
              fontSize: 12,
            }}
          >
            {node}
          </li>
        );
      })}
    </ul>
  );
}

function DecisionBadge({ decision }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "6px 20px",
        borderRadius: 6,
        background: DECISION_COLORS[decision] || "#666",
        color: "white",
        fontWeight: "bold",
        fontSize: 18,
      }}
    >
      {decision?.toUpperCase()}
    </span>
  );
}

export default function App() {
  const [applicationId, setApplicationId] = useState(APPLICATION_IDS[0]);
  const [runId, setRunId] = useState(null);
  const [status, setStatus] = useState(null);
  const [decision, setDecision] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const startRun = async () => {
    setError(null);
    setDecision(null);
    setStatus(null);
    try {
      const result = await api(`/applications/${applicationId}/runs`, { method: "POST" });
      setRunId(result.run_id);
    } catch (e) {
      setError(e.message);
    }
  };

  const resumeRun = async () => {
    setError(null);
    try {
      await api(`/runs/${runId}/resume`, { method: "POST" });
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    if (!runId) return undefined;

    const poll = async () => {
      try {
        const s = await api(`/runs/${runId}`);
        setStatus(s);
        if (s.status === "completed") {
          const d = await api(`/runs/${runId}/decision`);
          setDecision(d);
          clearInterval(pollRef.current);
        } else if (s.status === "failed" || s.status === "failed_input") {
          clearInterval(pollRef.current);
        }
      } catch (e) {
        setError(e.message);
        clearInterval(pollRef.current);
      }
    };

    poll();
    pollRef.current = setInterval(poll, 1000);
    return () => clearInterval(pollRef.current);
  }, [runId]);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 720, margin: "40px auto", padding: "0 16px" }}>
      <h1>AI Underwriting Analyst</h1>
      <p style={{ color: "#666" }}>
        Sandboxed demo — reads a loan application, checks it against the lending policy, and recommends a decision.
        Read-only; a human always reviews the result.
      </p>

      <section style={{ marginBottom: 24 }}>
        <label>
          Application:{" "}
          <select value={applicationId} onChange={(e) => setApplicationId(e.target.value)}>
            {APPLICATION_IDS.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>{" "}
        <button onClick={startRun}>Run</button>
        {status?.status === "failed_input" && <button onClick={resumeRun}>Resume</button>}
      </section>

      {error && <p style={{ color: "#a71d2a" }}>Error: {error}</p>}

      {status && (
        <section style={{ marginBottom: 24 }}>
          <h3>
            Run {status.run_id} — {status.status}
          </h3>
          <StepStatusList stepStatus={status.step_status} />
        </section>
      )}

      {decision && (
        <section>
          <h3>Result</h3>
          <p>
            <strong>{decision.applicant.full_name}</strong> — {decision.loan_request.product},{" "}
            {decision.loan_request.requested_amount.toLocaleString()} INR
          </p>
          <DecisionBadge decision={decision.decision} />
          <h4>Reasons</h4>
          <ul>
            {decision.fired_rules.filter((r) => r.fired).length === 0 && <li>No decline or refer rules fired.</li>}
            {decision.fired_rules
              .filter((r) => r.fired)
              .map((r) => (
                <li key={r.rule_id}>
                  ({r.rule_id}) {r.message}
                </li>
              ))}
          </ul>
          <p>
            <a href={`${API_BASE}/runs/${runId}/memo`} target="_blank" rel="noreferrer">
              Download memo (PDF)
            </a>{" "}
            ·{" "}
            <a href={`${API_BASE}/runs/${runId}/cashflow`} target="_blank" rel="noreferrer">
              Download cash-flow summary (Excel)
            </a>
          </p>
        </section>
      )}
    </div>
  );
}
