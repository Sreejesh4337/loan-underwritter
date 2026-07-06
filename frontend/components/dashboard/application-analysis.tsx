"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";

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

const sseSteps = [
  "Reading documents & extracting data",
  "Pulling live credit bureau data",
  "Running risk models & simulations",
  "Generating final decision matrix",
];

export type AnalysisStep = "upload" | "processing" | "result";
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
  
  // Store file names for each zone
  const [uploadedFiles, setUploadedFiles] = useState<Record<UploadId, string | null>>({
    bank: null,
    kyc: null,
    income: null,
  });
  
  const [currentSseStepIndex, setCurrentSseStepIndex] = useState(-1);

  const allUploaded = Object.values(uploadedFiles).every((file) => file !== null);

  const handleUpload = useCallback((id: UploadId, file: File) => {
    setUploadedFiles((prev) => ({
      ...prev,
      [id]: file.name,
    }));
  }, []);

  const handleRunAnalyst = useCallback(() => {
    setIsTransitioning(true); // Start fade-out animation

    setTimeout(() => {
      setIsTransitioning(false);
      setCurrentStep("processing");
      onStepChange?.("processing");
      onPipelineChange?.({ analysis: "analyzing", decision: "pending" });
      
      setCurrentSseStepIndex(0); // Start first step

      let step = 0;
      const interval = setInterval(() => {
        if (step < sseSteps.length - 1) {
          step++;
          setCurrentSseStepIndex(step);
        } else {
          clearInterval(interval);
          setTimeout(() => {
            setCurrentStep("result");
            onStepChange?.("result");
            onPipelineChange?.({ analysis: "complete", decision: "complete" });
          }, 1500); // Small pause at the end before showing result
        }
      }, 1800); // 1.8s per step for simulation
    }, 400); // 400ms CSS transition duration
  }, [onStepChange, onPipelineChange]);

  useEffect(() => {
    onStepChange?.(currentStep);
  }, [currentStep, onStepChange]);

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
                isTransitioning ? "opacity-0 translate-y-4 scale-[0.98]" : "opacity-100 translate-y-0 scale-100"
              }`}
            >
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {uploadZones.map((zone) => {
                  const uploadedFileName = uploadedFiles[zone.id];
                  const isUploaded = uploadedFileName !== null;
                  return (
                    <label
                      key={zone.id}
                      className={`upload-zone border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
                        isUploaded
                          ? "border-emerald-accent bg-surface-bright"
                          : "border-outline-variant hover:bg-surface-container-low"
                      }`}
                    >
                      <input
                        type="file"
                        className="hidden"
                        accept={zone.id === 'income' ? '.xlsx,.xls' : '.pdf'}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            handleUpload(zone.id, file);
                          }
                        }}
                      />
                      <span className="material-symbols-outlined text-[32px] text-ds-primary mb-2 block">
                        {isUploaded ? "check_circle" : zone.icon}
                      </span>
                      <h4 className="text-xs font-mono font-medium text-ds-primary mb-1 tracking-[0.02em]">
                        {zone.title}
                      </h4>
                      <p className="text-[10px] font-mono font-medium text-on-surface-variant leading-[14px] truncate px-2">
                        {isUploaded ? uploadedFileName : zone.description}
                      </p>
                      {isUploaded && (
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

          {/* Step 2: Processing (SSE Real-time Tracker) */}
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
                          isPending ? 'opacity-40 grayscale' : 'opacity-100 grayscale-0'
                        }`}
                      >
                        {/* Node Symbol */}
                        <div className={`flex items-center justify-center w-6 h-6 rounded-full border-2 shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-sm ${
                          isComplete ? 'bg-emerald-accent border-emerald-accent text-white' : 
                          isActive ? 'bg-ds-primary border-ds-primary text-white' : 
                          'bg-surface border-outline-variant text-transparent'
                        }`}>
                          {isComplete && <span className="material-symbols-outlined text-[14px] font-bold">check</span>}
                          {isActive && <span className="w-2 h-2 rounded-full bg-white animate-pulse" />}
                        </div>
                        
                        {/* Content Box */}
                        <div className="w-[calc(100%-2.5rem)] md:w-[calc(50%-1.5rem)] bg-surface-container-lowest p-3 rounded-md border border-outline-variant shadow-sm transition-transform duration-300 hover:-translate-y-0.5">
                          <p className={`text-[13px] font-mono font-medium ${isActive ? 'text-ds-primary' : 'text-on-surface'}`}>
                            {stepText}
                          </p>
                          {isActive && (
                            <p className="text-[10px] font-mono text-on-surface-variant mt-1.5 animate-pulse flex items-center gap-1">
                              <span className="w-1 h-1 bg-ds-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                              <span className="w-1 h-1 bg-ds-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                              <span className="w-1 h-1 bg-ds-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                              <span className="ml-1">Awaiting chunks...</span>
                            </p>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>

              </div>
            </div>
          )}
        </div>
      )}

      {/* Step 3: Recommendation */}
      {currentStep === "result" && (
        <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-4 animate-in fade-in zoom-in-95 duration-500">
          <div className="mb-4 border-b border-outline-variant pb-2 flex justify-between items-center">
            <h3 className="text-lg font-semibold leading-6">Recommendation</h3>
            <span className="bg-ds-secondary-container text-on-ds-secondary-container text-xs font-mono font-medium px-3 py-1 rounded-full flex items-center gap-1 tracking-[0.02em]">
              <span
                className="material-symbols-outlined text-[14px]"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                check_circle
              </span>
              Decision: Approved
            </span>
          </div>
          <div className="grid grid-cols-2 gap-5 mb-6">
            <div className="p-2 bg-surface-container-low rounded border border-outline-variant">
              <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-1 uppercase tracking-wider leading-[14px]">
                Risk Score
              </p>
              <p className="text-[32px] leading-[40px] font-bold tracking-[-0.02em] text-emerald-accent">
                842
              </p>
            </div>
            <div className="p-2 bg-surface-container-low rounded border border-outline-variant">
              <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-1 uppercase tracking-wider leading-[14px]">
                Est. Default Rate
              </p>
              <p className="text-[32px] leading-[40px] font-bold tracking-[-0.02em] text-ds-primary">
                0.4%
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1 bg-surface-container text-on-surface text-xs font-mono font-medium py-2 rounded flex items-center justify-center gap-2 hover:bg-surface-dim transition-colors border-outline-variant"
            >
              <span className="material-symbols-outlined text-[18px]">
                download
              </span>
              Underwriting Memo (PDF)
            </Button>
            <Button
              variant="outline"
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
