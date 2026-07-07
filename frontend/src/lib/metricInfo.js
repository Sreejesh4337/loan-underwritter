// Hand-authored explanations — not derived from field names — so tooltips read
// as plain-English underwriting context rather than a restatement of the label.

const money = (v) => `₹${Math.round(v).toLocaleString("en-IN")}`;

export const METRIC_FIELDS = [
  {
    key: "foir_pct",
    label: "FOIR",
    format: (m) => `${m.foir_pct.toFixed(1)}%`,
    explain: () =>
      "Fixed Obligations to Income Ratio — proposed EMI plus existing EMIs, as a percentage of net monthly income. Lower is safer.",
  },
  {
    key: "net_monthly_income",
    label: "Net monthly income",
    format: (m) => money(m.net_monthly_income),
    explain: (m) =>
      m.net_monthly_income_source === "bank_avg_credits"
        ? "Derived from average bank credits — the income document was inconclusive, so this is an estimate, not a stated salary."
        : "Taken directly from the applicant's income document.",
  },
  {
    key: "existing_emis",
    label: "Existing EMIs",
    format: (m) => money(m.existing_emis),
    explain: () => "Sum of EMI outflows already visible in the applicant's bank statement.",
  },
  {
    key: "proposed_emi",
    label: "Proposed EMI",
    format: (m) => money(m.proposed_emi),
    explain: () => "The monthly instalment this loan request would add, at the indicative rate and tenor.",
  },
  {
    key: "avg_bank_balance",
    label: "Avg. bank balance",
    format: (m) => money(m.avg_bank_balance),
    explain: () => "Average end-of-day balance across the statement period — a buffer/liquidity signal.",
  },
  {
    key: "payment_returns_count",
    label: "Payment returns",
    format: (m) => `${m.payment_returns_count}`,
    explain: () => "Number of bounced/returned payments (e.g. insufficient funds) found in the bank statement.",
  },
  {
    key: "salary_credit_months_count",
    label: "Salary credit months",
    format: (m) => (m.salary_credit_months_count == null ? "N/A (self-employed)" : `${m.salary_credit_months_count}`),
    explain: () => "How many months show a recognizable salary credit. Not tracked for self-employed applicants.",
  },
  {
    key: "vintage_months",
    label: "Bank statement vintage",
    format: (m) => `${m.vintage_months} mo`,
    explain: () => "Length of the bank statement history available for this review.",
  },
  {
    key: "unexplained_cash_deposit_flag",
    label: "Unexplained cash deposits",
    format: (m) => (m.unexplained_cash_deposit_flag ? "Yes" : "No"),
    explain: () =>
      "Whether a large cash deposit was found that doesn't match salary or other identifiable sources — a fraud/undisclosed-income risk signal.",
  },
  {
    key: "credit_score",
    label: "Credit score",
    format: (_m, c) => `${c.credit_score}`,
    explain: () => "Bureau credit score at time of application.",
  },
  {
    key: "active_loans",
    label: "Active loans",
    format: (_m, c) => `${c.active_loans}`,
    explain: () => "Number of currently active loans per the credit bureau report.",
  },
  {
    key: "delinquencies_12m",
    label: "Delinquencies (12mo)",
    format: (_m, c) => `${c.delinquencies_12m}`,
    explain: () => "Missed or late payments reported in the last 12 months.",
  },
  {
    key: "enquiries_6m",
    label: "Credit enquiries (6mo)",
    format: (_m, c) => `${c.enquiries_6m}`,
    explain: () => "Number of credit enquiries in the last 6 months — frequent enquiries can signal credit-seeking stress.",
  },
];

export const RULE_TIER_EXPLAIN = {
  decline: "This rule, on its own, is severe enough to decline the application.",
  refer: "This rule flags a risk that needs human underwriter review, but doesn't decline outright.",
  approve: "This rule supports approving the application.",
  override: "This rule was neutralized by a higher-priority policy override (e.g. high income).",
};
