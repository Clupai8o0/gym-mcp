/**
 * Typed access to React's `<ViewTransition>`. Next's App Router bundles a canary React that
 * exports `ViewTransition` (enabled by `experimental.viewTransition` in next.config), but the
 * stable `@types/react` doesn't declare it — so we read it off the runtime with a single,
 * isolated cast and fall back to a plain wrapper when it's unavailable (older/unsupported
 * browsers just don't animate — docs/08 "graceful fallback").
 */
import * as React from "react";

export interface ViewTransitionProps {
  name?: string;
  /** "morph" tags the transition with a `.morph` class we tune in globals.css. */
  share?: "morph" | "auto" | "none";
  enter?: string;
  exit?: string;
  default?: string;
  children: React.ReactNode;
}

const Impl = (
  React as unknown as {
    ViewTransition?: React.ComponentType<ViewTransitionProps>;
  }
).ViewTransition;

export function ViewTransition(props: ViewTransitionProps): React.ReactElement {
  if (Impl) {
    return <Impl {...props} />;
  }
  return <>{props.children}</>;
}

export const viewTransitionsSupported = Boolean(Impl);
