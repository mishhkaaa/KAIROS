import { cn } from "@/lib/utils";

/** The KAIROS mark: four tesserae, the last in ink. */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn("size-5 shrink-0", className)} aria-hidden>
      <rect x="2" y="2" width="9" height="9" rx="2" fill="var(--brand)" />
      <rect x="13" y="2" width="9" height="9" rx="2" fill="var(--brand)" opacity="0.55" />
      <rect x="2" y="13" width="9" height="9" rx="2" fill="var(--brand)" opacity="0.55" />
      <rect x="13" y="13" width="9" height="9" rx="2" fill="var(--text)" opacity="0.85" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-bold tracking-tight", className)}>
      KAIR<span className="text-brand">OS</span>
    </span>
  );
}
