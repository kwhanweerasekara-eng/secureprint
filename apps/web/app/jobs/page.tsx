"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ClassificationBadge, StatusBadge } from "@/components/status-badges";
import { api } from "@/lib/api";
import { formatDateTime, formatShortDateTime, humanize } from "@/lib/utils";
import type { Job } from "@/types";

const STATUSES = ["UPLOADED", "ANALYZING", "AWAITING_DECISION", "READY", "COMPLETED", "BLOCKED", "CANCELLED", "FAILED"];
const CLASSIFICATIONS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"];

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [classificationFilter, setClassificationFilter] = useState("ALL");

  useEffect(() => {
    const params = new URLSearchParams();
    if (statusFilter !== "ALL") params.set("status_filter", statusFilter);
    if (classificationFilter !== "ALL") params.set("classification", classificationFilter);
    api.get<Job[]>(`/api/v1/jobs?${params.toString()}`).then(setJobs).catch(() => {});
  }, [statusFilter, classificationFilter]);

  return (
    <AppShell title="Print Jobs">
      <Card>
        <CardContent>
          <div className="mb-4 flex gap-3">
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v ?? "ALL")}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All statuses</SelectItem>
                {STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={classificationFilter} onValueChange={(v) => setClassificationFilter(v ?? "ALL")}>
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
          </div>

          <div className="overflow-x-auto sp-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job ID</TableHead>
                  <TableHead>Document</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Classification</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((j) => (
                  <TableRow key={j.id}>
                    <TableCell>
                      <Link href={`/jobs/${j.id}`} className="font-medium text-primary hover:underline">
                        {j.id}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-[260px] truncate" title={j.original_filename}>
                      {j.original_filename}
                    </TableCell>
                    <TableCell className="tabular-nums">{j.risk_score ?? "-"}</TableCell>
                    <TableCell>{j.classification ? <ClassificationBadge value={j.classification} /> : "-"}</TableCell>
                    <TableCell className="text-muted-foreground">{humanize(j.action)}</TableCell>
                    <TableCell>
                      <StatusBadge value={j.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground" title={formatDateTime(j.created_at)}>
                      {formatShortDateTime(j.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
                {jobs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                      No jobs match these filters.
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
