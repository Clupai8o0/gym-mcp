/** Join truthy class names. Tiny, dependency-free `clsx` for CSS-Module class composition. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
