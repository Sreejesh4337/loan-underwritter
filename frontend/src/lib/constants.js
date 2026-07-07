export const API_BASE = "/api";
export const APPLICATION_IDS = Array.from({ length: 15 }, (_, i) => `APP-${String(i + 1).padStart(3, "0")}`);

// Mirrors the node order in src/graph/build_graph.py — this is a thin demo
// view, not a generic graph visualizer, so the order is hardcoded.
export const NODE_ORDER = [
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

export const STEP_LABELS = {
  plan: "Plan",
  parse_documents: "Parse documents",
  extract_kyc: "Extract KYC",
  extract_income: "Extract income",
  extract_bank_statement: "Extract bank statement",
  merge_and_cross_check: "Merge & cross-check",
  compute_metrics: "Compute metrics",
  evaluate_policy: "Evaluate policy",
  decide: "Decide",
  generate_outputs: "Generate outputs",
  done: "Done",
};

export const DECISION_COLORS = { approve: "#1e7e34", refer: "#b8860b", decline: "#a71d2a" };
export const STEP_COLORS = { done: "#1e7e34", running: "#0d6efd", failed: "#a71d2a", pending: "#ccc" };
