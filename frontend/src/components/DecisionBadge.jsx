import { CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { DECISION_COLORS } from "../lib/constants";

const DECISION_ICONS = { approve: CheckCircle2, refer: AlertTriangle, decline: XCircle };

export default function DecisionBadge({ decision }) {
  const Icon = DECISION_ICONS[decision];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 20px",
        borderRadius: 6,
        background: DECISION_COLORS[decision] || "#666",
        color: "white",
        fontWeight: "bold",
        fontSize: 18,
      }}
    >
      {Icon && <Icon size={18} />}
      {decision?.toUpperCase()}
    </span>
  );
}
