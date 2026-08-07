/**
 * Cut the landing page's line art into theme-aware masks.
 *
 * The drawings in `public/illustrations/` are generated, then split here. Two problems make the
 * split necessary rather than decorative:
 *
 *  1. **The generator does not emit alpha.** Asked for a transparent background it *paints* a
 *     transparency checkerboard as real grey pixels. So the cut-out has to come from luminance.
 *     The background greys sit well below the off-white linework, and the threshold is read off
 *     each image's own border, because the fake checkerboard came out near-black on some images
 *     and mid-grey on others — one hardcoded number kept either the light checkers or no strokes.
 *
 *  2. **A finished picture would hard-code white lines**, which vanish on the light theme. So each
 *     source is split by chroma into two ALPHA MASKS — body and implement — which the page paints
 *     with `var(--ill-ink)` and `var(--accent)` (`components/marketing/illustrations/`). Colour
 *     comes from tokens at render time, which is what lets one asset be correct on a near-black
 *     canvas and on white, and lets the hero figure sit quieter than the same figure in a card.
 *
 * Run manually after the art changes (dev-only; not part of the build):
 *   node scripts/build-illustration-masks.mjs --src ~/wherever-the-generations-are
 *
 * The raw generations are **not committed** — the baked checkerboard is high-entropy noise that
 * does not compress, so ten 1024px PNGs are ~5 MB even lossless, against 200 KB for every mask
 * they produce. `PROMPTS` below is the provenance instead: same convention as the catalog
 * pipeline (docs/06), which stores the prompt rather than the intermediate. Image generation is
 * not deterministic, so re-running these gives *new* art in the same style, not these drawings
 * back — the committed masks are the artefact.
 *
 * `sharp` is not a declared dependency of @tempo/web — it ships transitively with Next.js, so we
 * resolve it from the workspace store, the same way `generate-icons.mjs` does.
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { mkdirSync, readdirSync, writeFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");

function loadSharp() {
  try {
    return require("sharp");
  } catch {
    const store = join(webRoot, "..", "..", "node_modules", ".pnpm");
    const dir = readdirSync(store).find((d) => d.startsWith("sharp@"));
    if (!dir) throw new Error("sharp not found in the workspace store");
    return require(join(store, dir, "node_modules", "sharp"));
  }
}
const sharp = loadSharp();

/* ── Provenance ───────────────────────────────────────────────────────────────────────────── */

/**
 * The style lock, appended to every subject. It is the catalog's own spec (docs/06 §style) almost
 * verbatim, on purpose: the landing page is meant to preview the real library, so the marketing
 * art and the 800 exercise illustrations should read as one hand.
 */
const STYLE = `
Style, follow exactly: one continuous clean linework figure, a single uniform stroke weight
throughout, rounded line caps. Off-white (#f2f2f2) lines on a fully transparent background. No
shading, no gradients, no colour fills, no hatching. Exactly one accent colour, warm orange
#ff7a17, used only on the implement — the body stays off-white. Faceless neutral androgynous
mannequin, no facial features, no hair, no clothing detail. Consistent anatomical proportions.
Instructional and iconographic, like a technical exercise diagram. No text, no numbers, no logos,
no watermark, no background scenery, no floor line, no shadow.
`.trim();

