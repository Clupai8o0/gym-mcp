import { ImageResponse } from "next/og";

import { ridgeLines } from "@/components/marketing/trainingSeries";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Tempo: a workout log you can actually read";

/**
 * The share card. Rebuilds the hero's language rather than screenshotting it: near-black canvas,
 * the wordmark, the headline, and the same ridge running grey to accent.
 *
 * Satori (which renders this) supports a deliberately small slice of CSS. It has no support for
 * external stylesheets, CSS custom properties, `color-mix()` or `mask-image`, so every value here
 * is a literal and the grey-to-orange ramp is interpolated in JS instead. The token values are
 * duplicated on purpose and the dark side is used unconditionally, because a share card has no
 * viewer theme to follow.
 */
const CANVAS = "#0a0a0a";
const INK = "#ffffff";
const BODY = "#dadbdf";
const MUTED = "#868a90";
const ACCENT = "#ff7a17";
const NEUTRAL = "#363a3f";

/** Linear blend between the neutral hairline and the accent, matching the hero's ramp. */
function ramp(t: number): string {
  const from = [0x36, 0x3a, 0x3f];
  const to = [0xff, 0x7a, 0x17];
  const channel = (i: number) => Math.round(from[i]! + (to[i]! - from[i]!) * t);
  return `rgb(${channel(0)},${channel(1)},${channel(2)})`;
}

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: CANVAS,
          padding: 64,
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {/* The three tempo bars from the app icon, drawn as plain divs. */}
          <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 34 }}>
            <div style={{ width: 8, height: 20, borderRadius: 4, background: ACCENT }} />
            <div style={{ width: 8, height: 34, borderRadius: 4, background: ACCENT }} />
            <div style={{ width: 8, height: 27, borderRadius: 4, background: ACCENT }} />
          </div>
          <div style={{ color: INK, fontSize: 30, letterSpacing: -0.6 }}>Tempo</div>
        </div>

        {/* The ridge, as stacked SVGs so each line can carry its own flat colour. */}
        <div style={{ display: "flex", position: "relative", height: 250, width: "100%" }}>
          {ridgeLines.map((line) => (
            <svg
              key={line.row}
              width={1072}
              height={250}
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              style={{ position: "absolute", top: 0, left: 0 }}
            >
              <path
                d={line.d}
                fill="none"
                stroke={ramp(line.row / (ridgeLines.length - 1))}
                strokeWidth={0.6}
                strokeOpacity={line.opacity}
              />
            </svg>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ color: INK, fontSize: 68, letterSpacing: -2.4, lineHeight: 1.05 }}>
            Six months, one honest picture.
          </div>
          <div style={{ color: BODY, fontSize: 26, lineHeight: 1.4, maxWidth: 860 }}>
            An illustrated exercise library, fast set logging, and a dashboard you can actually
            read.
          </div>
          <div style={{ color: MUTED, fontSize: 20, letterSpacing: 1.4 }}>
            VOLUME · RECORDS · FREQUENCY
          </div>
        </div>

        <div style={{ display: "flex", height: 1, width: "100%", background: NEUTRAL }} />
      </div>
    ),
    size,
  );
}
