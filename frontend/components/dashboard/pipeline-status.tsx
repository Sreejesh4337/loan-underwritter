"use client";

import type { PipelineState } from "./application-analysis";

interface PipelineStatusProps {
  analysisState: PipelineState;
  decisionState: PipelineState;
}

interface StepConfig {
  label: string;
  sublabel: string;
  state: "completed" | "active" | "pending";
}

export function PipelineStatus({
  analysisState,
  decisionState,
}: PipelineStatusProps) {
  const getSteps = (): StepConfig[] => {
    const steps: StepConfig[] = [
      {
        label: "Intake",
        sublabel: "Received via API",
        state: "completed",
      },
      {
        label:
          analysisState === "complete"
            ? "Analysis Complete"
            : analysisState === "analyzing"
              ? "Analyzing..."
              : "Analysis Pending",
        sublabel:
          analysisState === "complete"
            ? "Models executed"
            : "Awaiting document upload",
        state:
          analysisState === "complete"
            ? "completed"
            : analysisState === "analyzing"
              ? "active"
              : "active",
      },
      {
        label: decisionState === "complete" ? "Approved" : "Decision",
        sublabel:
          decisionState === "complete"
            ? "Final recommendation"
            : "Pending model output",
        state: decisionState === "complete" ? "completed" : "pending",
      },
    ];
    return steps;
  };

  const steps = getSteps();

  return (
    <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-4">
      <h4 className="text-xs font-mono font-bold mb-4 uppercase tracking-wider text-on-surface-variant">
        Pipeline Status
      </h4>

      <div className="relative pl-6 space-y-6 before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-[2px] before:bg-outline-variant">
        {steps.map((step, i) => (
          <div
            key={i}
            className={`relative ${
              step.state === "active"
                ? "step-active"
                : step.state === "pending"
                  ? "opacity-50"
                  : ""
            }`}
          >
            {/* Step indicator */}
            {step.state === "completed" ? (
              <div className="absolute -left-6 top-0.5 w-[14px] h-[14px] rounded-full bg-emerald-accent border-2 border-surface-container-lowest flex items-center justify-center z-10">
                <span
                  className="material-symbols-outlined text-[10px] text-white"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  check
                </span>
              </div>
            ) : step.state === "active" ? (
              <div className="ring-indicator absolute -left-6 top-0.5 w-[14px] h-[14px] rounded-full bg-slate-dark border-2 border-surface-container-lowest z-10" />
            ) : (
              <div className="absolute -left-6 top-0.5 w-[14px] h-[14px] rounded-full bg-surface-container-high border-2 border-surface-container-lowest z-10" />
            )}

            <p
              className={`text-xs font-mono font-bold tracking-[0.02em] ${
                step.state === "completed" && i === steps.length - 1
                  ? "text-emerald-accent"
                  : step.state === "active"
                    ? "text-ds-primary"
                    : "text-on-surface"
              }`}
            >
              {step.label}
            </p>
            <p className="text-[10px] font-mono font-medium text-on-surface-variant leading-[14px]">
              {step.sublabel}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
