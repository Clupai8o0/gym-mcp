import Link from "next/link";
import type { Metadata } from "next";

import { SessionStarter, SessionSummaryCard } from "@/components/log";
import { Card, LocalTime } from "@/components/ui";
import { getActiveSession, listSessions } from "@/lib/api";
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

  // "In progress" comes from the server's lifecycle flag (`ended_at IS NULL`), never from a
  // date comparison — that used to evaluate in the server's timezone (Phase 11A).
  const [{ items }, active] = await Promise.all([listSessions(20), getActiveSession()]);
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
                <p className={styles.continueSub}>
                  Started <LocalTime iso={active.performed_at} format="time" />
                </p>
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
