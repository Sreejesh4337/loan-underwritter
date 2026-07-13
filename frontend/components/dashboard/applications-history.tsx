"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  getAllRuns,
  getDecision,
  getMemoUrl,
  getCashflowUrl,
  type RunStatusResponse,
  type DecisionResponse,
} from "@/lib/api";
import { ApplicantProfileCard } from "@/components/dashboard/applicant-profile-card";
import { SalaryCreditsTable } from "@/components/dashboard/salary-credits-table";

export function ApplicationsHistory() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunStatusResponse[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [decisionData, setDecisionData] = useState<DecisionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 8;

  useEffect(() => {
    setIsLoading(true);
    getAllRuns()
      .then((data) => {
        // Sort newest first
        data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        setRuns(data);
      })
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false));
  }, []);

  const handleViewRun = async (runId: string) => {
    try {
      setError(null);
      setDecisionData(null);
      const data = await getDecision(runId);
      setDecisionData(data);
    } catch (e: any) {
      setError(e.message || "Failed to fetch decision details");
    }
  };

  const getDecisionLabel = (decision: string) => {
    switch (decision.toLowerCase()) {
      case "approve": return "Approved";
      case "decline":
      case "reject": return "Rejected";
      case "refer": return "Referred";
      default: return decision;
    }
  };

  const getDecisionColor = (decision: string) => {
    switch (decision.toLowerCase()) {
      case "approve": return "text-emerald-accent";
      case "decline":
      case "reject": return "text-red-500";
      case "refer": return "text-amber-500";
      default: return "text-ds-primary";
    }
  };

  if (isLoading) {
    return (
      <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-8 flex justify-center items-center">
        <span className="material-symbols-outlined text-[32px] animate-spin text-ds-primary">progress_activity</span>
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(runs.length / itemsPerPage));
  const paginatedRuns = runs.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  return (
    <div className="space-y-6">
      {!decisionData && (
        <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-6">
          <h3 className="text-lg font-semibold leading-6 mb-4">Application History</h3>
          
          {error && (
            <p className="text-red-500 mb-4">{error}</p>
          )}

          {runs.length === 0 ? (
            <p className="text-on-surface-variant text-sm">No runs found in database. Go to Dashboard to upload one.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-outline-variant">
                    <th className="py-3 px-4 text-xs font-mono text-on-surface-variant font-medium">Processing ID</th>
                    <th className="py-3 px-4 text-xs font-mono text-on-surface-variant font-medium">Date</th>
                    <th className="py-3 px-4 text-xs font-mono text-on-surface-variant font-medium">Applicant</th>
                    <th className="py-3 px-4 text-xs font-mono text-on-surface-variant font-medium">Loan Decision</th>
                    <th className="py-3 px-4 text-xs font-mono text-on-surface-variant font-medium">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedRuns.map((r) => (
                    <tr key={r.run_id} className="border-b border-outline-variant last:border-0 hover:bg-surface-container-low transition-colors">
                      <td className="py-3 px-4 text-sm font-medium">{r.application_id}</td>
                      <td className="py-3 px-4 text-sm text-on-surface-variant">{new Date(r.created_at).toLocaleString()}</td>
                      <td className="py-3 px-4 text-sm font-medium">{r.applicant_name || "-"}</td>
                      <td className="py-3 px-4">
                        {r.status === "failed" || r.error ? (
                          <span className="text-red-500 text-xs font-semibold">Failed</span>
                        ) : r.status !== "completed" ? (
                          <span className="text-blue-500 text-xs font-semibold">Processing...</span>
                        ) : r.decision ? (
                          <span className={`text-xs font-semibold ${getDecisionColor(r.decision)}`}>
                            {getDecisionLabel(r.decision)}
                          </span>
                        ) : (
                          <span className="text-gray-500 text-xs font-semibold">Unknown</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        {r.status === "failed" || r.error ? (
                          <Button 
                            variant="outline"
                            size="sm"
                            onClick={() => router.push("/")}
                            className="text-xs py-1 h-auto bg-surface-container-high"
                          >
                            Retry
                          </Button>
                        ) : (
                          <Button 
                            variant="outline"
                            size="sm"
                            disabled={r.status !== "completed"}
                            onClick={() => { setSelectedRunId(r.run_id); handleViewRun(r.run_id); }}
                            className="text-xs py-1 h-auto bg-surface-container-high"
                          >
                            View Result
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination Controls */}
          {runs.length > 0 && totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 border-t border-outline-variant pt-4 px-2">
              <p className="text-xs text-on-surface-variant">
                Showing {(currentPage - 1) * itemsPerPage + 1} to {Math.min(currentPage * itemsPerPage, runs.length)} of {runs.length} entries
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="text-xs"
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={currentPage === totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  className="text-xs"
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Decision View */}
      {decisionData && (
        <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-6 animate-in fade-in zoom-in-95 duration-500">
          <div className="mb-6 flex gap-4 items-center border-b border-outline-variant pb-4">
             <Button variant="outline" onClick={() => setDecisionData(null)} className="h-8 px-3 text-xs">
                <span className="material-symbols-outlined text-[16px] mr-1">arrow_back</span>
                Back
             </Button>
             <h3 className="text-lg font-semibold leading-6 flex-1">Recommendation ({decisionData.application_id})</h3>
             <span className={`text-xs font-mono font-medium px-3 py-1 rounded-full flex items-center gap-1 tracking-[0.02em] ${
                decisionData.decision.toLowerCase() === "approve" ? "bg-emerald-100 text-emerald-800" :
                (decisionData.decision.toLowerCase() === "decline" || decisionData.decision.toLowerCase() === "reject") ? "bg-red-100 text-red-800" :
                decisionData.decision.toLowerCase() === "refer" ? "bg-amber-100 text-amber-800" :
                "bg-ds-secondary-container text-on-ds-secondary-container"
             }`}>
              <span className="material-symbols-outlined text-[14px]" style={{ fontVariationSettings: "'FILL' 1" }}>
                {decisionData.decision.toLowerCase() === "approve" ? "check_circle" : decisionData.decision.toLowerCase() === "decline" ? "cancel" : "info"}
              </span>
              Decision: {getDecisionLabel(decisionData.decision)}
             </span>
          </div>

          {/* Applicant Profile */}
          {selectedRunId && <ApplicantProfileCard runId={selectedRunId} />}

          {/* Salary Credits */}
          {selectedRunId && <SalaryCreditsTable runId={selectedRunId} />}

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 gap-5 mb-6">
            <div className="p-2 bg-surface-container-low rounded border border-outline-variant">
              <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-1 uppercase tracking-wider leading-[14px]">Credit Score</p>
              <p className={`text-[32px] leading-[40px] font-bold tracking-[-0.02em] ${getDecisionColor(decisionData.decision)}`}>
                {decisionData.credit_bureau.credit_score}
              </p>
            </div>
            <div className="p-2 bg-surface-container-low rounded border border-outline-variant">
              <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-1 uppercase tracking-wider leading-[14px]">FOIR</p>
              <p className="text-[32px] leading-[40px] font-bold tracking-[-0.02em] text-ds-primary">
                {decisionData.metrics.foir_pct.toFixed(1)}%
              </p>
            </div>
          </div>

          {/* Rationale */}
          <div className="mb-4 p-3 bg-surface-container-low rounded border border-outline-variant">
            <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-2 uppercase tracking-wider leading-[14px]">AI Rationale</p>
            <p className="text-[13px] leading-[20px] text-on-surface">{decisionData.rationale_text}</p>
            {decisionData.advisory_notes.length > 0 && (
              <div className="mt-3 pt-2 border-t border-outline-variant">
                <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-1 uppercase tracking-wider leading-[14px]">Advisory Notes</p>
                <ul className="space-y-1">
                  {decisionData.advisory_notes.map((note, i) => (
                    <li key={i} className="text-[12px] text-on-surface-variant flex items-start gap-1.5">
                      <span className="material-symbols-outlined text-[12px] mt-0.5 text-ds-primary">arrow_right</span>
                      {note}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Download Buttons */}
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => selectedRunId && window.open(getMemoUrl(selectedRunId), "_blank")}
              className="flex-1 bg-surface-container text-on-surface text-xs font-mono font-medium py-2 rounded flex items-center justify-center gap-2 hover:bg-surface-dim transition-colors border-outline-variant"
            >
              <span className="material-symbols-outlined text-[18px]">download</span>
              Underwriting Memo (PDF)
            </Button>
            <Button
              variant="outline"
              onClick={() => selectedRunId && window.open(getCashflowUrl(selectedRunId), "_blank")}
              className="flex-1 bg-surface-container text-on-surface text-xs font-mono font-medium py-2 rounded flex items-center justify-center gap-2 hover:bg-surface-dim transition-colors border-outline-variant"
            >
              <span className="material-symbols-outlined text-[18px]">table</span>
              Cash-Flow Summary (XLSX)
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
