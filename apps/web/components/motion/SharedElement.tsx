import { ViewTransition } from "./view-transition";

export interface SharedElementProps {
  /** Stable identity shared by the source (grid) and target (detail) element. */
  name: string;
  children: React.ReactNode;
}

/**
 * Names an element so it morphs between routes (docs/08 signature moment: Library list→detail).
 * The browser animates size/position between the old and new elements carrying the same `name`;
 * `share="morph"` opts into the softened blur we tune in globals.css. Reduced motion neutralizes
 * it via the global `::view-transition-*` override.
 */
export function SharedElement({ name, children }: SharedElementProps) {
  return (
    <ViewTransition name={name} share="morph">
      {children}
    </ViewTransition>
  );
}
