/**
 * Generate the Tempo PWA icon set from the brand mark (three sunset bars on near-black).
 *
 * Produces the full install-quality set that `public/icon.svg` alone can't cover:
 *   - icon-192.png / icon-512.png        → maskable-safe "any" PNGs (Android, Chrome install UI)
 *   - icon-maskable-192/512.png          → full-bleed, mark inside the 80% safe zone (adaptive masks)
 *   - apple-touch-icon.png (180)         → iOS home screen (iOS ignores SVG + transparency)
 *   - favicon-32.png / favicon-16.png    → legacy favicon fallbacks
 *
 * Run manually after the mark changes (dev-only; not part of the build):
 *   node scripts/generate-icons.mjs
 *
 * `sharp` is not a declared dependency of @tempo/web — it ships transitively with Next.js, so we
 * resolve it from the workspace store. The PNG outputs are committed brand assets; this script
 * documents how they were derived.
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { readdirSync } from "node:fs";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");
const publicDir = join(webRoot, "public");

// Resolve sharp from the pnpm store (transitive dep of Next).
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

const BG = "#0a0a0a"; // --bg (near-black canvas)
const ACCENT = "#ff7a17"; // --accent (sunset)

/**
 * The three tempo bars in a 512 viewBox, bottom-aligned — the brand mark. Bounding box spans
 * x∈[150,362], y∈[150,372]; its centre is (256, 261).
 */
const BARS = `
  <rect x="150" y="240" width="40" height="132" rx="20"/>
  <rect x="236" y="150" width="40" height="222" rx="20"/>
  <rect x="322" y="196" width="40" height="176" rx="20"/>`;

const MARK_CX = 256;
const MARK_CY = 261;

/**
 * Build an icon SVG string.
 * @param {"rounded"|"full"} bg  rounded brand tile, or full-bleed (masked/apple)
 * @param {number} scale         mark scale about canvas centre (1 = native brand size)
 */
function svg({ bg, scale }) {
  const radius = bg === "rounded" ? 112 : 0;
  // Scale about the mark's bbox centre, then recentre that bbox in the 512 canvas.
  const transform = `translate(256 256) scale(${scale}) translate(${-MARK_CX} ${-MARK_CY})`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="${radius}" fill="${BG}"/>
  <g fill="${ACCENT}" transform="${transform}">${BARS}
  </g>
</svg>`;
}

async function png(name, size, opts) {
  const out = join(publicDir, name);
  await sharp(Buffer.from(svg(opts))).resize(size, size).png({ compressionLevel: 9 }).toFile(out);
  console.log(`  ✓ ${name}  ${size}×${size}`);
}

async function main() {
  console.log("Generating Tempo icon set →", publicDir);
  // "any" PNGs — brand tile, mark at native scale.
  await png("icon-192.png", 192, { bg: "rounded", scale: 1 });
  await png("icon-512.png", 512, { bg: "rounded", scale: 1 });
  // Maskable — full-bleed, mark pulled into the ~80% safe zone (0.62 keeps the cluster clear of any mask).
  await png("icon-maskable-192.png", 192, { bg: "full", scale: 0.62 });
  await png("icon-maskable-512.png", 512, { bg: "full", scale: 0.62 });
  // iOS home screen — full-bleed (iOS rounds it), mark slightly inset.
  await png("apple-touch-icon.png", 180, { bg: "full", scale: 0.82 });
  // Legacy favicon fallbacks.
  await png("favicon-32.png", 32, { bg: "rounded", scale: 1 });
  await png("favicon-16.png", 16, { bg: "rounded", scale: 1 });
  console.log("Done.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
