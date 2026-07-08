"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function TopNav() {
  return (
    <header className="flex justify-between items-center w-full px-6 h-16 sticky top-0 z-40 bg-surface border-b border-outline-variant">
      <div className="flex items-center gap-4">
        <h2 className="text-2xl font-semibold font-sans tracking-[-0.01em] text-ds-primary">
          Underwriter AI
        </h2>
      </div>



      {/* Right Actions */}
      <div className="flex items-center gap-2">


        {/* Avatar */}
        <div className="w-8 h-8 rounded-full bg-surface-container-high ml-2 flex items-center justify-center border border-outline-variant text-on-surface-variant">
          <span className="material-symbols-outlined text-[20px]">
            person
          </span>
        </div>

        <Button 
          onClick={() => window.location.reload()}
          className="ml-4 bg-slate-dark text-white text-xs font-mono font-medium px-4 py-1.5 rounded hover:opacity-90 transition-opacity"
        >
          New Application
        </Button>
      </div>
    </header>
  );
}
