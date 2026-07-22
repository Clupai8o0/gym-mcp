import Link from "next/link";
import type { Metadata } from "next";

import { SessionStarter, SessionSummaryCard } from "@/components/log";
import { Card } from "@/components/ui";
import { listSessions } from "@/lib/api";
import { formatTime, isToday } from "@/lib/format";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Log",
  description: "Start a workout and log your sets — fast, one-handed, offline-ready.",
};

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

export default async function LogPage({ searchParams }: { searchParams: Promise<RawParams> }) {
  const params = await searchParams;
  const exerciseSlug = one(params.exercise) || undefined;

  const { items } = await listSessions(20);
  const active = items.find((session) => isToday(session.performed_at));
  const recent = items.filter((session) => session.id !== active?.id);
  const continueHref = active
    ? `/log/${active.id}${exerciseSlug ? `?add=${encodeURIComponent(exerciseSlug)}` : ""}`
    : null;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <p className="eyebrow">Log a workout</p>
        <h1 className={styles.title}>{active ? "Today’s workout" : "Start training"}</h1>
        <p className={styles.lede}>
          {active
            ? "Pick up where you left off, or start a fresh session."
            : "Start a session, add your movements, and log sets as you go. Personal records celebrate themselves."}
        </p>
      </header>

      {active && continueHref ? (
        <div className={styles.activeArea}>
          <Link href={continueHref} className={styles.continueLink}>
            <Card interactive padded className={styles.continue}>
              <div>
                <p className="eyebrow">In progress</p>
                <p className={styles.continueTitle}>{active.title ?? "Workout"}</p>
                <p className={styles.continueSub}>Started {formatTime(active.performed_at)}</p>
              </div>
              <span className={styles.continueCta} aria-hidden>
                Continue →
              </span>
            </Card>
          </Link>
          <SessionStarter exerciseSlug={exerciseSlug} compact />
        </div>
      ) : (
        <Card padded className={styles.starterCard}>
          <SessionStarter exerciseSlug={exerciseSlug} />
        </Card>
      )}

      {recent.length > 0 && (
        <section className={styles.recent} aria-labelledby="recent-heading">
          <h2 id="recent-heading" className={styles.recentHeading}>
            Recent workouts
          </h2>
          <div className={styles.recentList}>
            {recent.map((session) => (
              <SessionSummaryCard key={session.id} session={session} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
