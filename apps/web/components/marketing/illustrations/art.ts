/**
 * The landing page's illustration set.
 *
 * Each drawing ships as two **alpha masks** in `public/illustrations/` rather than as a finished
 * picture: one for the body, one for the implement. The page paints them with `--ill-ink` and
 * `--accent`, which is what makes a single asset correct on both themes and lets the same figure
 * sit quiet in the hero and full strength in a card. A baked-in white-line PNG would have been
 * invisible on the light theme and impossible to tune.
 *
 * Generated with Gemini 3 Pro Image against the catalog's own style lock (docs/06 §style), then
 * cut, trimmed and split offline. The intent is that the landing page previews the real library:
 * same brief, same mannequin, same single accent on the implement.
 *
 * `ratio` is the asset's true pixel aspect after trimming, so the box reserves the right height
 * before the mask loads and nothing shifts.
 */
export interface Art {
  /** Basename in `public/illustrations/`. `<name>-ink.webp`, optionally `<name>-accent.webp`. */
  name: string;
  /** Intrinsic width / height, as a CSS `aspect-ratio`. */
  ratio: string;
  /** False for body-weight movements, which hold nothing and so have no accent layer. */
  accent?: boolean;
}

export const BENCH_SIT: Art = { name: "bench-sit", ratio: "800 / 909", accent: true };
export const LOCKOUT: Art = { name: "lockout", ratio: "460 / 689", accent: true };

/**
 * The six catalog movements on the library band. Names are real catalog entries and the captions
 * are rendered as text, so the section reads as a list to a screen reader and a crawler rather
 * than as one picture with six names crammed into an alt string.
 */
export const MOVEMENTS: (Art & { label: string })[] = [
  { name: "glyph-squat", label: "Back squat", ratio: "1 / 1", accent: true },
  { name: "glyph-pullup", label: "Pull-up", ratio: "1 / 1", accent: true },
  { name: "glyph-bench", label: "Bench press", ratio: "1 / 1", accent: true },
  { name: "glyph-plank", label: "Plank", ratio: "1 / 1", accent: false },
  { name: "glyph-kettlebell", label: "Kettlebell swing", ratio: "1 / 1", accent: true },
  { name: "glyph-row", label: "Barbell row", ratio: "1 / 1", accent: true },
];
