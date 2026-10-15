"use client";

import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { JobStatus } from "@/types";

const STAGES: { key: JobStatus; label: string }[] = [
  { key: "UPLOADED", label: "Uploading" },
  { key: "ANALYZING", label: "Analyzing" },
  { key: "DETECTED", label: "Detecting" },
  { key: "CLASSIFIED", label: "Calculating Risk & Classifying" },
];

export function AnalysisProgress({ status }: { status: JobStatus }) {
  const terminal = ["AWAITING_DECISION", "READY", "SANITIZING", "PRINTING", "COMPLETED"];
  const currentIndex = terminal.includes(status) ? STAGES.length : STAGES.findIndex((s) => s.key === status);

  return (
    <div className="space-y-3">
      {STAGES.map((stage, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        return (
          <div key={stage.key} className="flex items-center gap-3">
            {done ? (
              <CheckCircle2 size={18} className="shrink-0 text-emerald-600" />
            ) : active ? (
              <Loader2 size={18} className="shrink-0 animate-spin text-primary" />
            ) : (
              <Circle size={18} className="shrink-0 text-muted-foreground/40" />
            )}
            <span className={done || active ? "text-sm font-medium" : "text-sm text-muted-foreground"}>
              {stage.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
