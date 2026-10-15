"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

interface WatermarkConfig {
  text: string;
  opacity: number;
  font_size: number;
  angle: number;
}

interface Health {
  app: string;
  environment: string;
  database_ok: boolean;
  storage_incoming_writable: boolean;
  storage_sanitized_writable: boolean;
}

export default function SettingsPage() {
  const [wm, setWm] = useState<WatermarkConfig>({ text: "RESTRICTED", opacity: 0.1, font_size: 26, angle: 45 });
  const [health, setHealth] = useState<Health | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get<WatermarkConfig>("/api/v1/settings/watermark").then(setWm).catch(() => {});
    api.get<Health>("/api/v1/settings/health").then(setHealth).catch(() => {});
  }, []);

  async function save() {
    await api.patch("/api/v1/settings/watermark", wm);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <AppShell title="Settings" adminOnly>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Watermark Configuration</CardTitle>
            <CardDescription>Applied to every page of RESTRICTED documents</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="wm-text">Text</Label>
              <Input id="wm-text" value={wm.text} onChange={(e) => setWm({ ...wm, text: e.target.value })} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="wm-opacity">Opacity</Label>
                <Input
                  id="wm-opacity"
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={wm.opacity}
                  onChange={(e) => setWm({ ...wm, opacity: Number(e.target.value) })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="wm-font">Font Size</Label>
                <Input id="wm-font" type="number" value={wm.font_size} onChange={(e) => setWm({ ...wm, font_size: Number(e.target.value) })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="wm-angle">Angle</Label>
                <Input id="wm-angle" type="number" value={wm.angle} onChange={(e) => setWm({ ...wm, angle: Number(e.target.value) })} />
              </div>
            </div>
            <div className="flex items-center gap-3 pt-1">
              <Button onClick={save}>Save Watermark Settings</Button>
              {saved && <span className="text-sm text-emerald-600">Saved</span>}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>System Health</CardTitle>
          </CardHeader>
          <CardContent>
            {health ? (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Application</span>
                  <span>{health.app}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Environment</span>
                  <span>{health.environment}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Database</span>
                  <Badge variant={health.database_ok ? "default" : "destructive"}>{health.database_ok ? "Connected" : "Unavailable"}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Incoming Storage</span>
                  <Badge variant={health.storage_incoming_writable ? "default" : "destructive"}>
                    {health.storage_incoming_writable ? "OK" : "Missing"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Sanitized Storage</span>
                  <Badge variant={health.storage_sanitized_writable ? "default" : "destructive"}>
                    {health.storage_sanitized_writable ? "OK" : "Missing"}
                  </Badge>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Loading...</p>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
