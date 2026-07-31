import Link from "next/link";
import type { Metadata } from "next";

import { FrequencyHeatmap, PrList, RangeControl, VolumeChart } from "@/components/dashboard";
import {
  DayStrip,
  HighlightRow,
  HomeHeader,
  HomeWelcome,
  WeekStats,
  WorkoutCard,
} from "@/components/home";
import { LocalTime } from "@/components/ui";
import {
  getActiveSession,
  getFrequency,
  getSession,
  getSkillsOverview,
  getVolume,
  listExercises,
  listPrs,
  listSessions,
} from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { formatPrValue, prTypeLabel } from "@/lib/format";
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
  const { from: rangeFrom, to: rangeTo } = rangeWindow(range);

  const now = new Date();
  const nowIso = now.toISOString();
  const weekFrom = new Date(now.getTime() - WEEK_MS).toISOString();
  const stripFrom = new Date(now.getTime() - STRIP_MS).toISOString();

  const [me, active, recent, lifetime, weekVolume, prs, skills, rangeVolume, frequency] =
    await Promise.all([
      requireUser("/dashboard"),
      getActiveSession(),
      // The nine-day window feeds both the strip and (filtered to seven) the session count.
      listSessions({ from: stripFrom, limit: 100 }),
      // `total` only — the cheapest way to ask "has this account ever logged anything?".
      listSessions({ limit: 1 }),
      getVolume(weekFrom, nowIso),
      listPrs(),
      getSkillsOverview(),
      // Desktop's right column; cheap aggregates, and SSR can't branch on viewport width.
      getVolume(rangeFrom, rangeTo),
      getFrequency(range.weeks),
    ]);

  const unit = me.unit_pref as UnitPref;
  const detail = active ? await getSession(active.id) : null;
  const setCount = detail
    ? detail.exercises.reduce((total, group) => total + group.sets.length, 0)
    : 0;

  const isNewAccount = lifetime.total === 0 && prs.items.length === 0;
  if (isNewAccount) {
    const catalog = await listExercises({ limit: 1 });
    return (
      <div className={styles.page}>
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
      <div className={styles.summary}>
        <HomeHeader me={me} now={nowIso} />

        <WorkoutCard active={active} setCount={setCount} />

        <WeekStats
          sessions={weekSessions.length}
          tonnageKg={weekTonnage}
          sets={weekSets}
          prs={weekPrs}
          unit={unit}
        />

        <DayStrip sessionDates={recent.items.map((session) => session.performed_at)} now={nowIso} />

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
      </div>

      {/* ≥768px only: the `/progress/*` screens, inline. Hidden (not fetched away) on mobile. */}
      <div className={styles.wide}>
        <div className={styles.wideHead}>
          <h2 className={styles.wideTitle}>Progress</h2>
          <RangeControl current={range.key} />
        </div>

        <section className={styles.section} aria-labelledby="volume-heading">
          <div className={styles.sectionHead}>
            <h3 id="volume-heading" className={styles.sectionTitle}>
              <Link href="/progress/volume">Volume</Link>
            </h3>
            <span className={styles.sectionMeta}>Last {range.label}</span>
          </div>
          {rangeVolume.items.length > 0 ? (
            <VolumeChart volume={rangeVolume} unit={unit} />
          ) : (
            <p className={styles.empty}>No sets logged in this range yet.</p>
          )}
        </section>

        <section className={styles.section} aria-labelledby="frequency-heading">
          <div className={styles.sectionHead}>
            <h3 id="frequency-heading" className={styles.sectionTitle}>
              <Link href="/progress/frequency">Frequency</Link>
            </h3>
            <span className={styles.sectionMeta}>Last {range.weeks} weeks</span>
          </div>
          <FrequencyHeatmap frequency={frequency} />
        </section>

        <section className={styles.section} aria-labelledby="records-heading">
          <div className={styles.sectionHead}>
            <h3 id="records-heading" className={styles.sectionTitle}>
              <Link href="/progress/records">Records</Link>
            </h3>
            <span className={styles.sectionMeta}>All-time</span>
          </div>
          {prs.items.length > 0 ? (
            <PrList prs={prs.items} unit={unit} />
          ) : (
            <p className={styles.empty}>No personal records yet.</p>
          )}
        </section>
      </div>
    </div>
  );
}
