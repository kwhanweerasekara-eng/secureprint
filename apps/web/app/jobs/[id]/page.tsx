"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { ClassificationBadge, StatusBadge } from "@/components/status-badges";
import { RiskMeter } from "@/components/ui/RiskMeter";
import { PrintActions } from "@/components/analyze/PrintActions";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { categoryLabel, eventLabel, formatDateTime, formatDuration } from "@/lib/utils";
import type { JobDetail } from "@/types";

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const [job, setJob] = useState<JobDetail | null>(null);

  function reload() {
    api.get<JobDetail>(`/api/v1/jobs/${params.id}`).then(setJob).catch(() => {});
  }

  useEffect(reload, [params.id]);

  if (!job) {
    return (
      <AppShell title="Job Details">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <Skeleton className="h-[340px] rounded-xl" />
            <Skeleton className="h-[140px] rounded-xl" />
          </div>
          <Skeleton className="h-[400px] rounded-xl" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title={`Job ${job.id}`}>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Job Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-y-3 text-sm">
                <div>
                  <dt className="text-xs text-muted-foreground">Document</dt>
                  <dd>{job.original_filename}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Submission Time</dt>
                  <dd>{formatDateTime(job.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Status</dt>
                  <dd>
                    <StatusBadge value={job.status} />
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Classification</dt>
                  <dd>{job.classification ? <ClassificationBadge value={job.classification} /> : "-"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Action</dt>
                  <dd>{job.action}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Processing Time</dt>
                  <dd>{formatDuration(job.processing_time_ms)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Pages</dt>
                  <dd>{job.page_count}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Printer</dt>
                  <dd>{job.printer_id || "Web Analysis Mode"}</dd>
                </div>
              </dl>

              {job.risk_score !== null && (
                <div className="mt-5">
                  <p className="mb-1.5 text-xs text-muted-foreground">Risk Score</p>
                  <RiskMeter score={job.risk_score} />
                </div>
              )}

              {job.status_message && (
                <div className="mt-4 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {job.status_message}
                </div>
              )}

              {job.status === "READY" && (
                <div className="mt-5">
                  <PrintActions jobId={job.id} onPrinted={reload} />
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Detection Categories</CardTitle>
            </CardHeader>
            <CardContent>
              {job.detections.length === 0 ? (
                <p className="text-sm text-muted-foreground">No sensitive data detected.</p>
              ) : (
                <div className="grid grid-cols-2 gap-x-8 gap-y-1.5">
                  {job.detections.map((d) => (
                    <div key={d.category} className="flex items-center justify-between border-b py-1.5 text-sm last:border-0">
                      <span className="text-muted-foreground">{categoryLabel(d.category)}</span>
                      <span className="font-semibold tabular-nums">{d.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Event Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="ml-2 space-y-5 border-l">
              {job.events.map((e) => (
                <li key={e.id} className="relative ml-4">
                  <div className="absolute -ml-[21px] mt-1.5 h-2 w-2 rounded-full bg-primary" />
                  <p className="text-xs text-muted-foreground">{formatDateTime(e.created_at)}</p>
                  <p className="text-sm font-medium">{eventLabel(e.event_type)}</p>
                  {e.message && <p className="text-xs text-muted-foreground">{e.message}</p>}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
