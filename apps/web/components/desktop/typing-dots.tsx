import { cn } from "@/lib/utils";

/** Three bouncing dots: the model is writing. */
export function TypingDots({ className, label = "thinking" }: { className?: string; label?: string }) {
  return (
    <span role="status" aria-label={label} className={cn("inline-flex items-center gap-1", className)}>
      {[0, 1, 2].map((i) => (
        <span key={i} className="typing-dot size-1.5 rounded-full bg-current" style={{ animationDelay: `${i * 140}ms` }} />
      ))}
    </span>
  );
}
