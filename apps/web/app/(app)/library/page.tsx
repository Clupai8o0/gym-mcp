import Link from "next/link";
import { cookies } from "next/headers";
import type { Metadata } from "next";

import { FilterBar, InfiniteExerciseGrid } from "@/components/library";
import { Button, EmptyState } from "@/components/ui";
import { listExercises, type ExerciseFilters } from "@/lib/api";
import { FILTER_KEYS } from "@/lib/catalog";
import { THEME_COOKIE, toThemePreference } from "@/lib/theme";
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

export default async function LibraryPage({ searchParams }: { searchParams: Promise<RawParams> }) {
  const params = await searchParams;
  const filters = readFilters(params);

  // One cookie read for the whole grid, handed down to every tile — the illustrations are two
  // distinct assets chosen per surface (see `IllustrationView`), and the client-appended pages
  // need the same answer the server used for the first one.
  const [{ items, total }, cookieStore] = await Promise.all([
    listExercises({ ...filters, limit: PAGE_SIZE }),
    cookies(),
  ]);
  const preference = toThemePreference(cookieStore.get(THEME_COOKIE)?.value);

  // Stable identity for this filter set: changes exactly when the result set does.
  const cacheKey = new URLSearchParams(filters as Record<string, string>).toString() || "all";

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
        <InfiniteExerciseGrid
          initial={items}
          initialTotal={total}
          pageSize={PAGE_SIZE}
          query={filters}
          preference={preference}
          cacheKey={cacheKey}
        />
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
