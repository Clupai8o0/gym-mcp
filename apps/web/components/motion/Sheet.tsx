"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { durations, easings } from "@/design/motion";
import styles from "./Sheet.module.css";

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  /** Edge the panel slides from. `bottom` suits mobile filter/entry panels. */
  side?: "bottom" | "right";
  /** Accessible name for the dialog. */
  label: string;
}

/**
 * An interruptible slide-in panel (docs/08 primitive `Sheet`). Overlay fade + panel slide via
 * `motion` + `AnimatePresence`; ESC and overlay-click close it; body scroll is locked while open;
 * focus moves into the panel and restores on close. Reduced motion → instant, no slide.
 */
export function Sheet({ open, onClose, children, side = "bottom", label }: SheetProps) {
  const reduce = useReducedMotion();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previous?.focus?.();
    };
  }, [open, onClose]);

  // Portals need a DOM target — render nothing during SSR (sheets always start closed).
  if (typeof document === "undefined") return null;

  const offset = side === "bottom" ? { y: "100%" } : { x: "100%" };
  const slide = reduce
    ? { duration: durations.fast, ease: easings.out }
    : { duration: durations.slow, ease: easings.out };

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className={styles.root}>
          <motion.div
            className={styles.overlay}
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: durations.base, ease: easings.out }}
          />
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label={label}
            tabIndex={-1}
            className={side === "bottom" ? styles.panelBottom : styles.panelRight}
            initial={reduce ? { opacity: 0 } : offset}
            animate={reduce ? { opacity: 1 } : { x: 0, y: 0 }}
            exit={reduce ? { opacity: 0 } : offset}
            transition={slide}
          >
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
