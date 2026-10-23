import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const SIZES = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-8 w-8",
} as const;

export function Spinner({
  size = "sm",
  className,
}: {
  size?: keyof typeof SIZES;
  className?: string;
}) {
  return (
    <Loader2
      aria-hidden
      className={cn("animate-spin text-primary", SIZES[size], className)}
    />
  );
}

/** Full-viewport loader used while the app resolves auth or a route shell. */
export function PageLoader({ label }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="min-h-screen bg-background flex flex-col items-center justify-center gap-3"
    >
      <Spinner size="lg" />
      <p className="text-sm text-muted-foreground">{label ?? "Loading…"}</p>
    </div>
  );
}

/** Centred block loader for a panel or list that is waiting on the backend. */
export function SectionLoader({
  label,
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground",
        className
      )}
    >
      <Spinner size="lg" />
      {label && <p className="text-sm">{label}</p>}
    </div>
  );
}
