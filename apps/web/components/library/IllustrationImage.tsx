import Image from "next/image";

import { SharedElement } from "@/components/motion/SharedElement";
import { cn } from "@/lib/cn";
import type { IllustrationStatus } from "@/lib/types";
import styles from "./IllustrationImage.module.css";

export interface IllustrationImageProps {
  url: string | null;
  status: string;
  name: string;
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

/**
 * The exercise illustration — the primary visual texture of the app (docs/08). Renders a sized
 * `next/image` (explicit ratio → no CLS) when `ready`, otherwise a tasteful placeholder. Wrapping
 * in {@link SharedElement} lets the same illustration morph from the grid into the detail page.
 */
export function IllustrationImage({
  url,
  status,
  name,
  shareName,
  priority = false,
  size = "card",
  className,
}: IllustrationImageProps) {
  const ready = status === "ready" && Boolean(url);
  const media = (
    <div className={cn(styles.frame, styles[size], className)}>
      {ready ? (
        <Image
          src={url as string}
          alt={`Line-art illustration of ${name}`}
          fill
          sizes={
            size === "detail" ? "(max-width: 768px) 100vw, 480px" : "(max-width: 768px) 50vw, 240px"
          }
          className={styles.image}
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
