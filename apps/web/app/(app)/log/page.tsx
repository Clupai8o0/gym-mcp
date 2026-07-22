import type { Metadata } from "next";

import { EmptyState } from "@/components/ui";

export const metadata: Metadata = { title: "Log" };

/** Placeholder until the Log slice (Phase 7) lands — keeps the shell navigable, no dead links. */
export default function LogPage() {
  return (
    <EmptyState
      title="Workout logging is coming next"
      description="Fast set entry, PR celebrations, and offline-first logging arrive in the next slice. For now, browse the library and pick your movements."
    />
  );
}
