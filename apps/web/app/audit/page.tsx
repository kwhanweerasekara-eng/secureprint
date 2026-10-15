"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { eventLabel, formatDateTime, formatShortDateTime } from "@/lib/utils";
import type { AuditEvent } from "@/types";

const EVENT_TYPES = [
  "JOB_RECEIVED",
  "ANALYSIS_STARTED",
  "DATA_DETECTED",
  "CLASSIFIED",
  "AWAITING_DECISION",
  "DECISION_MASK",
  "DECISION_CANCEL",
  "SANITIZED",
  "RELEASED_TO_PRINTER",
  "PRINT_COMPLETED",
  "BLOCKED",
  "FAILED",
  "LOGIN_SUCCESS",
  "LOGIN_FAILED",
];
const CLASSIFICATIONS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"];
const STATUSES = ["READY", "COMPLETED", "BLOCKED", "CANCELLED", "FAILED"];

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [eventType, setEventType] = useState("ALL");
  const [classification, setClassification] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");

  function buildParams() {
    const params = new URLSearchParams();
    if (eventType !== "ALL") params.set("event_type", eventType);
    if (classification !== "ALL") params.set("classification", classification);
    if (statusFilter !== "ALL") params.set("status", statusFilter);
    return params;
  }

  useEffect(() => {
    api
      .get<AuditEvent[]>(`/api/v1/audit?${buildParams().toString()}`)
      .then(setEvents)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventType, classification, statusFilter]);

  return (
    <AppShell title="Audit Log" adminOnly>
      <Card>
        <CardContent>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <Select value={eventType} onValueChange={(v) => setEventType(v ?? "ALL")}>
              <SelectTrigger className="w-[190px]">
                <SelectValue placeholder="All event types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All event types</SelectItem>
                {EVENT_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {eventLabel(t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={classification} onValueChange={(v) => setClassification(v ?? "ALL")}>
              <SelectTrigger className="w-[190px]">
                <SelectValue placeholder="All classifications" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All classifications</SelectItem>
                {CLASSIFICATIONS.map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v ?? "ALL")}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="All job statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All job statuses</SelectItem>
                {STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <a href={api.fileUrl(`/api/v1/audit/export?${buildParams().toString()}`)} className="ml-auto">
              <Button variant="outline" size="sm">
                <Download /> Export CSV
              </Button>
            </a>
          </div>

          <div className="overflow-x-auto sp-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Event</TableHead>
                  <TableHead>Job</TableHead>
                  <TableHead>Message</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="whitespace-nowrap text-muted-foreground" title={formatDateTime(e.created_at)}>
                      {formatShortDateTime(e.created_at)}
                    </TableCell>
                    <TableCell className="font-medium">{eventLabel(e.event_type)}</TableCell>
                    <TableCell className="text-muted-foreground">{e.job_id || "-"}</TableCell>
                    <TableCell className="max-w-[420px] truncate text-muted-foreground" title={e.message}>
                      {e.message}
                    </TableCell>
                  </TableRow>
                ))}
                {events.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                      No audit events match these filters.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
