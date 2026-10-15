"use client";

import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Label, Pie, PieChart, XAxis, YAxis } from "recharts";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";

const CATEGORY_PALETTE = ["#0071e3", "#409cff", "#7ab8ff", "#86868b", "#aeaeb2", "#c7c7cc", "#5ac8fa", "#d2d2d7"];

function EmptyState({ label = "No data yet" }: { label?: string }) {
  return <div className="flex h-full min-h-[200px] items-center justify-center text-sm text-muted-foreground">{label}</div>;
}

// ---------------------------------------------------------------------------
// Classification distribution - donut with a centered total
// ---------------------------------------------------------------------------

const CLASSIFICATION_CONFIG: ChartConfig = {
  count: { label: "Documents" },
  PUBLIC: { label: "Public", color: "#34c759" },
  INTERNAL: { label: "Internal", color: "#5ac8fa" },
  CONFIDENTIAL: { label: "Confidential", color: "#ff9f0a" },
  RESTRICTED: { label: "Restricted", color: "#ff3b30" },
};

export function ClassificationDonut({ data }: { data: Record<string, number> }) {
  const rows = Object.entries(data)
    .map(([classification, count]) => ({ classification, count }))
    .filter((r) => r.count > 0);
  const total = rows.reduce((sum, r) => sum + r.count, 0);

  if (total === 0) return <EmptyState />;

  return (
    <ChartContainer config={CLASSIFICATION_CONFIG} className="mx-auto aspect-square max-h-[260px]">
      <PieChart>
        <ChartTooltip content={<ChartTooltipContent hideLabel />} />
        <Pie data={rows} dataKey="count" nameKey="classification" innerRadius={62} outerRadius={92} strokeWidth={3} paddingAngle={2}>
          {rows.map((r) => (
            <Cell key={r.classification} fill={`var(--color-${r.classification})`} stroke="var(--card)" />
          ))}
          <Label
            content={({ viewBox }) => {
              if (!viewBox || !("cx" in viewBox) || !("cy" in viewBox)) return null;
              return (
                <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                  <tspan x={viewBox.cx} y={viewBox.cy} className="fill-foreground text-2xl font-bold">
                    {total.toLocaleString()}
                  </tspan>
                  <tspan x={viewBox.cx} y={(viewBox.cy ?? 0) + 20} className="fill-muted-foreground text-xs">
                    total
                  </tspan>
                </text>
              );
            }}
          />
        </Pie>
        <ChartLegend content={<ChartLegendContent nameKey="classification" />} />
      </PieChart>
    </ChartContainer>
  );
}

// ---------------------------------------------------------------------------
// Blocked vs allowed - compact two-slice donut
// ---------------------------------------------------------------------------

const BLOCKED_ALLOWED_CONFIG: ChartConfig = {
  count: { label: "Jobs" },
  allowed: { label: "Allowed", color: "#34c759" },
  blocked: { label: "Blocked", color: "#ff3b30" },
};

export function BlockedAllowedDonut({ allowed, blocked }: { allowed: number; blocked: number }) {
  const rows = [
    { key: "allowed", count: allowed },
    { key: "blocked", count: blocked },
  ].filter((r) => r.count > 0);
  const total = allowed + blocked;

  if (total === 0) return <EmptyState />;

  return (
    <ChartContainer config={BLOCKED_ALLOWED_CONFIG} className="mx-auto aspect-square max-h-[260px]">
      <PieChart>
        <ChartTooltip content={<ChartTooltipContent hideLabel />} />
        <Pie data={rows} dataKey="count" nameKey="key" innerRadius={62} outerRadius={92} strokeWidth={3} paddingAngle={2}>
          {rows.map((r) => (
            <Cell key={r.key} fill={`var(--color-${r.key})`} stroke="var(--card)" />
          ))}
          <Label
            content={({ viewBox }) => {
              if (!viewBox || !("cx" in viewBox) || !("cy" in viewBox)) return null;
              return (
                <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                  <tspan x={viewBox.cx} y={viewBox.cy} className="fill-foreground text-2xl font-bold">
                    {total.toLocaleString()}
                  </tspan>
                  <tspan x={viewBox.cx} y={(viewBox.cy ?? 0) + 20} className="fill-muted-foreground text-xs">
                    total
                  </tspan>
                </text>
              );
            }}
          />
        </Pie>
        <ChartLegend content={<ChartLegendContent nameKey="key" />} />
      </PieChart>
    </ChartContainer>
  );
}