/** Model: Gemini 3 Pro Image, one session so the six glyphs hold a common style. */
const PROMPTS = {
  lifter:
    "Standing upright holding a loaded barbell at the hang, arms straight down, the bar across the front of the thighs — the top of a deadlift. Front view, symmetrical. Accent on the bar and plates.",
  "bench-sit":
    "Sitting on the end of a flat gym bench between sets, leaning slightly forward, forearms resting toward the knees, holding a phone in one hand and looking down at it. Side view, facing left. The bench is plain line geometry. Accent on the phone only.",
  lockout:
    "Standing upright with a loaded barbell locked out straight overhead, both arms extended above the head, bar horizontal above the crown. Front view, symmetrical. Accent on the bar and plates.",
  "glyph-squat":
    "Barbell back squat. Front view, bar across the shoulders behind the neck, hands gripping wide, knees bent in a deep squat.",
  "glyph-pullup":
    "Pull-up. Front view, hanging from a horizontal fixed bar, both arms overhead, body straight below. Accent on the fixed bar.",
  "glyph-bench":
    "Barbell bench press. Side view, lying on a flat bench, feet on the floor, pressing a barbell straight up above the chest.",
  "glyph-plank":
    "Forearm plank. Side view, straight rigid body from head to heels, propped on both forearms, toes down. Body-weight — NO accent colour at all.",
  "glyph-kettlebell":
    "Kettlebell swing. Side view, hinged at the hips, knees slightly bent, arms straight, kettlebell swung down between the legs. The bell must read as a kettlebell: round body with a distinct semicircular handle arch. Accent on the kettlebell.",
  "glyph-row":
    "Bent-over barbell row. Side view, torso hinged forward with a flat back, knees slightly bent, bar pulled toward the waist, elbows drawn back.",
};

/** Glyphs also asked for a BOLD stroke and ~70% fill of a square frame, to survive thumbnailing. */
const GLYPH_FRAMING =
  "Simplified so it stays legible shrunk to thumbnail size, with a bold stroke. The drawing fills about seventy percent of a square frame, centred, with even margins on all four sides.";

/* ── Cutting ──────────────────────────────────────────────────────────────────────────────── */

/** Chroma at or above CHROMA_HI is fully accent; below CHROMA_LO, fully ink. */
const CHROMA_LO = 26;
const CHROMA_HI = 70;

const JOBS = [
  { src: "gen-lifter.png", name: "lifter", square: false, width: 640 },
  { src: "gen-betweensets.png", name: "bench-sit", square: false, width: 800 },
  { src: "gen-lockout.png", name: "lockout", square: false, width: 460 },
  { src: "glyph-squat.png", name: "glyph-squat", square: true, width: 320 },
  { src: "glyph-pullup.png", name: "glyph-pullup", square: true, width: 320 },
  { src: "glyph-bench.png", name: "glyph-bench", square: true, width: 320 },
  { src: "glyph-plank.png", name: "glyph-plank", square: true, width: 320 },
  { src: "glyph-kettlebell.png", name: "glyph-kettlebell", square: true, width: 320 },
  { src: "glyph-row.png", name: "glyph-row", square: true, width: 320 },
];

const clamp01 = (n) => (n < 0 ? 0 : n > 1 ? 1 : n);
const lum = (r, g, b) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

/** White RGB carrying the mask in alpha — `mask-image` reads alpha, so the RGB never shows. */
function maskImage(alpha, width, height) {
  const rgba = Buffer.alloc(width * height * 4);
  for (let i = 0; i < width * height; i++) {
    rgba[i * 4] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = 255;
    rgba[i * 4 + 3] = alpha[i];
  }
  return sharp(rgba, { raw: { width, height, channels: 4 } });
}

/**
 * Reassemble the exact prompt a subject was drawn from, so the provenance above is runnable
 * rather than just readable:
 *
 *   node scripts/build-illustration-masks.mjs --prompt glyph-kettlebell
 */
function promptFor(name) {
  const subject = PROMPTS[name];
  if (!subject) throw new Error(`no prompt on record for "${name}"`);
  const framing = name.startsWith("glyph-") ? `\n\n${GLYPH_FRAMING}` : "";
  return `Minimal single-weight line-art illustration. ${subject}${framing}\n\n${STYLE}`;
}

const promptFlag = process.argv.indexOf("--prompt");
if (promptFlag > -1) {
  const name = process.argv[promptFlag + 1];
  console.log(name ? promptFor(name) : Object.keys(PROMPTS).join("\n"));
  process.exit(0);
}

const srcFlag = process.argv.indexOf("--src");
const SRC = srcFlag > -1 ? process.argv[srcFlag + 1] : join(here, "illustration-sources");
const OUT = join(webRoot, "public", "illustrations");
mkdirSync(OUT, { recursive: true });

