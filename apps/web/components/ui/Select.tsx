import { forwardRef } from "react";

import { cn } from "@/lib/cn";
import styles from "./Select.module.css";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends Omit<
  React.SelectHTMLAttributes<HTMLSelectElement>,
  "children"
> {
  options: SelectOption[];
  /** Label shown for the empty/"all" value. */
  placeholder?: string;
}

/** Native-select wrapper (accessible, keyboard-native) styled to match the dark system. */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { options, placeholder, className, ...props },
  ref,
) {
  return (
    <span className={cn(styles.wrap, className)}>
      <select ref={ref} className={styles.select} {...props}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <svg
        className={styles.chevron}
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden
      >
        <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </span>
  );
});
