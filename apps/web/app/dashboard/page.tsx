"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  FileStack,
  ShieldOff,
  ShieldCheck,
  Gauge,
  Timer,
  Eye,
  Radio,
  Globe2,
  Building2,
  Lock,
  ShieldAlert as ShieldAlertIcon,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, CardTitle, CardDescription, CardAction, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ClassificationBadge, StatusBadge } from "@/components/status-badges";
import { StatCard } from "@/components/dashboard/StatCard";
import {
  BlockedAllowedDonut,
  CategoryBarChart,
  ClassificationDonut,
  JobsOverTimeChart,
  RiskScoreBarChart,
} from "@/components/dashboard/DashboardCharts";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { categoryLabel, formatDateTime, formatDuration } from "@/lib/utils";
import type { DashboardStats } from "@/types";

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[76px] rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[76px] rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Skeleton className="h-[340px] rounded-xl" />
        <Skeleton className="h-[340px] rounded-xl" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    function load() {
      api.get<DashboardStats>("/api/v1/dashboard/stats").then(setStats).catch(() => {});
    }
    load();
    const interval = setInterval(load, 8000);
    return () => clearInterval(interval);
  }, []);

  if (!stats) {
    return (
      <AppShell title="Security Overview">
        <DashboardSkeleton />
      </AppShell>
    );
  }

  const topCategories = Object.entries(stats.detections_by_category)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([category, value]) => ({ label: categoryLabel(category), value }));

  return (
    <AppShell title="Security Overview">
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Documents Processed" value={stats.documents_processed} icon={<FileStack size={20} />} />
        <StatCard label="Blocked Jobs" value={stats.blocked_jobs} icon={<ShieldOff size={20} />} tone="danger" />
        <StatCard label="Masked & Printed" value={stats.masked_jobs} icon={<ShieldCheck size={20} />} tone="warning" />
        <StatCard label="Avg Risk Score" value={stats.average_risk_score} icon={<Gauge size={20} />} />
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Public" value={stats.public_count} icon={<Globe2 size={20} />} tone="success" />
        <StatCard label="Internal" value={stats.internal_count} icon={<Building2 size={20} />} />
        <StatCard label="Confidential" value={stats.confidential_count} icon={<Lock size={20} />} tone="warning" />
        <StatCard label="Restricted" value={stats.restricted_count} icon={<ShieldAlertIcon size={20} />} tone="danger" />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Classification Distribution</CardTitle>
            <CardDescription>Across all processed documents</CardDescription>
          </CardHeader>
          <CardContent>
            <ClassificationDonut data={stats.classification_distribution} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Risk Score Distribution</CardTitle>
            <CardDescription>0-20 / 21-40 / 41-70 / 71-100</CardDescription>
          </CardHeader>
          <CardContent>
            <RiskScoreBarChart data={stats.risk_score_distribution} />
          </CardContent>
        </Card>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Detections by Category</CardTitle>
            <CardDescription>Most frequently detected sensitive data</CardDescription>
          </CardHeader>
          <CardContent>
            <CategoryBarChart data={topCategories} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Blocked vs Allowed</CardTitle>
            <CardDescription>Print jobs by final outcome</CardDescription>
          </CardHeader>
          <CardContent>
            <BlockedAllowedDonut allowed={stats.blocked_vs_allowed.allowed || 0} blocked={stats.blocked_vs_allowed.blocked || 0} />
          </CardContent>
        </Card>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Print Jobs Over Time</CardTitle>
          <CardDescription>Last 14 days</CardDescription>
        </CardHeader>
        <CardContent>
          <JobsOverTimeChart data={stats.jobs_over_time} />
        </CardContent>
      </Card>

      <div className="mb-6 grid grid-cols-1 gap-5 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Recent Print Jobs</CardTitle>
            <CardAction>
              <Link href="/jobs" className="flex items-center gap-1 text-xs text-primary hover:underline">
                <Eye size={13} /> View all
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent className="overflow-x-auto sp-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Classification</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {stats.recent_jobs.map((j) => (
                  <TableRow key={j.id}>
                    <TableCell>
                      <Link href={`/jobs/${j.id}`} className="font-medium text-primary hover:underline">
                        {j.id}
                      </Link>
                      <span className="ml-2 text-xs text-muted-foreground">{j.filename}</span>
                    </TableCell>
                    <TableCell className="tabular-nums">{j.risk_score ?? "-"}</TableCell>
                    <TableCell>{j.classification ? <ClassificationBadge value={j.classification} /> : "-"}</TableCell>
                    <TableCell>
                      <StatusBadge value={j.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(j.created_at)}</TableCell>
                  </TableRow>
                ))}
                {stats.recent_jobs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-6 text-center text-muted-foreground">
                      No print jobs yet. Head to Analyze to get started.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>DLP Activity Log</CardTitle>
            <CardDescription>Live pipeline events</CardDescription>
            <CardAction>
              <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                <Radio size={12} className="animate-pulse" /> Live
              </span>
            </CardAction>
          </CardHeader>
          <CardContent>
            <ActivityFeed events={stats.recent_events} />
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
        <Timer size={13} /> Average processing time: {formatDuration(stats.average_processing_time_ms)}
      </div>
    </AppShell>
  );
}