const report = [];

for (const job of JOBS) {
  const { data, info } = await sharp(join(SRC, job.src))
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const { width, height } = info;

  // Read the cut threshold off this image's own border — see the note at the top of the file.
  let bgHi = 0;
  const band = Math.max(4, Math.round(Math.min(width, height) * 0.02));
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (!(x < band || y < band || x >= width - band || y >= height - band)) continue;
      const o = (y * width + x) * 3;
      const l = lum(data[o], data[o + 1], data[o + 2]);
      if (l > bgHi) bgHi = l;
    }
  }
  const lo = Math.max(bgHi + 6, 120);
  const hi = Math.min(lo + 55, 248);

  const px = width * height;
  const ink = Buffer.alloc(px);
  const accent = Buffer.alloc(px);
  let accentPixels = 0;
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      const o = i * 3;
      const r = data[o];
      const g = data[o + 1];
      const b = data[o + 2];
      const chroma = Math.max(r, g, b) - Math.min(r, g, b);
      // How much this pixel reads as "drawn": bright neutral linework, or saturated at all. The
      // accent sits at mid luminance, so brightness alone would drop the barbells.
      const byLum = clamp01((lum(r, g, b) - lo) / (hi - lo));
      const byChroma = clamp01((chroma - CHROMA_LO) / (CHROMA_HI - CHROMA_LO));
      const coverage = Math.max(byLum, byChroma);
      if (coverage <= 0.02) continue;

      const a = Math.round(coverage * 255);
      // Saturated pixels go to the accent layer, neutral ones to ink, and the antialiased
      // boundary between them is split between the two rather than drawn into both.
      accent[i] = Math.round(a * byChroma);
      ink[i] = a - accent[i];
      if (accent[i] > 24) accentPixels++;

      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }

  // One bounding box for both layers, so ink and accent stay registered after cropping.
  const crop = { left: minX, top: minY, width: maxX - minX + 1, height: maxY - minY + 1 };

  const shape = (img) => {
    const cropped = img.extract(crop);
    const clear = { r: 0, g: 0, b: 0, alpha: 0 };
    // Glyphs are normalised to a common square so the sheet's cells line up and a wide pose does
    // not end up drawn larger than a tall one.
    return job.square
      ? cropped
          .resize(job.width - 24, job.width - 24, { fit: "contain", background: clear })
          .extend({ top: 12, bottom: 12, left: 12, right: 12, background: clear })
      : cropped.resize({ width: job.width });
  };

  const inkOut = await shape(maskImage(ink, width, height))
    .webp({ lossless: true, effort: 6 })
    .toBuffer({ resolveWithObject: true });
  writeFileSync(join(OUT, `${job.name}-ink.webp`), inkOut.data);

  let accentKb = "—";
  // A body-weight movement holds nothing, so its accent layer is empty — don't ship a blank file.
  if (accentPixels > px * 0.0004) {
    const accentOut = await shape(maskImage(accent, width, height))
      .webp({ lossless: true, effort: 6 })
      .toBuffer({ resolveWithObject: true });
    writeFileSync(join(OUT, `${job.name}-accent.webp`), accentOut.data);
    accentKb = (accentOut.data.length / 1024).toFixed(1);
  }

  report.push({
    name: job.name,
    cut: `${lo.toFixed(0)}-${hi.toFixed(0)}`,
    out: `${inkOut.info.width}x${inkOut.info.height}`,
    // Feed this back into `ratio` in components/marketing/illustrations/art.ts, which reserves the
    // box before the mask loads so nothing shifts.
    ratio: `${inkOut.info.width} / ${inkOut.info.height}`,
    inkKb: (inkOut.data.length / 1024).toFixed(1),
    accentKb,
  });
}

console.table(report);
console.log(
  `Each prompt is PROMPTS[name] + STYLE, plus GLYPH_FRAMING for the six glyphs. ` +
    `${Object.keys(PROMPTS).length} subjects on record.`,
);
