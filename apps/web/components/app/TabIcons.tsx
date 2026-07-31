/**
 * The four tab glyphs. Minimal monochrome line-art on a 24px grid — the same visual language
 * as the exercise illustrations and the Tempo mark (docs/08). All decorative: every tab ships
 * a visible text label, so the icon never carries the accessible name.
 */
const BASE = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

export type TabIcon = (props: { className?: string }) => React.ReactElement;

/** Home — the week's training at a glance. */
export const HomeIcon: TabIcon = ({ className }) => (
  <svg {...BASE} className={className}>
    <path d="M3.5 10.2 12 3.75l8.5 6.45v9.05a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z" />
    <path d="M9.25 20.25v-6h5.5v6" />
  </svg>
);

/** Library — the catalog grid. */
export const LibraryIcon: TabIcon = ({ className }) => (
  <svg {...BASE} className={className}>
    <rect x="3.75" y="3.75" width="7" height="7" rx="1.5" />
    <rect x="13.25" y="3.75" width="7" height="7" rx="1.5" />
    <rect x="3.75" y="13.25" width="7" height="7" rx="1.5" />
    <rect x="13.25" y="13.25" width="7" height="7" rx="1.5" />
  </svg>
);

/** Log — add a set. */
export const LogIcon: TabIcon = ({ className }) => (
  <svg {...BASE} className={className}>
    <rect x="3.75" y="3.75" width="16.5" height="16.5" rx="4.5" />
    <path d="M12 8.25v7.5M8.25 12h7.5" />
  </svg>
);

/** You — the account. */
export const YouIcon: TabIcon = ({ className }) => (
  <svg {...BASE} className={className}>
    <circle cx="12" cy="8.25" r="3.5" />
    <path d="M4.75 20.25a7.25 7.25 0 0 1 14.5 0" />
  </svg>
);
