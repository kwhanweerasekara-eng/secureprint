import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const CLASSIFICATION_STYLES: Record<string, string> = {
  PUBLIC: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-600/20",
  INTERNAL: "bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-600/20",
  CONFIDENTIAL: "bg-amber-500/10 text-amber-800 dark:text-amber-400 border-amber-600/20",
  RESTRICTED: "bg-red-500/10 text-red-700 dark:text-red-400 border-red-600/20",
};

const STATUS_STYLES: Record<string, string> = {
  UPLOADED: "bg-muted text-muted-foreground border-transparent",
  QUEUED: "bg-muted text-muted-foreground border-transparent",
  ANALYZING: "bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-600/20",
  DETECTED: "bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-600/20",
  CLASSIFIED: "bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-600/20",
  AWAITING_DECISION: "bg-amber-500/10 text-amber-800 dark:text-amber-400 border-amber-600/20",
  SANITIZING: "bg-amber-500/10 text-amber-800 dark:text-amber-400 border-amber-600/20",
  READY: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-600/20",
  PRINTING: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-600/20",
  COMPLETED: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-600/20",
  BLOCKED: "bg-red-500/10 text-red-700 dark:text-red-400 border-red-600/20",
  CANCELLED: "bg-muted text-muted-foreground border-transparent",
  FAILED: "bg-red-500/10 text-red-700 dark:text-red-400 border-red-600/20",
};

export function ClassificationBadge({ value, className }: { value: string; className?: string }) {
  return (
    <Badge variant="outline" className={cn(CLASSIFICATION_STYLES[value] || "", className)}>
      {value}
    </Badge>
  );
}

export function StatusBadge({ value, className }: { value: string; className?: string }) {
  return (
    <Badge variant="outline" className={cn(STATUS_STYLES[value] || "", className)}>
      {value}
    </Badge>
  );
}
