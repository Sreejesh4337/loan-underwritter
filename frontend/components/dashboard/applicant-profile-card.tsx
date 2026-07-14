"use client";

import { useEffect, useState } from "react";
import { getApplicantProfile, type ApplicantProfileResponse } from "@/lib/api";

export function ApplicantProfileCard({ runId }: { runId: string }) {
  const [profile, setProfile] = useState<ApplicantProfileResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getApplicantProfile(runId)
      .then((p) => !cancelled && setProfile(p))
      .catch(() => !cancelled && setProfile(null));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (!profile) return null;

  return (
    <div className="mb-4 p-3 bg-surface-container-low rounded border border-outline-variant">
      <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-2 uppercase tracking-wider leading-[14px]">
        Applicant Profile
      </p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        <div>
          <p className="text-sm font-semibold">{profile.full_name}</p>
          <p className="text-[11px] text-on-surface-variant capitalize">
            {profile.employment_type?.replace("_", " ")}
            {profile.employer_or_business ? ` · ${profile.employer_or_business}` : ""}
          </p>
        </div>
        <div className="text-[11px] text-on-surface-variant">
          <p>{[profile.city, profile.state].filter(Boolean).join(", ")}</p>
          <p>{profile.mobile_masked}</p>
          <p>{profile.pan_masked}</p>
        </div>
        <div className="text-[11px] text-on-surface-variant">
          <p className="font-mono uppercase tracking-wider text-[9px] mb-0.5">Loan Request</p>
          <p>
            {profile.product} · ₹{profile.requested_amount?.toLocaleString()} ·{" "}
            {profile.tenor_months}mo @ {profile.indicative_rate_pct}%
          </p>
        </div>
        <div className="text-[11px] text-on-surface-variant">
          <p className="font-mono uppercase tracking-wider text-[9px] mb-0.5">Existing Credit</p>
          <p>
            {profile.active_loans} active loans · {profile.delinquencies_12m} delinquencies (12m)
            · {profile.enquiries_6m} enquiries (6m)
          </p>
        </div>
      </div>
    </div>
  );
}
