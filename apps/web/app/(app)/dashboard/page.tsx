import type { Metadata } from "next";

import { EmptyState } from "@/components/ui";

export const metadata: Metadata = { title: "Dashboard" };

/** Placeholder until the Dashboard slice (Phase 8) lands — keeps the shell navigable. */
export default function DashboardPage() {
  return (
    <EmptyState
      title="Your progress dashboard is on the way"
      description="Personal records, volume trends, and training frequency land in a later slice. Log a few workouts first and they'll fill in here."
    />
  );
}
