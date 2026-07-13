"use client";

import { useEffect, useState } from "react";
import { getSalaryCredits, type SalaryCreditResponse } from "@/lib/api";

export function SalaryCreditsTable({ runId }: { runId: string }) {
  const [credits, setCredits] = useState<SalaryCreditResponse[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSalaryCredits(runId)
      .then((c) => !cancelled && setCredits(c))
      .catch(() => !cancelled && setCredits([]));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (!credits || credits.length === 0) return null;

  return (
    <div className="mb-4 p-3 bg-surface-container-low rounded border border-outline-variant">
      <p className="text-[10px] font-mono font-medium text-on-surface-variant mb-2 uppercase tracking-wider leading-[14px]">
        Salary Credits
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-on-surface-variant text-left">
              <th className="font-mono uppercase tracking-wider text-[9px] pb-1 pr-3">Date</th>
              <th className="font-mono uppercase tracking-wider text-[9px] pb-1 pr-3">Description</th>
              <th className="font-mono uppercase tracking-wider text-[9px] pb-1 pr-3 text-right">Credit</th>
              <th className="font-mono uppercase tracking-wider text-[9px] pb-1 text-right">Balance</th>
            </tr>
          </thead>
          <tbody>
            {credits.map((c, i) => (
              <tr key={`${c.txn_date}-${i}`} className="border-t border-outline-variant">
                <td className="py-1 pr-3">{c.txn_date}</td>
                <td className="py-1 pr-3 text-on-surface-variant">{c.description}</td>
                <td className="py-1 pr-3 text-right font-medium">
                  {c.credit_amount != null ? `₹${c.credit_amount.toLocaleString()}` : "—"}
                </td>
                <td className="py-1 text-right text-on-surface-variant">
                  {c.balance != null ? `₹${c.balance.toLocaleString()}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
