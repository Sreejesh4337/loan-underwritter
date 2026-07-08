"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navLinks = [
  { icon: "dashboard", label: "Dashboard", href: "/" },
  { icon: "description", label: "Applications", href: "/applications" },
];

export function SideNav() {
  const pathname = usePathname();

  return (
    <nav className="hidden md:flex flex-col h-full w-[260px] p-4 space-y-1 fixed left-0 top-0 z-50 bg-surface-container-low border-r border-outline-variant">
      {/* Header */}
      <div className="flex items-center gap-2 mb-6 px-2">
        <div className="w-8 h-8 rounded-full bg-ds-primary flex items-center justify-center text-on-ds-primary">
          <span className="material-symbols-outlined text-[18px]">
            corporate_fare
          </span>
        </div>
        <div>
          <h1 className="text-lg font-black text-on-surface leading-tight">
            AI Underwriter
          </h1>
          <p className="text-[10px] font-mono font-medium text-on-surface-variant leading-[14px]">
            Loan Analysis System
          </p>
        </div>
      </div>

      {/* Navigation Links */}
      <div className="flex-1 space-y-0.5">
        {navLinks.map((link) => {
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.label}
              href={link.href}
              className={`flex items-center gap-2 px-2 py-2 rounded-lg transition-all duration-150 ${
                isActive
                  ? "bg-ds-secondary-container text-on-ds-secondary-container font-bold scale-[0.98]"
                  : "text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              <span
                className="material-symbols-outlined"
                style={
                  isActive
                    ? { fontVariationSettings: "'FILL' 1" }
                    : undefined
                }
              >
                {link.icon}
              </span>
              <span className="text-xs font-mono font-medium tracking-[0.02em]">
                {link.label}
              </span>
            </Link>
          );
        })}
      </div>

    </nav>
  );
}
