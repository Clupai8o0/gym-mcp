"use client";

import { useCallback, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Button, Input, Select } from "@/components/ui";
import { CATEGORIES, EQUIPMENT, LEVELS, MUSCLES } from "@/lib/catalog";
import styles from "./FilterBar.module.css";

// The filter Sheet (and the `motion` library it pulls in) only ever renders after a tap on mobile,
// so defer its chunk — this keeps `motion` out of the Library route's initial bundle (docs/07 CWV).
const Sheet = dynamic(() => import("@/components/motion/Sheet").then((m) => m.Sheet), {
  ssr: false,
});

const SEARCH_DEBOUNCE_MS = 250;

/** Search glyph for the input adornment. */
function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
      <path d="m20 20-3-3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Library filters, synced to the URL for shareability + back-button (docs/07 §Library). Search is
 * debounced; muscle/equipment/category/level apply immediately. On mobile the selects live in a
 * `Sheet`; on desktop they sit inline. Server re-renders the grid from the new `searchParams`.
 */
export function FilterBar() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [sheetOpen, setSheetOpen] = useState(false);

  const get = (key: string) => searchParams.get(key) ?? "";

  // Push a mutated query to the URL without scrolling or growing history.
  const setParam = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) params.set(key, value);
      else params.delete(key);
      params.delete("offset"); // any filter change returns to the first page
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  // Debounced search input. Local state drives the field for responsiveness while typing; when
  // the URL's `q` changes externally (clear, back button, shared link) we re-sync during render
  // via the previous-value pattern — no effect needed (React "adjust state when a prop changes").
  const urlQuery = get("q");
  const [search, setSearch] = useState(urlQuery);
  const [syncedQuery, setSyncedQuery] = useState(urlQuery);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  if (urlQuery !== syncedQuery) {
    setSyncedQuery(urlQuery);
    setSearch(urlQuery);
  }

  const onSearchChange = (value: string) => {
    setSearch(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setParam("q", value.trim()), SEARCH_DEBOUNCE_MS);
  };

  const activeCount = ["muscle", "equipment", "category", "level"].filter((k) => get(k)).length;
  const hasAny = activeCount > 0 || get("q") !== "";

  const clearAll = () => {
    router.replace(pathname, { scroll: false });
    setSearch("");
    setSheetOpen(false);
  };

  const selects = (
    <>
      <Select
        aria-label="Filter by muscle"
        options={MUSCLES}
        placeholder="All muscles"
        value={get("muscle")}
        onChange={(e) => setParam("muscle", e.target.value)}
      />
      <Select
        aria-label="Filter by equipment"
        options={EQUIPMENT}
        placeholder="All equipment"
        value={get("equipment")}
        onChange={(e) => setParam("equipment", e.target.value)}
      />
      <Select
        aria-label="Filter by category"
        options={CATEGORIES}
        placeholder="All categories"
        value={get("category")}
        onChange={(e) => setParam("category", e.target.value)}
      />
      <Select
        aria-label="Filter by level"
        options={LEVELS}
        placeholder="All levels"
        value={get("level")}
        onChange={(e) => setParam("level", e.target.value)}
      />
    </>
  );

  return (
    <div className={styles.bar}>
      <div className={styles.searchRow}>
        <Input
          type="search"
          inputMode="search"
          aria-label="Search exercises"
          placeholder="Search exercises…"
          leading={<SearchIcon />}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className={styles.search}
        />
        <Button
          variant="outline"
          className={styles.mobileFilters}
          onClick={() => setSheetOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={sheetOpen}
        >
          Filters{activeCount > 0 ? ` (${activeCount})` : ""}
        </Button>
      </div>

      <div className={styles.inlineSelects}>
        {selects}
        {hasAny && (
          <Button variant="ghost" size="sm" onClick={clearAll}>
            Clear
          </Button>
        )}
      </div>

      <Sheet open={sheetOpen} onClose={() => setSheetOpen(false)} label="Filter exercises">
        <div className={styles.sheetHeader}>
          <h2 className={styles.sheetTitle}>Filters</h2>
          <Button variant="ghost" size="sm" onClick={() => setSheetOpen(false)}>
            Done
          </Button>
        </div>
        <div className={styles.sheetSelects}>{selects}</div>
        {hasAny && (
          <Button variant="outline" fullWidth onClick={clearAll} className={styles.sheetClear}>
            Clear all
          </Button>
        )}
      </Sheet>
    </div>
  );
}