// ---------------------------------------------------------------------------
// Risk score distribution - vertical bars, colored by severity band
// ---------------------------------------------------------------------------

const RISK_BAND_COLORS: Record<string, string> = {
  "0-20": "#34c759",
  "21-40": "#5ac8fa",
  "41-70": "#ff9f0a",
  "71-100": "#ff3b30",
};

const RISK_CONFIG: ChartConfig = { value: { label: "Documents" } };

export function RiskScoreBarChart({ data }: { data: Record<string, number> }) {
  const rows = Object.entries(data).map(([band, value]) => ({ band, value }));
  if (rows.every((r) => r.value === 0)) return <EmptyState />;

  return (
    <ChartContainer config={RISK_CONFIG} className="h-[260px] w-full">
      <BarChart data={rows} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="#ececf0" />
        <XAxis dataKey="band" tickLine={false} axisLine={false} tickMargin={8} />
        <YAxis tickLine={false} axisLine={false} tickMargin={8} allowDecimals={false} width={30} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="value" radius={[8, 8, 0, 0]} maxBarSize={56}>
          {rows.map((r) => (
            <Cell key={r.band} fill={RISK_BAND_COLORS[r.band] ?? "#0071e3"} />
          ))}
        </Bar>
      </BarChart>
    </ChartContainer>
  );
}

// ---------------------------------------------------------------------------
// Detections by category - horizontal bars, one hue per category
// ---------------------------------------------------------------------------

const CATEGORY_CONFIG: ChartConfig = { value: { label: "Detections" } };

export function CategoryBarChart({ data }: { data: { label: string; value: number }[] }) {
  if (data.length === 0) return <EmptyState />;

  return (
    <ChartContainer config={CATEGORY_CONFIG} className="h-[260px] w-full">
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid horizontal={false} stroke="#ececf0" />
        <XAxis type="number" tickLine={false} axisLine={false} allowDecimals={false} />
        <YAxis type="category" dataKey="label" tickLine={false} axisLine={false} width={110} tick={{ fontSize: 11 }} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="value" radius={[0, 6, 6, 0]}>
          {data.map((d, i) => (
            <Cell key={d.label} fill={CATEGORY_PALETTE[i % CATEGORY_PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ChartContainer>
  );
}

// ---------------------------------------------------------------------------
// Print jobs over time - gradient-filled area chart
// ---------------------------------------------------------------------------

const JOBS_OVER_TIME_CONFIG: ChartConfig = { count: { label: "Jobs", color: "#0071e3" } };

export function JobsOverTimeChart({ data }: { data: { date: string; count: number }[] }) {
  if (data.length === 0) return <EmptyState />;

  return (
    <ChartContainer config={JOBS_OVER_TIME_CONFIG} className="h-[220px] w-full">
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="fillJobsOverTime" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--color-count)" stopOpacity={0.35} />
            <stop offset="95%" stopColor="var(--color-count)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="#ececf0" />
        <XAxis
          dataKey="date"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          tickFormatter={(v: string) => v.slice(5)}
        />
        <YAxis tickLine={false} axisLine={false} tickMargin={8} allowDecimals={false} width={30} />
        <ChartTooltip content={<ChartTooltipContent indicator="line" />} />
        <Area dataKey="count" type="monotone" fill="url(#fillJobsOverTime)" stroke="var(--color-count)" strokeWidth={2} />
      </AreaChart>
    </ChartContainer>
  );
}
