import { forwardRef } from "react";

import { cn } from "@/lib/cn";
import styles from "./Input.module.css";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Optional leading adornment (e.g. a search glyph). */
  leading?: React.ReactNode;
}

/** Text input on dark: `--surface-2` fill, hairline border, focus ring (DESIGN.md `text-input`). */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { leading, className, ...props },
  ref,
) {
  if (leading) {
    return (
      <div className={cn(styles.wrap, className)}>
        <span className={styles.leading} aria-hidden>
          {leading}
        </span>
        <input ref={ref} className={cn(styles.input, styles.hasLeading)} {...props} />
      </div>
    );
  }
  return <input ref={ref} className={cn(styles.input, className)} {...props} />;
});
