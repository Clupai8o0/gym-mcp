import { Suspense } from "react";
import Link from "next/link";
import type { Metadata } from "next";

import { FrequencyHeatmap } from "@/components/dashboard/FrequencyHeatmap";
import { PrList } from "@/components/dashboard/PrList";
import { RangeControl } from "@/components/dashboard/RangeControl";
import { VolumeChart } from "@/components/dashboard/VolumeChart";
import {
  DayStrip,
  HighlightRow,
  HomeHeader,
  HomeWelcome,
  WeekStats,
  WorkoutCard,
} from "@/components/home";
import { LocalTime, Skeleton } from "@/components/ui";
import {
  getActiveSession,
  getFrequency,
  getSkillsOverview,
  getVolume,
  listExercises,
  listPrs,
  listSessions,
} from "@/lib/api";
import { parked, requireUser } from "@/lib/auth";
import { formatPrValue, prTypeLabel } from "@/lib/format";
import type { DashboardRange } from "@/lib/ranges";
import { DEFAULT_RANGE_KEY, rangeWindow, resolveRange } from "@/lib/ranges";
import type { Pr, SkillOverview, UnitPref } from "@/lib/types";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Home",
  description:
    "Your week at a glance — the workout in progress, this week's training, and your latest records.",
};

const DAY_MS = 86_400_000;
/** The stats window: a rolling seven days, which means the same thing in every timezone (D33). */
const WEEK_MS = 7 * DAY_MS;
/** The strip only needs seven local days; fetch nine so no timezone can clip an edge day. */
const STRIP_MS = 9 * DAY_MS;

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/** The single strongest skill: furthest through its tree, percent breaking ties. */
function topSkill(skills: SkillOverview[]): SkillOverview | null {
  const started = skills.filter((s) => s.current_stage > 0 || s.progress_percent > 0);
  if (started.length === 0) return null;
  const score = (s: SkillOverview) =>
    (s.current_stage + s.progress_percent / 100) / Math.max(1, s.total_stages);
  return started.reduce((best, s) => (score(s) > score(best) ? s : best));
}

function latestPr(prs: Pr[]): Pr | null {
  if (prs.length === 0) return null;
  return prs.reduce((best, pr) => (pr.achieved_at > best.achieved_at ? pr : best));
}

/**
 * The two panels below are `display: none` under 768px, so on the screen size that actually has
 * a latency budget their data is never seen. Fetching them inside a `Suspense` boundary takes
 * them off the blocking path entirely: the phone screen streams as soon as its own reads land,
 * and desktop fills these in a beat later.
 *
 * `listPrs` deliberately stays blocking even though the Records panel is also desktop-only — it
 * feeds "Latest PR" and the week's PR count above the fold, and it has no React `cache()`, so
 * deferring it would issue a *second* request for data the page already needs.
 */
async function VolumePanelBody({ range, unit }: { range: DashboardRange; unit: UnitPref }) {
  const { from, to } = rangeWindow(range);
  const volume = await getVolume(from, to);
  if (volume.items.length === 0) {
    return <p className={styles.empty}>No sets logged in this range yet.</p>;
  }
  return <VolumeChart volume={volume} unit={unit} />;
}

async function FrequencyPanelBody({ weeks }: { weeks: number }) {
  return <FrequencyHeatmap frequency={await getFrequency(weeks)} />;
}

/** Placeholder for a deferred panel — only ever visible ≥768px, where the panels exist. */
function PanelFallback({ height }: { height: string }) {
  return <Skeleton height={height} radius="var(--radius-md)" />;
}

/**
 * Home (Phase 11C). `/dashboard` stopped being "the charts page" and became the app's front door:
 * one phone screen, no scrolling, with the workout above the fold and everything else a one-line
 * summary that links to its own `/progress/*` screen.
 *
 * From 768px up the vertical budget that forced that split doesn't exist, so the progress content
 * renders **inline** in a right-hand column instead — same components, no second set.
 */
