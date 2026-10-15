"use client";

import Link from "next/link";
import {
  Upload,
  ScanSearch,
  Search,
  Gauge,
  Tags,
  ShieldQuestion,
  ShieldCheck,
  ShieldX,
  Scissors,
  Sparkles,
  AlertTriangle,
  Printer,
  CheckCircle2,
  Ban,
  XCircle,
  LogIn,
  LogOut,
  Activity,
  type LucideIcon,
} from "lucide-react";
import { eventLabel, parseApiDate } from "@/lib/utils";

const EVENT_META: Record<string, { icon: LucideIcon; tone: string }> = {
  JOB_RECEIVED: { icon: Upload, tone: "text-muted-foreground bg-muted" },
  ANALYSIS_STARTED: { icon: ScanSearch, tone: "text-sky-600 bg-sky-500/10" },
  NO_TEXT_LAYER: { icon: Search, tone: "text-amber-600 bg-amber-500/10" },
  DATA_DETECTED: { icon: Search, tone: "text-sky-600 bg-sky-500/10" },
  RISK_SCORED: { icon: Gauge, tone: "text-sky-600 bg-sky-500/10" },
  CLASSIFIED: { icon: Tags, tone: "text-indigo-600 bg-indigo-500/10" },
  AWAITING_DECISION: { icon: ShieldQuestion, tone: "text-amber-600 bg-amber-500/10" },
  DECISION_CANCEL: { icon: XCircle, tone: "text-muted-foreground bg-muted" },
  DECISION_MASK: { icon: ShieldCheck, tone: "text-emerald-600 bg-emerald-500/10" },
  SANITIZING: { icon: Scissors, tone: "text-amber-600 bg-amber-500/10" },
  SANITIZED: { icon: Sparkles, tone: "text-emerald-600 bg-emerald-500/10" },
  REDACTION_VERIFICATION_FAILED: { icon: ShieldX, tone: "text-destructive bg-red-500/10" },
  RELEASED_TO_PRINTER: { icon: Printer, tone: "text-emerald-600 bg-emerald-500/10" },
  PRINT_COMPLETED: { icon: CheckCircle2, tone: "text-emerald-600 bg-emerald-500/10" },
  BLOCKED: { icon: Ban, tone: "text-destructive bg-red-500/10" },
  FAILED: { icon: AlertTriangle, tone: "text-destructive bg-red-500/10" },
  LOGIN_SUCCESS: { icon: LogIn, tone: "text-muted-foreground bg-muted" },
  LOGIN_FAILED: { icon: LogIn, tone: "text-destructive bg-red-500/10" },
  LOGOUT: { icon: LogOut, tone: "text-muted-foreground bg-muted" },
};

function timeAgo(iso: string): string {
  const diffMs = Date.now() - parseApiDate(iso).getTime();
  const s = Math.floor(diffMs / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function ActivityFeed({
  events,
}: {
  events: { id: string; job_id: string | null; event_type: string; message: string; created_at: string }[];
}) {
  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-muted-foreground text-sm gap-2">
        <Activity size={22} className="text-muted-foreground/50" />
        No DLP activity recorded yet.
      </div>
    );
  }

  return (
    <ol className="space-y-1">
      {events.map((e) => {
        const meta = EVENT_META[e.event_type] || { icon: Activity, tone: "text-muted-foreground bg-muted" };
        const Icon = meta.icon;
        return (
          <li key={e.id} className="flex items-start gap-3 py-2 border-b border-border/50 last:border-0">
            <span className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${meta.tone}`}>
              <Icon size={14} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium truncate">{eventLabel(e.event_type)}</p>
                <span className="text-[11px] text-muted-foreground shrink-0">{timeAgo(e.created_at)}</span>
              </div>
              <p className="text-xs text-muted-foreground truncate">
                {e.message || "—"}
                {e.job_id && (
                  <>
                    {" "}
                    &middot;{" "}
                    <Link href={`/jobs/${e.job_id}`} className="text-primary hover:underline">
                      {e.job_id}
                    </Link>
                  </>
                )}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
