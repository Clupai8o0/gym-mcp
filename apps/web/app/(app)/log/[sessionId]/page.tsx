import { cache } from "react";
import { notFound } from "next/navigation";
import type { Metadata } from "next";

import { SessionLogger } from "@/components/log";
import { getMe, getSession } from "@/lib/api";
import type { UnitPref } from "@/lib/types";

// One fetch shared by generateMetadata + the page (React per-request dedupe).
const loadSession = cache((id: string) => getSession(id));

export async function generateMetadata({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}): Promise<Metadata> {
  const { sessionId } = await params;
  const session = await loadSession(sessionId);
  return { title: session?.title ?? "Workout" };
}

export default async function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  const session = await loadSession(sessionId);
  if (!session) notFound();

  const me = await getMe();
  const unitPref: UnitPref = me?.unit_pref === "lb" ? "lb" : "kg";

  return <SessionLogger session={session} unitPref={unitPref} />;
}
