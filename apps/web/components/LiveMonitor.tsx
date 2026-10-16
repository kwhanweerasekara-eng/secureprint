"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { categoryLabel } from "@/lib/utils";
import type { Job, JobDetail, JobStatus } from "@/types";

// A job is announced once the server has classified it.
const CLASSIFIED: JobStatus[] = [
  "AWAITING_DECISION",
  "SANITIZING",
  "READY",
  "PRINTING",
  "COMPLETED",
  "BLOCKED",
  "CANCELLED",
  "FAILED",
];

const POLL_MS = 3000;

function printedBy(job: JobDetail): string | null {
  const received = job.events.find((e) => e.event_type === "JOB_RECEIVED");
  const user = received?.event_metadata?.print_user;
  return typeof user === "string" && user ? user : null;
}

function headline(job: JobDetail): string {
  if (job.status === "BLOCKED") return "Blocked";
  if (job.status === "AWAITING_DECISION") return "Waiting for the user's decision";
  if (job.status === "CANCELLED") return "Cancelled by the user";
  if (job.action === "MASK_AND_PRINT") return "Masked and released";
  return "Released";
}

// Short two-tone chime for Restricted documents. Browsers only allow sound
// after the page has been clicked once, so a silent failure is fine.
function chime() {
  try {
    const ctx = new AudioContext();
    [880, 660].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.12, ctx.currentTime + i * 0.18);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.18 + 0.16);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + i * 0.18);
      osc.stop(ctx.currentTime + i * 0.18 + 0.17);
    });
  } catch {
    // no audio available
  }
}

/**
 * Live print monitor: watches for new print jobs and announces each one with a
 * toast showing its level, what kinds of data were found (never the values) and
 * who printed it.
 */
export function LiveMonitor() {
  const router = useRouter();
  const seen = useRef<Set<string> | null>(null);

  useEffect(() => {
    let stopped = false;

    async function announce(id: string) {
      const job = await api.get<JobDetail>(`/api/v1/jobs/${id}`);
      if (stopped || !job.classification) return;
      const found = job.detections
        .filter((d) => d.count > 0)
        .sort((a, b) => b.count - a.count)
        .map((d) => `${categoryLabel(d.category)} ${d.count}`)
        .join(", ");
      const who = printedBy(job);
      const description = [
        headline(job),
        found ? `Found: ${found}` : "No sensitive data found",
        who ? `Printed by ${who}` : null,
      ]
        .filter(Boolean)
        .join("\n");
      const title = `${job.classification}: ${job.original_filename}`;
      const options = {
        description,
        duration: job.classification === "RESTRICTED" || job.classification === "CONFIDENTIAL" ? 10000 : 5000,
        action: { label: "View", onClick: () => router.push(`/jobs/${job.id}`) },
        classNames: { description: "whitespace-pre-line" },
      };
      if (job.classification === "RESTRICTED" || job.status === "BLOCKED") {
        toast.error(title, options);
        chime();
      } else if (job.classification === "CONFIDENTIAL") {
        toast.warning(title, options);
      } else {
        toast.success(title, options);
      }
    }

    async function poll() {
      try {
        const jobs = await api.get<Job[]>("/api/v1/jobs?limit=20");
        if (stopped) return;
        if (seen.current === null) {
          // First look: remember what is already there, announce only new jobs.
          seen.current = new Set(jobs.map((j) => j.id));
          return;
        }
        for (const job of jobs.slice().reverse()) {
          if (seen.current.has(job.id) || !CLASSIFIED.includes(job.status)) continue;
          seen.current.add(job.id);
          announce(job.id).catch(() => {});
        }
      } catch {
        // server unavailable: try again on the next tick
      }
    }

    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [router]);

  return null;
}
