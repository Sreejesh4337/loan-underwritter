"use client";

import { SideNav } from "@/components/layout/side-nav";
import { TopNav } from "@/components/layout/top-nav";
import { ApplicationAnalysis } from "@/components/dashboard/application-analysis";

export default function DashboardPage() {
  return (
    <>
      {/* Sidebar */}
      <SideNav />

      {/* Main Content Area */}
      <main className="flex-1 md:ml-[260px] min-h-screen flex flex-col">
        {/* Top Navigation */}
        <TopNav />

        {/* Canvas */}
        <div className="flex-1 p-6 max-w-[1440px] mx-auto w-full">
          {/* Main Stage: Application Analysis */}
          <div className="space-y-4">
            <ApplicationAnalysis />
          </div>
        </div>
      </main>
    </>
  );
}

