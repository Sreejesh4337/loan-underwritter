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

      {/* Search Bar */}
      <div className="flex-1 max-w-md mx-6 hidden md:block">
        <div className="relative">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">
            search
          </span>
          <Input
            type="text"
            placeholder="Search applications, ID..."
            className="w-full bg-surface-container-low border-outline-variant rounded pl-10 pr-4 py-1.5 text-[13px] leading-[18px] focus:border-emerald-accent focus:ring-1 focus:ring-emerald-accent"
          />
        </div>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="text-on-surface-variant hover:bg-surface-container-low rounded-full"
        >
          <span className="material-symbols-outlined">notifications</span>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="text-on-surface-variant hover:bg-surface-container-low rounded-full"
        >
          <span className="material-symbols-outlined">settings</span>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="text-on-surface-variant hover:bg-surface-container-low rounded-full"
        >
          <span className="material-symbols-outlined">help</span>
        </Button>

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
