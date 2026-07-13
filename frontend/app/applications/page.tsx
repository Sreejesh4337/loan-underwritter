"use client";

import { SideNav } from "@/components/layout/side-nav";
import { TopNav } from "@/components/layout/top-nav";
import { ApplicationsHistory } from "@/components/dashboard/applications-history";

export default function ApplicationsPage() {
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
          <div className="space-y-4">
            <ApplicationsHistory />
          </div>
        </div>
      </main>
    </>
  );
}
