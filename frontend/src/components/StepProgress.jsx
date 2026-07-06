import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { NODE_ORDER, STEP_COLORS, STEP_LABELS } from "../lib/constants";

const STEP_ICONS = { done: CheckCircle2, running: Loader2, failed: XCircle, pending: Circle };

export default function StepProgress({ stepStatus, currentStep, runStatus, error }) {
  const doneCount = NODE_ORDER.filter((n) => stepStatus?.[n]?.status === "done").length;
  const currentIndex = currentStep ? NODE_ORDER.indexOf(currentStep) : doneCount;
  const progressPct =
    runStatus === "completed" ? 100 : ((doneCount + (currentStep ? 0.5 : 0)) / NODE_ORDER.length) * 100;

  return (
    <div>
      <h3 style={{ marginBottom: 8 }}>
        Step {Math.min(currentIndex + 1, NODE_ORDER.length)} of {NODE_ORDER.length} — {runStatus}
      </h3>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${progressPct}%` }} />
      </div>
      <ul className="step-track">
        {NODE_ORDER.map((node) => {
          const status = stepStatus?.[node]?.status || "pending";
          const Icon = STEP_ICONS[status];
          return (
            <li
              key={node}
              className={`step-pill${status === "running" ? " is-running" : ""}`}
              style={{ background: STEP_COLORS[status] }}
              aria-current={status === "running" ? "step" : undefined}
            >
              <Icon size={13} className={status === "running" ? "spin-icon" : undefined} />
              {STEP_LABELS[node] || node}
            </li>
          );
        })}
      </ul>
      {error && <p className="step-error">{error}</p>}
    </div>
  );
}
