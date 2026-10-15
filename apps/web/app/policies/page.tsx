"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, CardTitle, CardAction, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ClassificationBadge } from "@/components/status-badges";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Policy } from "@/types";

const FLAGS: { key: keyof Policy; label: string }[] = [
  { key: "require_alert", label: "Require Alert" },
  { key: "require_masking", label: "Require Masking" },
  { key: "require_watermark", label: "Require Watermark" },
  { key: "require_footer", label: "Require Footer" },
  { key: "allow_printing", label: "Allow Printing" },
];

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);

  function load() {
    api.get<Policy[]>("/api/v1/policies").then(setPolicies).catch(() => {});
  }
  useEffect(load, []);

  // Each change saves on its own, so say whether it reached the server.
  async function save(p: Policy, change: Partial<Policy>, what: string) {
    try {
      await api.patch(`/api/v1/policies/${p.id}`, change);
      toast.success(`${p.classification}: ${what} saved`);
    } catch (err) {
      toast.error(`${p.classification}: ${what} was not saved`, {
        description: err instanceof ApiError ? err.message : "The server could not be reached.",
      });
    }
    load();
  }

  function updateFlag(p: Policy, key: keyof Policy, label: string, value: boolean) {
    save(p, { [key]: value }, `${label} ${value ? "on" : "off"}`);
  }

  function updateScore(p: Policy, key: "min_score" | "max_score", value: number) {
    if (value === p[key]) return;
    save(p, { [key]: value }, `${key === "min_score" ? "Min" : "Max"} Score ${value}`);
  }

  return (
    <AppShell title="Security Policies" adminOnly>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        {policies.map((p) => (
          <Card key={p.id}>
            <CardHeader>
              <CardTitle>{p.classification}</CardTitle>
              <CardAction>
                <ClassificationBadge value={p.classification} />
              </CardAction>
            </CardHeader>
            <CardContent>
              <div className="mb-4 flex items-center gap-3 text-sm">
                <Label htmlFor={`min-${p.id}`} className="text-xs text-muted-foreground">
                  Min Score
                </Label>
                <Input
                  id={`min-${p.id}`}
                  type="number"
                  defaultValue={p.min_score}
                  onBlur={(e) => updateScore(p, "min_score", Number(e.target.value))}
                  className="w-16 text-right"
                />
                <Label htmlFor={`max-${p.id}`} className="text-xs text-muted-foreground">
                  Max Score
                </Label>
                <Input
                  id={`max-${p.id}`}
                  type="number"
                  defaultValue={p.max_score}
                  onBlur={(e) => updateScore(p, "max_score", Number(e.target.value))}
                  className="w-16 text-right"
                />
              </div>
              <div className="space-y-1">
                {FLAGS.map((f) => (
                  <div key={f.key} className="flex items-center justify-between border-b py-2 text-sm last:border-0">
                    <Label htmlFor={`${f.key}-${p.id}`} className="font-normal">
                      {f.label}
                    </Label>
                    <Switch
                      id={`${f.key}-${p.id}`}
                      checked={Boolean(p[f.key])}
                      onCheckedChange={(checked) => updateFlag(p, f.key, f.label, checked)}
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
