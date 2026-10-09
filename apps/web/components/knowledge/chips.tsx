import { cn } from "@/lib/utils";

const PRIVACY: Record<string, string> = {
  public: "border-line text-text-2",
  internal: "border-ev-tool/50 text-ev-tool",
  confidential: "border-risk-high/60 bg-risk-high/10 text-risk-high",
  restricted: "border-st-failed/70 bg-st-failed/12 text-st-failed",
};
const TRUST: Record<string, string> = {
  verified: "border-st-running/60 bg-st-running/10 text-st-running",
  trusted: "border-ev-knowledge/50 text-ev-knowledge",
  unverified: "border-st-waiting/60 text-st-waiting",
  untrusted: "border-untrusted/60 bg-untrusted-bg text-untrusted",
};

export function Chip({ label, value, className }: { label?: string; value: string; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-md border border-line px-2 py-0.5 font-mono text-xs", className)}>
      {label && <span className="text-muted-foreground">{label}</span>}
      {value}
    </span>
  );
}

export const PrivacyChip = ({ value }: { value?: string | null }) =>
  value ? <Chip label="privacy" value={value} className={PRIVACY[value] ?? PRIVACY.public} /> : null;

export const TrustChip = ({ value }: { value?: string | null }) =>
  value ? <Chip label="trust" value={value} className={TRUST[value] ?? "border-line"} /> : null;
