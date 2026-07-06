import { useEffect, useRef, useState } from "react";
import ResultPanel from "./components/ResultPanel";
import StepProgress from "./components/StepProgress";
import { api } from "./lib/api";
import { APPLICATION_IDS } from "./lib/constants";

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
          <StepProgress
            stepStatus={status.step_status}
            currentStep={status.current_step}
            runStatus={status.status}
            error={status.error}
          />
        </section>
      )}

      {decision && <ResultPanel decision={decision} runId={runId} />}
    </div>
  );
}
