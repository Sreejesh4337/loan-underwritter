import { AlertTriangle, Bot, CheckCircle2, ChevronDown, Info, XCircle, Zap } from "lucide-react";
import { METRIC_FIELDS, RULE_TIER_EXPLAIN } from "../lib/metricInfo";
import DecisionBadge from "./DecisionBadge";
import DownloadLinks from "./DownloadLinks";
import Tooltip from "./Tooltip";

const TIER_ICONS = { decline: XCircle, refer: AlertTriangle, approve: CheckCircle2, override: Zap };

function InfoTrigger({ content }) {
  return (
    <Tooltip content={content}>
      <Info size={13} className="info-icon" tabIndex={0} title={content} />
    </Tooltip>
  );
}

export default function ResultPanel({ decision, runId }) {
  const { applicant, loan_request: loanRequest, metrics, credit_bureau: creditBureau, fired_rules: firedRules, advisory_notes: advisoryNotes } = decision;
  const activeRules = firedRules.filter((r) => r.fired);
  const rationale = decision.rationale_text || "No rationale narrative was generated for this run.";

  return (
    <section className="result-panel">
      <div className="chat-message">
        <div className="chat-avatar">
          <Bot size={18} />
        </div>
        <div className="chat-bubble">
          <header className="chat-bubble-header">
            <strong>{applicant.full_name}</strong> — {loanRequest.product}, {loanRequest.requested_amount.toLocaleString()} INR
            <DecisionBadge decision={decision.decision} />
          </header>

          <p className="chat-rationale">{rationale}</p>

          <div className="reasoning-breakdown">
            <h4>Why this decision</h4>
            {activeRules.length === 0 ? (
              <p className="reason-empty">
                <CheckCircle2 size={16} /> No decline or refer rules fired against the lending policy.
              </p>
            ) : (
              <ul className="reason-list">
                {activeRules.map((r) => {
                  const TierIcon = TIER_ICONS[r.tier] || Info;
                  return (
                    <li key={r.rule_id} className={`reason-item tier-${r.tier}`}>
                      <TierIcon size={16} />
                      <span>{r.message}</span>
                      <InfoTrigger content={RULE_TIER_EXPLAIN[r.tier]} />
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <details className="metrics-section" open>
            <summary>
              <ChevronDown size={14} className="chevron" /> Key metrics
            </summary>
            <div className="metrics-grid">
              {METRIC_FIELDS.map((f) => (
                <div className="metric-tile" key={f.key}>
                  <span className="metric-label">
                    {f.label}
                    <InfoTrigger content={f.explain(metrics, creditBureau)} />
                  </span>
                  <span className="metric-value">{f.format(metrics, creditBureau)}</span>
                </div>
              ))}
            </div>
          </details>

          {advisoryNotes && advisoryNotes.length > 0 && (
            <div className="advisory-notes">
              <h4>
                <AlertTriangle size={14} /> Advisory notes
              </h4>
              <ul>
                {advisoryNotes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}

          <DownloadLinks runId={runId} />
        </div>
      </div>
    </section>
  );
}
