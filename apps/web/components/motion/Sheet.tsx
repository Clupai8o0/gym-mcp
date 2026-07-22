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

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * An interruptible slide-in panel (docs/08 primitive `Sheet`). Overlay fade + panel slide via
 * `motion` + `AnimatePresence`; the panel slides in with ease-out and *out* with ease-in (docs/08
 * §3). A proper modal dialog: ESC + overlay-click close it, body scroll locks, focus moves in and
 * is **trapped** (Tab cycles within the panel), the background is `inert`, and focus restores on
 * close. Reduced motion → instant cross-fade, no slide.
 */
export function Sheet({ open, onClose, children, side = "bottom", label }: SheetProps) {
  const reduce = useReducedMotion();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      // Trap Tab within the panel so focus can't wander onto the obscured page behind the overlay.
      const items = panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (items.length === 0) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === panelRef.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();

    // Hide the rest of the document from AT + pointer while the dialog is open.
    const backdropped = Array.from(document.body.children).filter((el) => el !== rootRef.current);
    backdropped.forEach((el) => el.setAttribute("inert", ""));

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      backdropped.forEach((el) => el.removeAttribute("inert"));
      previous?.focus?.();
    };
  }, [open, onClose]);

  // Portals need a DOM target — render nothing during SSR (sheets always start closed).
  if (typeof document === "undefined") return null;

  const offset = side === "bottom" ? { y: "100%" } : { x: "100%" };
  const enter = reduce
    ? { duration: durations.fast, ease: easings.out }
    : { duration: durations.slow, ease: easings.out };
  const exit = reduce
    ? { duration: durations.fast, ease: easings.out }
    : { duration: durations.base, ease: easings.in };

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className={styles.root} ref={rootRef}>
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
            animate={reduce ? { opacity: 1, transition: enter } : { x: 0, y: 0, transition: enter }}
            exit={reduce ? { opacity: 0, transition: exit } : { ...offset, transition: exit }}
          >
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
