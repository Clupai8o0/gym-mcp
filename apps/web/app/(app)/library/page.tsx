import Link from "next/link";
import type { Metadata } from "next";

import { ExerciseGrid, FilterBar } from "@/components/library";
import { Button, EmptyState } from "@/components/ui";
import { listExercises, type ExerciseFilters } from "@/lib/api";
import { FILTER_KEYS } from "@/lib/catalog";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Library",
  description: "Browse the full illustrated exercise catalog.",
};

const PAGE_SIZE = 48;

type RawParams = Record<string, string | string[] | undefined>;

/** First value of a (possibly repeated) search param. */
function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/** Extract the catalog filters (q/muscle/equipment/category/level) from the URL. */
function readFilters(params: RawParams): ExerciseFilters {
  const filters: ExerciseFilters = {};
  for (const key of FILTER_KEYS) {
    const value = one(params[key]);
    if (value) filters[key] = value;
  }
  return filters;
}

/** Build a Library href preserving filters, at a given offset (for prev/next). */
function pageHref(params: RawParams, offset: number): string {
  const query = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = one(params[key]);
    if (value) query.set(key, value);
  }
  if (offset > 0) query.set("offset", String(offset));
  const qs = query.toString();
  return qs ? `/library?${qs}` : "/library";
}

export default async function LibraryPage({ searchParams }: { searchParams: Promise<RawParams> }) {
  const params = await searchParams;
  const filters = readFilters(params);
  const offset = Math.max(0, Number.parseInt(one(params.offset), 10) || 0);

  const { items, total, limit } = await listExercises({
    ...filters,
    limit: PAGE_SIZE,
    offset,
  });

  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <p className="eyebrow">Exercise library</p>
        <h1 className={styles.title}>Browse the catalog</h1>
        <p className={styles.lede}>
          Every movement, illustrated. Search or filter by muscle, equipment, category, and level.
        </p>
      </header>

      <FilterBar />

      {total > 0 ? (
        <>
          <p className={styles.count} aria-live="polite">
            Showing <span className="tnum">{from}</span>–<span className="tnum">{to}</span> of{" "}
            <span className="tnum">{total}</span>
          </p>

          <ExerciseGrid exercises={items} />

          {(hasPrev || hasNext) && (
            <nav className={styles.pagination} aria-label="Pagination">
              {hasPrev ? (
                <Link href={pageHref(params, Math.max(0, offset - limit))} scroll>
                  <Button variant="outline">← Previous</Button>
                </Link>
              ) : (
                <Button variant="outline" disabled>
                  ← Previous
                </Button>
              )}
              {hasNext ? (
                <Link href={pageHref(params, offset + limit)} scroll>
                  <Button variant="outline">Next →</Button>
                </Link>
              ) : (
                <Button variant="outline" disabled>
                  Next →
                </Button>
              )}
            </nav>
          )}
        </>
      ) : (
        <EmptyState
          title="No exercises match those filters"
          description="Try broadening your search or clearing a filter to see more of the catalog."
          action={
            <Link href="/library">
              <Button variant="primary">Clear filters</Button>
            </Link>
          }
        />
      )}
    </div>
  );
}
