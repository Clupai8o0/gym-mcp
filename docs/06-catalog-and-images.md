# 06 — Exercise Catalog & Illustration Pipeline

Two offline jobs plus one runtime fallback:
1. **`scripts/seed_catalog.py`** — import the exercise catalog into Neon (metadata only).
2. **`scripts/generate_illustrations.py`** — batch-generate the minimal line-art image for
   every catalog exercise, upload to Vercel Blob, set `illustration_url`.
3. **On-demand fallback** (`services/images.ensure`) — generate a single image at runtime for
   a newly-created custom exercise or any catalog row still missing art.

Both scripts are **idempotent** and safe to re-run (they skip completed work).

## Source dataset

**yuhonas/free-exercise-db** — https://github.com/yuhonas/free-exercise-db
- **~800+ exercises**, **Unlicense (public domain)** — no attribution required, safe to use.
- Consolidated JSON: `dist/exercises.json` (fetch the raw file at build time; pin a commit SHA
  for reproducibility).
- Fields per exercise: `id, name, force, level, mechanic, equipment, primaryMuscles,
  secondaryMuscles, instructions, category, images`. `force`, `mechanic`, `equipment` may be null.
- **We use the metadata only.** We do **not** ship the dataset's photos — Tempo generates its
  own consistent line-art (Decision D9). The `images` field is ignored except optionally as a
  visual reference when crafting the style (not shipped).

### Field mapping (dataset → `exercises` table)

| Dataset | Column | Notes |
|---|---|---|
| `id` or `name` | `source_id` | Stable key for idempotent upsert (`source='free-exercise-db'`) |
| `name` | `name` | |
| slugify(`name`) | `slug` | url-safe, unique in the global catalog |
| `category` | `category` | |
| `force` | `force` | null allowed |
| `level` | `level` | |
| `mechanic` | `mechanic` | null allowed |
| `equipment` | `equipment` | null allowed |
| `primaryMuscles` | `primary_muscles` | text[] |
| `secondaryMuscles` | `secondary_muscles` | text[] |
| `instructions` | `instructions` | text[] |
| — | `illustration_status` | `'pending'` on import |

### `seed_catalog.py` behavior
- Fetch pinned `dist/exercises.json`; validate against a Pydantic model; report any schema drift.
- **Upsert** by `(source, source_id)`; never duplicate on re-run; update changed metadata.
- Idempotent, transactional, logs a summary (`inserted/updated/skipped`).
- Runs locally or in CI against the target Neon DB (use the unpooled URL). **Not** on Vercel.

## Illustration style (LOCKED SPEC)

All ~1000 images must look like one set. Lock these and do not vary per-image except the pose:

- **Style:** minimal, single-weight **line art**. One continuous clean linework figure
  performing the movement. No shading, no gradients, no background scene.
- **Palette:** **monochrome** — off-white/near-white lines on a **transparent** background
  (so the app can place them on any surface); one optional accent color for the active
  muscle/implement, used sparingly and identically across all images.
- **Figure:** neutral, androgynous, faceless or minimal-face mannequin; consistent proportions;
  consistent line weight; centered; full movement shown at the most legible mid-point of the rep.
- **Equipment:** drawn in the same line style (barbell/dumbbell/machine as simple geometric line
  forms). If `equipment` is null/body-only, no implement.
- **Framing:** square **1024×1024**, generous padding, subject centered, safe margins so it
  crops well into cards and circles.
- **No text, no logos, no watermarks, no measurement annotations.**

### Reference-locking procedure (do this ONCE, in Phase 4, before the batch)
1. Hand-generate **5–8 exemplars** across categories (a squat, a bench press, a pull-up, a
   plank, a cable movement) and iterate the prompt until they are visually consistent.
2. Save the winning **prompt template** and, if the model supports it, a **reference image**
   to feed as style anchor for the batch. Record both in `illustration_meta` provenance.
3. Get a quick human/Antigravity design sign-off on the exemplars **before** spending on 1000.

### Prompt template (starting point — refine during locking)
```
Minimal single-weight line-art illustration of a person performing "{name}".
{equipment_clause}  Show the movement at its most recognizable position, emphasizing the
{primary_muscles} working. Clean continuous linework, off-white lines, fully transparent
background, no shading, no color fills{accent_clause}, faceless neutral mannequin, centered,
generous margins, square composition. Instructional, iconographic, consistent proportions.
No text, no logos, no background scenery.
```
- `{equipment_clause}` = "Using a {equipment}." or "" (body-only).
- `{accent_clause}` = "" for pure monochrome, or ", except a single {accent} accent on the
  primary muscle" if the locked style uses one accent.

## Image generation

- **Model:** OpenAI **GPT Image 2** (current flagship; `gpt-image-1` retires 2026-10-23, so we
  do **not** use it). Pin the model id in config.
- **Size:** `1024x1024`. **Quality:** start at **low/medium** — the minimal line style needs no
  high-detail tier; validate on the exemplars. **Background:** request transparent if supported;
  otherwise post-process to transparent PNG.
- **Cost math (one-time):** GPT Image 2 ≈ $0.005–$0.211/image by quality×size. ~1000 images:
  ~**$5–$35 at low/medium**, up to ~$100+ at high. Prefer low/medium; the style tolerates it.
- **Output format:** PNG (transparent). Store the exact `{model, prompt, prompt_hash, size,
  quality, generated_at}` into `exercises.illustration_meta` for provenance/reproducibility.

### `generate_illustrations.py` behavior
- Query `exercises WHERE illustration_status IN ('pending','failed')`.
- For each (bounded concurrency, e.g. 4–8; respect rate limits + retries w/ backoff):
  1. Set `illustration_status='generating'`.
  2. Build the prompt from the locked template + this exercise's fields.
  3. Call GPT Image 2 → PNG bytes.
  4. Upload to **Vercel Blob** at a stable key `exercises/{slug}.png` (public), get the URL.
  5. Update `illustration_url`, `illustration_status='ready'`, `illustration_meta`.
  6. On error: `illustration_status='failed'`, log; the row is retried next run.
- Idempotent: `ready` rows are skipped. Safe to Ctrl-C and resume.
- **Not** on Vercel (long-running, exceeds the 300s function limit). Run locally or as a CI job.
- Emit a final report: counts by status, total cost estimate, list of failures.

## On-demand fallback (`services/images.ensure`)

For custom exercises and any still-missing art, at runtime:
- `POST /api/exercises/{id}/illustration` (or lazily when an exercise with no image is opened).
- Guard against duplicate work: if status is `generating`, return "in progress"; use a short
  advisory lock or a status check so two requests don't double-generate.
- Generate **one** image within the function budget, upload to Blob, update the row, return the URL.
- The UI shows a tasteful placeholder (see `08`) until `ready`.

## Storage (Vercel Blob)

- Public blobs; URL stored in `exercises.illustration_url`; served via Vercel's CDN.
- Key scheme: `exercises/{slug}.png`. Overwriting regenerates in place (keep the same URL).
- Serve responsive sizes via the Next.js `<Image>` component; keep originals at 1024².

## Definition of Done (catalog + images phase)
- `seed_catalog.py` imports the full dataset idempotently; `SELECT count(*) FROM exercises`
  ≈ dataset size; re-running changes nothing.
- Style exemplars approved; prompt template + reference locked and committed.
- `generate_illustrations.py` produces `ready` images for the large majority of the catalog,
  stored in Blob, with `illustration_meta` provenance; failures are re-runnable.
- On-demand endpoint generates and persists a single image for a custom exercise.
- A cost report is produced and within the expected range.
