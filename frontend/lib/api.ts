const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface UploadResponse {
  application_id: string;
  run_id: string;
  thread_id: string;
  status: string;
}

export interface StepStatusEntry {
  status: string; // "pending" | "running" | "done" | "failed"
  attempt_count: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface RunStatusResponse {
  run_id: string;
  thread_id: string;
  application_id: string;
  status: string;
  current_step: string | null;
  step_status: Record<string, StepStatusEntry>;
  error: string | null;
  created_at: string;
  updated_at: string | null;
  applicant_name?: string | null;
  decision?: string | null;
}

export interface DecisionResponse {
  application_id: string;
  run_id: string;
  decision: string; // "approve" | "decline" | "refer"
  rationale_text: string;
  advisory_notes: string[];
  credit_bureau: {
    credit_score: number;
    active_loans: number;
    delinquencies_12m: number;
    enquiries_6m: number;
  };
  metrics: {
    net_monthly_income: number;
    foir_pct: number;
    proposed_emi: number;
    avg_bank_balance: number;
    vintage_months: number;
    payment_returns_count: number;
  };
  applicant: {
    full_name: string;
    employment_type: string;
  };
  fired_rules: Array<{
    rule_id: string;
    tier: string;
    fired: boolean;
    message: string;
  }>;
}

/**
 * Upload 3 documents and trigger the underwriting pipeline.
 */
export async function uploadAndRun(files: {
  bank: File;
  kyc: File;
  income: File;
}): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("bank_statement", files.bank);
  formData.append("kyc_and_credit", files.kyc);
  formData.append("income_details", files.income);

  const res = await fetch(`${API_BASE}/applications/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Upload failed (${res.status}): ${errorText}`);
  }

  return res.json();
}

/**
 * Poll the current status of an underwriting run.
 */
export async function getRunStatus(runId: string): Promise<RunStatusResponse> {
  const res = await fetch(`${API_BASE}/runs/${runId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch run status (${res.status})`);
  }
  return res.json();
}

/**
 * Resume a failed run.
 */
export async function resumeRun(runId: string): Promise<RunStatusResponse> {
  const res = await fetch(`${API_BASE}/runs/${runId}/resume`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Failed to resume run (${res.status})`);
  }
  return res.json();
}

/**
 * Fetch all runs.
 */
export async function getAllRuns(): Promise<RunStatusResponse[]> {
  const res = await fetch(`${API_BASE}/runs`);
  if (!res.ok) {
    throw new Error(`Failed to fetch runs (${res.status})`);
  }
  return res.json();
}

/**
 * Fetch the full decision JSON for a completed run.
 */
export async function getDecision(runId: string): Promise<DecisionResponse> {
  const res = await fetch(`${API_BASE}/runs/${runId}/decision`);
  if (!res.ok) {
    throw new Error(`Failed to fetch decision (${res.status})`);
  }
  return res.json();
}

/**
 * Get the download URL for the underwriting memo PDF.
 */
export function getMemoUrl(runId: string): string {
  return `${API_BASE}/runs/${runId}/memo`;
}

/**
 * Get the download URL for the cashflow Excel file.
 */
export function getCashflowUrl(runId: string): string {
  return `${API_BASE}/runs/${runId}/cashflow`;
}
