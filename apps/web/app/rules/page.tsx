"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import type { DetectionRule, Keyword, RiskWeight } from "@/types";

export default function RulesPage() {
  const [rules, setRules] = useState<DetectionRule[]>([]);
  const [keywords, setKeywords] = useState<Keyword[]>([]);
  const [weights, setWeights] = useState<RiskWeight[]>([]);
  const [newKeyword, setNewKeyword] = useState({ category: "credential", term: "" });

  function loadAll() {
    api.get<DetectionRule[]>("/api/v1/rules").then(setRules).catch(() => {});
    api.get<Keyword[]>("/api/v1/rules/keywords/all").then(setKeywords).catch(() => {});
    api.get<RiskWeight[]>("/api/v1/rules/weights/all").then(setWeights).catch(() => {});
  }

  useEffect(loadAll, []);

  async function toggleRule(rule: DetectionRule) {
    await api.patch(`/api/v1/rules/${rule.id}`, { enabled: !rule.enabled });
    loadAll();
  }

  async function deleteKeyword(id: string) {
    await api.del(`/api/v1/rules/keywords/${id}`);
    loadAll();
  }

  async function addKeyword() {
    if (!newKeyword.term.trim()) return;
    await api.post("/api/v1/rules/keywords", newKeyword);
    setNewKeyword({ ...newKeyword, term: "" });
    loadAll();
  }

  async function updateWeight(w: RiskWeight, weight: number) {
    await api.patch(`/api/v1/rules/weights/${w.id}`, { weight });
    loadAll();
  }

  async function toggleWeight(w: RiskWeight) {
    await api.patch(`/api/v1/rules/weights/${w.id}`, { enabled: !w.enabled });
    loadAll();
  }

  return (
    <AppShell title="Detection Rules" adminOnly>
      <Tabs defaultValue="rules">
        <TabsList className="mb-5">
          <TabsTrigger value="rules">Regex Rules</TabsTrigger>
          <TabsTrigger value="keywords">Keywords</TabsTrigger>
          <TabsTrigger value="weights">Risk Weights</TabsTrigger>
        </TabsList>

        <TabsContent value="rules">
          <Card>
            <CardHeader>
              <CardTitle>Regex Detection Rules</CardTitle>
              <CardDescription>{rules.length} rules configured</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {rules.map((r) => (
                <div key={r.id} className="flex items-center justify-between rounded-lg border px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{r.name}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Category: {r.category} &middot; Priority: {r.priority}
                    </p>
                    <code className="mt-1 inline-block rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                      {r.pattern}
                    </code>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant={r.enabled ? "default" : "secondary"}>{r.enabled ? "Enabled" : "Disabled"}</Badge>
                    <Button size="sm" variant="outline" onClick={() => toggleRule(r)}>
                      {r.enabled ? "Disable" : "Enable"}
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="keywords">
          <Card>
            <CardHeader>
              <CardTitle>Keyword Dictionary</CardTitle>
              <CardDescription>{keywords.length} keywords configured</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-4 flex gap-2">
                <Select value={newKeyword.category} onValueChange={(v) => setNewKeyword({ ...newKeyword, category: v ?? "credential" })}>
                  <SelectTrigger className="w-[190px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["credential", "api_key", "salary", "classification_marker", "employee_id", "bank_account", "iban", "passport"].map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={newKeyword.term}
                  onChange={(e) => setNewKeyword({ ...newKeyword, term: e.target.value })}
                  placeholder="new keyword"
                  className="flex-1"
                />
                <Button size="sm" onClick={addKeyword}>
                  <Plus /> Add
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                {keywords.map((k) => (
                  <div key={k.id} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
                    <div>
                      <p>{k.term}</p>
                      <p className="text-[11px] text-muted-foreground">{k.category}</p>
                    </div>
                    <button onClick={() => deleteKeyword(k.id)} className="text-muted-foreground/50 hover:text-destructive">
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="weights">
          <Card>
            <CardHeader>
              <CardTitle>Risk Weights</CardTitle>
              <CardDescription>Contribution to risk score per distinct category</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {weights.map((w) => (
                <div key={w.id} className="flex items-center justify-between rounded-lg border px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{w.label}</p>
                    <p className="text-xs text-muted-foreground">{w.category}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      defaultValue={w.weight}
                      onBlur={(e) => updateWeight(w, Number(e.target.value))}
                      className="w-20 text-right"
                    />
                    <Button size="sm" variant="outline" onClick={() => toggleWeight(w)}>
                      {w.enabled ? "Disable" : "Enable"}
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}
