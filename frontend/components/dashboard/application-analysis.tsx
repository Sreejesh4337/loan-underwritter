"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import {
  uploadAndRun,
  getRunStatus,
  getDecision,
  getMemoUrl,
  getCashflowUrl,
  DocumentValidationError,
  type DecisionResponse,
  type RunStatusResponse,
} from "@/lib/api";

type UploadId = "bank" | "kyc" | "income";

interface UploadZone {
  id: UploadId;
  icon: string;
  title: string;
  description: string;
}

const uploadZones: UploadZone[] = [
  {
    id: "bank",
    icon: "account_balance",
    title: "Bank Statement",
    description: "PDF format (Max 5MB)",
  },
  {
    id: "kyc",
    icon: "verified_user",
    title: "KYC & Credit",
    description: "PDF format (Max 10MB)",
  },
  {
    id: "income",
    icon: "table_chart",
    title: "Income Sheet",
    description: "XLSX, XLS (Max 2MB)",
  },
];

// Map backend pipeline nodes to frontend progress steps
const PIPELINE_STEP_MAP: Record<string, number> = {
  plan: 0,
  parse_documents: 0,
  extract_kyc: 1,
  extract_income: 1,
  extract_bank_statement: 1,
  merge_and_cross_check: 1,
  compute_metrics: 2,
  evaluate_policy: 2,
  decide: 3,
  generate_outputs: 3,
  done: 3,
};

// Maps the backend's multipart form field names to this component's upload slots.
const API_FIELD_TO_UPLOAD_ID: Record<string, UploadId> = {
  bank_statement: "bank",
  kyc_and_credit: "kyc",
  income_details: "income",
};

const sseSteps = [
  "Reading documents & extracting data",
  "Pulling live credit bureau data",
  "Running risk models & simulations",
  "Generating final decision matrix",
];

export type AnalysisStep = "upload" | "processing" | "result" | "error";
export type PipelineState = "pending" | "active" | "analyzing" | "complete";

interface ApplicationAnalysisProps {
  onStepChange?: (step: AnalysisStep) => void;
  onPipelineChange?: (state: {
    analysis: PipelineState;
    decision: PipelineState;
  }) => void;
}

