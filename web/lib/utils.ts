// Minimal className joiner (cn) — used by copy-paste UI components (e.g. fancy/*).
// No clsx/tailwind-merge dependency: we only ever join, never resolve conflicts.
export function cn(...classes: Array<string | undefined | null | false>): string {
  return classes.filter(Boolean).join(' ')
}