export default async function HomePage({ searchParams }: { searchParams: Promise<RawParams> }) {
  const params = await searchParams;
  const range = resolveRange(one(params.range) || DEFAULT_RANGE_KEY);

  const now = new Date();
  const nowIso = now.toISOString();
  const weekFrom = new Date(now.getTime() - WEEK_MS).toISOString();
  const stripFrom = new Date(now.getTime() - STRIP_MS).toISOString();

  // Every read starts here, but the user resolves *first*: on an expired cookie these all throw
  // 401 and only `requireUser` knows to redirect (see `lib/auth.parked`).
  const reads = {
    active: parked(getActiveSession()),
    // The nine-day window feeds both the strip and (filtered to seven) the session count.
    recent: parked(listSessions({ from: stripFrom, limit: 100 })),
    weekVolume: parked(getVolume(weekFrom, nowIso)),
    prs: parked(listPrs()),
    skills: parked(getSkillsOverview()),
  };
  const me = await requireUser("/dashboard");
  const [{ session: active, set_count: setCount }, recent, weekVolume, prs, skills] =
    await Promise.all([reads.active, reads.recent, reads.weekVolume, reads.prs, reads.skills]);

  const unit = me.unit_pref as UnitPref;

  // "Has this account ever logged anything?" — asked only when the answer is still in doubt.
  // Any PR, or any session in the last nine days, settles it without a sixth round trip; only a
  // genuinely bare-looking account pays for the lifetime count.
  const isNewAccount =
    prs.items.length === 0 &&
    recent.items.length === 0 &&
    (await listSessions({ limit: 1 })).total === 0;
  if (isNewAccount) {
    const catalog = await listExercises({ limit: 1 });
    return (
      <div className={styles.welcomePage}>
        <HomeHeader me={me} now={nowIso} />
        <HomeWelcome exerciseCount={catalog.total} />
      </div>
    );
  }

  const weekSessions = recent.items.filter((session) => session.performed_at >= weekFrom);
  const weekSets = weekVolume.items.reduce((total, item) => total + item.total_sets, 0);
  const weekTonnage = weekVolume.items.reduce(
    (total, item) => total + (item.total_tonnage_kg ?? 0),
    0,
  );
  const weekPrs = prs.items.filter((pr) => pr.achieved_at >= weekFrom).length;

  const pr = latestPr(prs.items);
  const skill = topSkill(skills.items);

  return (
    <div className={styles.page}>
      <HomeHeader me={me} now={nowIso} action={<RangeControl current={range.key} />} />

      <div className={styles.workout}>
        <WorkoutCard active={active} setCount={setCount} />
      </div>

      <div className={styles.stats}>
        <WeekStats
          sessions={weekSessions.length}
          tonnageKg={weekTonnage}
          sets={weekSets}
          prs={weekPrs}
          unit={unit}
        />
      </div>

      <div className={styles.strip}>
        <DayStrip sessionDates={recent.items.map((session) => session.performed_at)} now={nowIso} />
      </div>

      <div className={styles.highlights}>
        {pr ? (
          <HighlightRow
            eyebrow="Latest PR"
            title={pr.exercise_name}
            value={formatPrValue(pr.value, pr.unit === "kg" ? unit : pr.unit)}
            meta={
              <>
                {prTypeLabel(pr.pr_type)} · <LocalTime iso={pr.achieved_at} format="relative" />
              </>
            }
            href="/progress/records"
          />
        ) : (
          <HighlightRow
            eyebrow="Latest PR"
            title="No records yet"
            value="—"
            href="/progress/records"
          />
        )}

        {skill ? (
          <HighlightRow
            eyebrow="Top skill"
            title={skill.name}
            value={`${skill.progress_percent}%`}
            meta={`Stage ${skill.current_stage} of ${skill.total_stages}`}
            href="/progress/skills"
          />
        ) : (
          <HighlightRow
            eyebrow="Top skill"
            title="Pick a skill to train"
            value="—"
            href="/progress/skills"
          />
        )}
      </div>

      {/*
       * From 768px up the vertical budget that forced the split doesn't exist, so the
       * `/progress/*` screens render inline as further panels of this same grid — one page,
       * one card language, no seam between a phone column and a desktop one.
       */}
      <section className={`${styles.panel} ${styles.volume}`} aria-labelledby="volume-heading">
        <div className={styles.panelHead}>
          <h2 id="volume-heading" className={styles.panelTitle}>
            <Link href="/progress/volume">Volume</Link>
          </h2>
          <span className={styles.panelMeta}>Last {range.label}</span>
        </div>
        <div className={styles.panelBody}>
          <Suspense fallback={<PanelFallback height="16rem" />}>
            <VolumePanelBody range={range} unit={unit} />
          </Suspense>
        </div>
      </section>

      <section
        className={`${styles.panel} ${styles.frequency}`}
        aria-labelledby="frequency-heading"
      >
        <div className={styles.panelHead}>
          <h2 id="frequency-heading" className={styles.panelTitle}>
            <Link href="/progress/frequency">Frequency</Link>
          </h2>
          <span className={styles.panelMeta}>Last {range.weeks} weeks</span>
        </div>
        <div className={styles.panelBody}>
          <Suspense fallback={<PanelFallback height="10rem" />}>
            <FrequencyPanelBody weeks={range.weeks} />
          </Suspense>
        </div>
      </section>

      <section className={`${styles.panel} ${styles.records}`} aria-labelledby="records-heading">
        <div className={styles.panelHead}>
          <h2 id="records-heading" className={styles.panelTitle}>
            <Link href="/progress/records">Records</Link>
          </h2>
          <span className={styles.panelMeta}>All-time</span>
        </div>
        <div className={styles.panelBody}>
          {prs.items.length > 0 ? (
            <PrList prs={prs.items} unit={unit} />
          ) : (
            <p className={styles.empty}>No personal records yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}
