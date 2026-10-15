"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { UploadCloud, FileText, XCircle, RotateCcw, ShieldAlert } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RiskMeter } from "@/components/ui/RiskMeter";
import { ClassificationBadge } from "@/components/status-badges";
import { AnalysisProgress } from "@/components/analyze/AnalysisProgress";
import { SecurityAlertModal } from "@/components/analyze/SecurityAlertModal";
import { PrintActions } from "@/components/analyze/PrintActions";
import { api, ApiError } from "@/lib/api";
import { cn, categoryLabel, formatDuration } from "@/lib/utils";
import type { JobDetail } from "@/types";

type Phase = "idle" | "uploading" | "processing" | "done";

export default function AnalyzePage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const pollJob = useCallback(
    (jobId: string) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const updated = await api.get<JobDetail>(`/api/v1/jobs/${jobId}`);
          setJob(updated);
          if (["AWAITING_DECISION", "READY", "BLOCKED", "FAILED", "CANCELLED"].includes(updated.status)) {
            stopPolling();
            setPhase("done");
          }
        } catch {
          stopPolling();
        }
      }, 600);
    },
    [stopPolling]
  );

  async function handleFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }
    setError(null);
    setJob(null);
    setPhase("uploading");
    try {
      const form = new FormData();
      form.append("file", file);
      const created = await api.postForm<JobDetail>("/api/v1/documents/analyze", form);
      setJob(created);
      setPhase("processing");
      pollJob(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
      setPhase("idle");
    }
  }

  function reset() {
    stopPolling();
    setJob(null);
    setPhase("idle");
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function onCancel() {
    if (!job) return;
    setBusy(true);
    try {
      const updated = await api.post<JobDetail>(`/api/v1/jobs/${job.id}/cancel`);
      setJob({ ...job, ...updated });
    } finally {
      setBusy(false);
    }
  }

  async function onMask() {
    if (!job) return;
    setBusy(true);
    try {
      await api.post(`/api/v1/jobs/${job.id}/sanitize`);
      setPhase("processing");
      pollJob(job.id);
    } finally {
      setBusy(false);
    }
  }

  async function refreshJob() {
    if (!job) return;
    const updated = await api.get<JobDetail>(`/api/v1/jobs/${job.id}`);
    setJob(updated);
  }

  const showAlertModal = job?.status === "AWAITING_DECISION";

  return (
    <AppShell title="Document Security Analysis">
      {phase === "idle" && (
        <div className="mx-auto mt-10 max-w-2xl">
          <Card>
            <CardContent>
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file) handleFile(file);
                }}
                className={cn(
                  "flex flex-col items-center justify-center rounded-lg border-2 border-dashed py-16 transition-colors",
                  dragging ? "border-primary bg-primary/5" : "border-border"
                )}
              >
                <UploadCloud size={40} className="mb-4 text-muted-foreground" />
                <p className="mb-1 font-medium">Drop PDF here</p>
                <p className="mb-4 text-sm text-muted-foreground">OR</p>
                <Button onClick={() => fileInputRef.current?.click()}>Select File</Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFile(file);
                  }}
                />
                <p className="mt-5 text-xs text-muted-foreground">Supported: PDF</p>
              </div>
              {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
            </CardContent>
          </Card>
        </div>
      )}

      {(phase === "uploading" || (phase === "processing" && job)) && (
        <div className="mx-auto mt-10 max-w-2xl">
          <Card>
            <CardContent>
              <div className="mb-6 flex items-center gap-3">
                <FileText size={20} className="text-muted-foreground" />
                <span className="font-medium">{job?.original_filename || "Uploading..."}</span>
              </div>
              <AnalysisProgress status={job?.status || "UPLOADED"} />
            </CardContent>
          </Card>
        </div>
      )}

      {phase === "done" && job && (
        <div className="mx-auto mt-6 max-w-3xl space-y-5">
          <Card>
            <CardContent>
              <div className="mb-5 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileText size={20} className="text-muted-foreground" />
                  <div>
                    <p className="font-semibold">{job.original_filename}</p>
                    <p className="text-xs text-muted-foreground">Job {job.id}</p>
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={reset}>
                  <RotateCcw /> New analysis
                </Button>
              </div>

              {job.status === "BLOCKED" || job.status === "FAILED" ? (
                <div className="flex items-start gap-3 rounded-lg bg-destructive/10 p-4 text-destructive">
                  <ShieldAlert size={20} className="mt-0.5 shrink-0" />
                  <div>
                    <p className="font-medium">Print job blocked</p>
                    <p className="mt-1 text-sm">{job.status_message || "This document was blocked for security reasons."}</p>
                  </div>
                </div>
              ) : job.status === "CANCELLED" ? (
                <div className="flex items-center gap-3 rounded-lg bg-muted p-4 text-muted-foreground">
                  <XCircle size={20} />
                  <p>Print job cancelled. The original document was not released.</p>
                </div>
              ) : (
                <div className="space-y-5">
                  {job.risk_score !== null && (
                    <div>
                      <p className="mb-1.5 text-xs font-medium text-muted-foreground">Risk Score</p>
                      <RiskMeter score={job.risk_score} size="lg" />
                    </div>
                  )}
                  <div className="flex items-center gap-3">
                    <p className="text-xs font-medium text-muted-foreground">Classification</p>
                    {job.classification && <ClassificationBadge value={job.classification} />}
                  </div>

                  {job.detections.length > 0 && (
                    <div>
                      <p className="mb-2 text-xs font-medium text-muted-foreground">Sensitive Data Detected</p>
                      <div className="grid grid-cols-2 gap-x-8 gap-y-1.5">
                        {job.detections.map((d) => (
                          <div key={d.category} className="flex items-center justify-between border-b py-1 text-sm last:border-0">
                            <span className="text-muted-foreground">{categoryLabel(d.category)}</span>
                            <span className="font-semibold tabular-nums">{d.count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex gap-8 pt-1 text-sm text-muted-foreground">
                    <span>
                      Pages: <strong className="text-foreground">{job.page_count}</strong>
                    </span>
                    <span>
                      Processing Time: <strong className="text-foreground">{formatDuration(job.processing_time_ms)}</strong>
                    </span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {job.status === "READY" && (
            <Card>
              <CardContent>
                <p className="mb-3 text-xs font-medium text-muted-foreground">Sanitized Document Preview</p>
                <iframe
                  src={api.fileUrl(`/api/v1/jobs/${job.id}/document`)}
                  className="h-[480px] w-full rounded-lg border"
                  title="Sanitized document preview"
                />
                <div className="mt-4">
                  <PrintActions jobId={job.id} onPrinted={refreshJob} />
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {showAlertModal && job && (
        <SecurityAlertModal
          riskScore={job.risk_score || 0}
          classification={job.classification || "RESTRICTED"}
          detections={job.detections}
          busy={busy}
          onCancel={onCancel}
          onMask={onMask}
        />
      )}
    </AppShell>
  );
}
