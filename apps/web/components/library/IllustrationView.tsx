/**
 * The illustration renderer, minus the cookie read.
 *
 * Split out of {@link IllustrationImage} so it can live in **both** component graphs. The server
 * wrapper resolves the theme preference from the cookie and delegates here; the Library's
 * infinite grid — a client component, because it appends pages after the initial render — passes
 * the preference down as a prop it received from the server. One implementation, two callers, no
 * `next/headers` in the browser bundle.
 */
import Image, { getImageProps } from "next/image";
import ReactDOM from "react-dom";

import { SharedElement } from "@/components/motion/SharedElement";
import { cn } from "@/lib/cn";
import type { ThemePreference } from "@/lib/theme";
import type { IllustrationStatus } from "@/lib/types";
import styles from "./IllustrationImage.module.css";

/** The light twin is selected by this query; the dark asset is everything else. */
const LIGHT_MEDIA = "(prefers-color-scheme: light)";
const DARK_MEDIA = "not all and (prefers-color-scheme: light)";

export interface IllustrationViewProps {
  /** Bold off-white linework — the asset that belongs on a dark surface. */
  url: string | null;
  /**
   * The same art with its linework inverted to near-black, for light surfaces (docs/06). The
   * amber working-muscle accent is byte-identical in both, which is why this is a second asset
   * and not a `filter: invert()` — inverting would drag the accent to blue. Omit it (or pass
   * `null`) and the dark asset is used on both surfaces, as before.
   */
  urlLight?: string | null;
  status: string;
  name: string;
  /** The viewer's resolved appearance preference; `system` defers the choice to the browser. */
  preference: ThemePreference;
  /** When set, the media morphs across the list→detail transition (docs/08 signature moment). */
  shareName?: string;
  /** Prioritize the LCP image on detail pages. */
  priority?: boolean;
  size?: "card" | "detail";
  className?: string;
}

/** Minimal line-art placeholder shown until an illustration is `ready` (docs/06/07). */
function Placeholder({ status }: { status: string }) {
  return (
    <div
      className={cn(styles.placeholder, status === "generating" && styles.generating)}
      aria-hidden
    >
      <svg viewBox="0 0 48 48" fill="none" className={styles.glyph}>
        <path
          d="M6 24h6M36 24h6M12 18v12M36 18v12M18 21v6M30 21v6M18 24h12"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

interface ThemedProps {
  dark: string;
  light: string;
  preference: ThemePreference;
  alt: string;
  sizes: string;
  priority: boolean;
}

/**
 * Picks between the two assets.
 *
 * An **explicit** preference is already known to the server (it rides in on the theme cookie), so
 * the right asset goes straight into a plain `next/image` — one `src`, one request, and `priority`
 * keeps emitting its own preload exactly as before.
 *
 * **System** is the case the server can't resolve, so it doesn't try: a `<picture>` hands the
 * decision to the browser, which settles it from `prefers-color-scheme` while parsing — no JS, no
 * round-trip, no flash of the wrong linework, and it re-decides for free if the viewer flips their
 * system appearance mid-session. `getImageProps` is what keeps the `<source>` on the optimizer
 * (AVIF + the tuned `deviceSizes`) instead of dropping to the raw Blob original. The hand-rolled
 * preloads stand in for the one `next/image` no longer emits here; each is scoped to the same
 * media query as its source, so exactly one of the two is ever fetched.
 */
function ThemedIllustration({ dark, light, preference, alt, sizes, priority }: ThemedProps) {
  // `light === dark` is an exercise with no light twin yet — nothing to choose between.
  if (preference !== "system" || light === dark) {
    return (
      <Image
        src={preference === "light" ? light : dark}
        alt={alt}
        fill
        sizes={sizes}
        className={styles.image}
        priority={priority}
      />
    );
  }

  const common = { alt, fill: true, sizes, priority };
  const { props: darkProps } = getImageProps({ ...common, src: dark });
  const { props: lightProps } = getImageProps({ ...common, src: light });

  if (priority) {
    // The same call `next/image` makes for a priority image, once per variant and scoped to the
    // media query its `<source>` answers — so the head still carries an LCP preload, and still
    // only one of the two is ever fetched. Imperative rather than a rendered `<link>` because
    // this is the path React dedupes: six priority tiles share one pair of hoisted preloads.
    ReactDOM.preload(darkProps.src, {
      as: "image",
      media: DARK_MEDIA,
      imageSrcSet: darkProps.srcSet,
      imageSizes: darkProps.sizes,
      fetchPriority: "high",
    });
    ReactDOM.preload(lightProps.src, {
      as: "image",
      media: LIGHT_MEDIA,
      imageSrcSet: lightProps.srcSet,
      imageSizes: lightProps.sizes,
      fetchPriority: "high",
    });
  }

  return (
    <picture className={styles.picture}>
      <source media={LIGHT_MEDIA} srcSet={lightProps.srcSet} sizes={lightProps.sizes} />
      {/* A bare <img>, but not an unoptimized one: these are next/image's own computed props
          (getImageProps), and a <picture> has to wrap a real <img>, not the component. */}
      <img {...darkProps} className={styles.image} alt={alt} />
    </picture>
  );
}

/**
 * The exercise illustration — the primary visual texture of the app (docs/08). Renders a sized
 * image (explicit ratio → no CLS) when `ready`, otherwise a tasteful placeholder. Wrapping in
 * {@link SharedElement} lets the same illustration morph from the grid into the detail page.
 *
 * Synchronous and free of server-only imports, so it renders identically on either side of the
 * boundary. Callers that *are* server components should reach for {@link IllustrationImage},
 * which reads the cookie for them.
 */
export function IllustrationView({
  url,
  urlLight,
  status,
  name,
  preference,
  shareName,
  priority = false,
  size = "card",
  className,
}: IllustrationViewProps) {
  const ready = status === "ready" && Boolean(url);

  const media = (
    <div className={cn(styles.frame, styles[size], className)}>
      {ready ? (
        <ThemedIllustration
          dark={url as string}
          light={urlLight ?? (url as string)}
          preference={preference}
          alt={`Line-art illustration of ${name}`}
          sizes={
            size === "detail" ? "(max-width: 768px) 100vw, 480px" : "(max-width: 768px) 50vw, 240px"
          }
          priority={priority}
        />
      ) : (
        <Placeholder status={status} />
      )}
    </div>
  );

  if (shareName) {
    return <SharedElement name={shareName}>{media}</SharedElement>;
  }
  return media;
}

export type { IllustrationStatus };