export function ApplicationAnalysis({
  onStepChange,
  onPipelineChange,
}: ApplicationAnalysisProps) {
  const [currentStep, setCurrentStep] = useState<AnalysisStep>("upload");
  const [isTransitioning, setIsTransitioning] = useState(false);

  // Store actual File objects for upload
  const [uploadedFiles, setUploadedFiles] = useState<
    Record<UploadId, File | null>
  >({
    bank: null,
    kyc: null,
    income: null,
  });

  // API state
  const [runId, setRunId] = useState<string | null>(null);
  const [currentSseStepIndex, setCurrentSseStepIndex] = useState(-1);
  const [decisionData, setDecisionData] = useState<DecisionResponse | null>(
    null
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<
    Partial<Record<UploadId, string>>
  >({});

  // Polling ref
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const allUploaded = Object.values(uploadedFiles).every(
    (file) => file !== null
  );

  const handleUpload = useCallback((id: UploadId, file: File) => {
    setUploadedFiles((prev) => ({
      ...prev,
      [id]: file,
    }));
    setFieldErrors((prev) => ({
      ...prev,
      [id]: undefined,
    }));
  }, []);

  // Derive progress step index from run status
  const deriveStepIndex = useCallback((runStatus: RunStatusResponse): number => {
    const stepStatus = runStatus.step_status || {};

    // Find the highest step that is running or done
    let highestStep = -1;
    for (const [nodeName, status] of Object.entries(stepStatus)) {
      if (
        status.status === "running" ||
        status.status === "done"
      ) {
        const mappedIndex = PIPELINE_STEP_MAP[nodeName];
        if (mappedIndex !== undefined && mappedIndex > highestStep) {
          highestStep = mappedIndex;
        }
      }
    }
    return highestStep;
  }, []);

  // Start polling for run status
  const startPolling = useCallback(
    (runIdToWatch: string) => {
      // Clear any existing poll
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }

      pollingRef.current = setInterval(async () => {
        try {
          const status = await getRunStatus(runIdToWatch);

          // Update progress step
          const stepIdx = deriveStepIndex(status);
          if (stepIdx >= 0) {
            setCurrentSseStepIndex(stepIdx);
          }

          // Check if completed
          if (status.status === "completed") {
            if (pollingRef.current) clearInterval(pollingRef.current);

            // Fetch the decision data
            try {
              const decision = await getDecision(runIdToWatch);
              setDecisionData(decision);
              setCurrentStep("result");
              onStepChange?.("result");
              onPipelineChange?.({
                analysis: "complete",
                decision: "complete",
              });
            } catch {
              setErrorMessage("Pipeline completed but failed to fetch results.");
              setCurrentStep("error");
            }
          }

          // Check if failed
          if (
            status.status === "failed" ||
            status.status === "failed_input"
          ) {
            if (pollingRef.current) clearInterval(pollingRef.current);
            setErrorMessage(
              status.error || "Pipeline failed. Check your uploaded documents."
            );
            setCurrentStep("error");
          }
        } catch {
          // Network error — keep trying
        }
      }, 1500);
    },
    [deriveStepIndex, onStepChange, onPipelineChange]
  );

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  const handleRunAnalyst = useCallback(async () => {
    if (
      !uploadedFiles.bank ||
      !uploadedFiles.kyc ||
      !uploadedFiles.income
    )
      return;

    setIsTransitioning(true);

    setTimeout(async () => {
      setIsTransitioning(false);
      setCurrentStep("processing");
      onStepChange?.("processing");
      onPipelineChange?.({ analysis: "analyzing", decision: "pending" });
      setCurrentSseStepIndex(0);

      try {
        const response = await uploadAndRun({
          bank: uploadedFiles.bank!,
          kyc: uploadedFiles.kyc!,
          income: uploadedFiles.income!,
        });

        setRunId(response.run_id);
        startPolling(response.run_id);
      } catch (err) {
        if (err instanceof DocumentValidationError) {
          const mapped: Partial<Record<UploadId, string>> = {};
          const cleared: Partial<Record<UploadId, File | null>> = {};
          for (const [field, message] of Object.entries(err.fieldErrors)) {
            const uploadId = API_FIELD_TO_UPLOAD_ID[field];
            if (uploadId) {
              mapped[uploadId] = message;
              cleared[uploadId] = null;
            }
          }
          setFieldErrors(mapped);
          setUploadedFiles((prev) => ({ ...prev, ...cleared }));
          setCurrentStep("upload");
          onStepChange?.("upload");
          onPipelineChange?.({ analysis: "pending", decision: "pending" });
        } else {
          setErrorMessage(
            err instanceof Error ? err.message : "Upload failed"
          );
          setCurrentStep("error");
        }
      }
    }, 400);
  }, [uploadedFiles, onStepChange, onPipelineChange, startPolling]);

  useEffect(() => {
    onStepChange?.(currentStep);
  }, [currentStep, onStepChange]);

  // Helper to format decision label
  const getDecisionLabel = (decision: string) => {
    switch (decision.toLowerCase()) {
      case "approve":
        return "Approved";
      case "decline":
        return "Declined";
      case "refer":
        return "Referred";
      default:
        return decision;
    }
  };

  const getDecisionColor = (decision: string) => {
    switch (decision.toLowerCase()) {
      case "approve":
        return "text-emerald-accent";
      case "decline":
        return "text-red-500";
      case "refer":
        return "text-amber-500";
      default:
        return "text-ds-primary";
    }
  };

  return (
    <>
      {/* Card: New Application Analysis */}
      {(currentStep === "upload" || currentStep === "processing") && (
        <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-4 transition-all duration-500 overflow-hidden">
          <div className="mb-4 border-b border-outline-variant pb-2">
            <h3 className="text-lg font-semibold leading-6">
              New Application Analysis
            </h3>
            <p className="text-[13px] leading-[18px] text-on-surface-variant">
              Upload required documentation to initiate risk assessment pipeline.
            </p>
          </div>

          {/* Step 1: Uploads */}
          {currentStep === "upload" && (
            <div
              className={`space-y-4 transition-all duration-400 ease-in-out ${
                isTransitioning
                  ? "opacity-0 translate-y-4 scale-[0.98]"
                  : "opacity-100 translate-y-0 scale-100"
              }`}
            >
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {uploadZones.map((zone) => {
                  const uploadedFile = uploadedFiles[zone.id];
                  const isUploaded = uploadedFile !== null;
                  const zoneError = fieldErrors[zone.id];
                  return (
                    <label
                      key={zone.id}
                      className={`upload-zone border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
                        zoneError
                          ? "border-red-400 bg-red-50"
                          : isUploaded
                            ? "border-emerald-accent bg-surface-bright"
                            : "border-outline-variant hover:bg-surface-container-low"
                      }`}
                    >
                      <input
                        type="file"
                        className="hidden"
                        accept={
                          zone.id === "income" ? ".xlsx,.xls" : ".pdf"
                        }
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            handleUpload(zone.id, file);
                          }
                        }}
                      />
                      <span
                        className={`material-symbols-outlined text-[32px] mb-2 block ${
                          zoneError ? "text-red-500" : "text-ds-primary"
                        }`}
                      >
                        {zoneError ? "error" : isUploaded ? "check_circle" : zone.icon}
                      </span>
                      <h4 className="text-xs font-mono font-medium text-ds-primary mb-1 tracking-[0.02em]">
                        {zone.title}
                      </h4>
                      {zoneError ? (
                        <p className="text-[10px] font-mono font-medium text-red-600 leading-[14px] px-2">
                          {zoneError}
                        </p>
                      ) : (
                        <p className="text-[10px] font-mono font-medium text-on-surface-variant leading-[14px] truncate px-2">
                          {isUploaded ? uploadedFile.name : zone.description}
                        </p>
                      )}
                      {isUploaded && !zoneError && (
                        <div className="w-full h-1 bg-emerald-accent mt-2 rounded-full opacity-50" />
                      )}
                    </label>
                  );
                })}
              </div>
              <div className="flex justify-end pt-4">
                <Button
                  onClick={handleRunAnalyst}
                  disabled={!allUploaded}
                  className={`text-xs font-mono font-medium px-6 py-2 rounded transition-colors ${
                    allUploaded
                      ? "bg-slate-dark text-white cursor-pointer hover:opacity-90"
                      : "bg-surface-container-high text-on-surface-variant cursor-not-allowed"
                  }`}
                >
                  Run Analyst
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: Processing (Real-time Pipeline Tracker) */}
          {currentStep === "processing" && (
            <div className="py-8 px-4 animate-in fade-in slide-in-from-bottom-4 duration-700">
              <div className="max-w-lg mx-auto space-y-8">
                {/* Header */}
                <div className="flex items-center gap-4 border-b border-outline-variant pb-4">
                  <span className="material-symbols-outlined text-[28px] text-slate-dark animate-spin">
                    progress_activity
                  </span>
                  <div>
                    <h4 className="text-lg font-semibold leading-6">
                      Agent Analysis in Progress...
                    </h4>
                    <p className="text-[13px] text-on-surface-variant">
                      Streaming updates from reasoning engine
                    </p>
                  </div>
                </div>

                {/* Vertical Stepper */}
                <div className="space-y-6 relative before:absolute before:inset-0 before:ml-[11px] before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-outline-variant before:to-transparent pl-8 md:pl-0">
                  {sseSteps.map((stepText, index) => {
                    const isComplete = index < currentSseStepIndex;
                    const isActive = index === currentSseStepIndex;
                    const isPending = index > currentSseStepIndex;

                    return (
                      <div
                        key={index}
                        className={`relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group transition-all duration-500 ${
                          isPending
                            ? "opacity-40 grayscale"
                            : "opacity-100 grayscale-0"
                        }`}
                      >
                        {/* Node Symbol */}
                        <div
                          className={`flex items-center justify-center w-6 h-6 rounded-full border-2 shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-sm ${
                            isComplete
                              ? "bg-emerald-accent border-emerald-accent text-white"
                              : isActive
                                ? "bg-ds-primary border-ds-primary text-white"
                                : "bg-surface border-outline-variant text-transparent"
                          }`}
                        >
                          {isComplete && (
                            <span className="material-symbols-outlined text-[14px] font-bold">
                              check
                            </span>
                          )}
                          {isActive && (
                            <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
                          )}
                        </div>

                        {/* Content Box */}
                        <div className="w-[calc(100%-2.5rem)] md:w-[calc(50%-1.5rem)] bg-surface-container-lowest p-3 rounded-md border border-outline-variant shadow-sm transition-transform duration-300 hover:-translate-y-0.5">
                          <p
                            className={`text-[13px] font-mono font-medium ${isActive ? "text-ds-primary" : "text-on-surface"}`}
                          >
                            {stepText}
                          </p>
                          {isActive && (
                            <p className="text-[10px] font-mono text-on-surface-variant mt-1.5 animate-pulse flex items-center gap-1">
                              <span
                                className="w-1 h-1 bg-ds-primary rounded-full animate-bounce"
                                style={{ animationDelay: "0ms" }}
                              />
                              <span
                                className="w-1 h-1 bg-ds-primary rounded-full animate-bounce"
                                style={{ animationDelay: "150ms" }}
                              />
                              <span
                                className="w-1 h-1 bg-ds-primary rounded-full animate-bounce"
                                style={{ animationDelay: "300ms" }}
                              />
                              <span className="ml-1">Processing...</span>
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Error State */}
      {currentStep === "error" && (
        <div className="bg-surface-container-lowest border border-red-300 rounded-lg p-4 animate-in fade-in zoom-in-95 duration-500">
          <div className="flex items-center gap-3 mb-4">
            <span className="material-symbols-outlined text-[28px] text-red-500">
              error
            </span>
            <div>
              <h3 className="text-lg font-semibold leading-6 text-red-600">
                Analysis Failed
              </h3>
              <p className="text-[13px] text-on-surface-variant">
                {errorMessage || "An unexpected error occurred."}
              </p>
            </div>
          </div>
          <Button
            onClick={() => {
              setCurrentStep("upload");
              setUploadedFiles({ bank: null, kyc: null, income: null });
              setRunId(null);
              setErrorMessage(null);
              setCurrentSseStepIndex(-1);
            }}
            className="bg-slate-dark text-white text-xs font-mono font-medium px-6 py-2 rounded hover:opacity-90 transition-opacity"
          >
            Try Again
          </Button>
        </div>
      )}

      {/* Step 3: Recommendation — now with REAL data */}
      {currentStep === "result" && decisionData && (
        <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-4 animate-in fade-in zoom-in-95 duration-500">
          <div className="mb-4 border-b border-outline-variant pb-2 flex justify-between items-center">
            <h3 className="text-lg font-semibold leading-6">Recommendation</h3>
            <span
              className={`bg-ds-secondary-container text-on-ds-secondary-container text-xs font-mono font-medium px-3 py-1 rounded-full flex items-center gap-1 tracking-[0.02em]`}
            >
              <span
                className="material-symbols-outlined text-[14px]"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                {decisionData.decision.toLowerCase() === "approve"
                  ? "check_circle"
                  : decisionData.decision.toLowerCase() === "decline"
                    ? "cancel"
                    : "info"}
              </span>
              Decision: {getDecisionLabel(decisionData.decision)}
            </span>
          </div>

          {/* Applicant Info */}
          <div className="mb-4 p-2 bg-surface-container-low rounded border border-outline-variant">
            <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-1 uppercase tracking-wider leading-[14px]">
              Applicant
            </p>
            <p className="text-sm font-semibold">
              {decisionData.applicant.full_name}
            </p>
            <p className="text-[11px] text-on-surface-variant capitalize">
              {decisionData.applicant.employment_type.replace("_", " ")}
            </p>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 gap-5 mb-6">
            <div className="p-2 bg-surface-container-low rounded border border-outline-variant">
              <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-1 uppercase tracking-wider leading-[14px]">
                Credit Score
              </p>
              <p
                className={`text-[32px] leading-[40px] font-bold tracking-[-0.02em] ${getDecisionColor(decisionData.decision)}`}
              >
                {decisionData.credit_bureau.credit_score}
              </p>
            </div>
            <div className="p-2 bg-surface-container-low rounded border border-outline-variant">
              <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-1 uppercase tracking-wider leading-[14px]">
                FOIR
              </p>
              <p className="text-[32px] leading-[40px] font-bold tracking-[-0.02em] text-ds-primary">
                {decisionData.metrics.foir_pct.toFixed(1)}%
              </p>
            </div>
          </div>

          {/* Rationale */}
          <div className="mb-4 p-3 bg-surface-container-low rounded border border-outline-variant">
            <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-2 uppercase tracking-wider leading-[14px]">
              AI Rationale
            </p>
            <p className="text-[13px] leading-[20px] text-on-surface">
              {decisionData.rationale_text}
            </p>
            {decisionData.advisory_notes.length > 0 && (
              <div className="mt-3 pt-2 border-t border-outline-variant">
                <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-1 uppercase tracking-wider leading-[14px]">
                  Advisory Notes
                </p>
                <ul className="space-y-1">
                  {decisionData.advisory_notes.map((note, i) => (
                    <li
                      key={i}
                      className="text-[12px] text-on-surface-variant flex items-start gap-1.5"
                    >
                      <span className="material-symbols-outlined text-[12px] mt-0.5 text-ds-primary">
                        arrow_right
                      </span>
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
              onClick={() => runId && window.open(getMemoUrl(runId), "_blank")}
              className="flex-1 bg-surface-container text-on-surface text-xs font-mono font-medium py-2 rounded flex items-center justify-center gap-2 hover:bg-surface-dim transition-colors border-outline-variant"
            >
              <span className="material-symbols-outlined text-[18px]">
                download
              </span>
              Underwriting Memo (PDF)
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                runId && window.open(getCashflowUrl(runId), "_blank")
              }
              className="flex-1 bg-surface-container text-on-surface text-xs font-mono font-medium py-2 rounded flex items-center justify-center gap-2 hover:bg-surface-dim transition-colors border-outline-variant"
            >
              <span className="material-symbols-outlined text-[18px]">
                table
              </span>
              Cash-Flow Summary (XLSX)
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
