"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, Printer as PrinterIcon, Wifi, Radio, Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/status-badges";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type { Printer, PrinterProtocol } from "@/types";

const STATUS_DOT: Record<string, string> = {
  ONLINE: "bg-emerald-500",
  OFFLINE: "bg-destructive",
  UNKNOWN: "bg-amber-400",
};

const DEFAULT_PORT: Record<PrinterProtocol, number> = { IPP: 631, SOCKET: 9100 };

export default function PrintersPage() {
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [form, setForm] = useState({
    name: "",
    location: "",
    protocol: "IPP" as PrinterProtocol,
    host: "",
    port: 631,
    ipp_path: "/ipp/print",
    use_tls: false,
  });
  const [error, setError] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);

  function load() {
    api.get<Printer[]>("/api/v1/printers").then(setPrinters).catch(() => {});
  }
  useEffect(load, []);

  async function createPrinter() {
    if (!form.name.trim() || !form.host.trim()) return;
    setError(null);
    try {
      await api.post("/api/v1/printers", form);
      setForm({ name: "", location: "", protocol: "IPP", host: "", port: 631, ipp_path: "/ipp/print", use_tls: false });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add printer");
    }
  }

  async function testPrinter(p: Printer) {
    setTestingId(p.id);
    try {
      await api.post(`/api/v1/printers/${p.id}/test`);
    } finally {
      setTestingId(null);
      load();
    }
  }

  async function remove(p: Printer) {
    await api.del(`/api/v1/printers/${p.id}`);
    load();
  }

  return (
    <AppShell title="Printers" adminOnly>
      <Card className="mb-5">
        <CardContent className="flex gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Wifi size={17} />
          </span>
          <div>
            <p className="text-sm font-semibold">Direct network printing — no agent required</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              SecurePrint talks to your printers itself, over IPP or raw AppSocket (port 9100), the same way any
              managed print server does. Register a printer&apos;s network address below and the backend delivers
              sanitized documents straight to it — nothing to install anywhere else.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Add a Printer</CardTitle>
          <CardDescription>Connect a real network printer by its IP address or hostname</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Display name</Label>
              <Input placeholder="Office Printer" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Location</Label>
              <Input placeholder="3rd floor" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Protocol</Label>
              <Select
                value={form.protocol}
                onValueChange={(v) => {
                  const protocol = (v as PrinterProtocol) ?? "IPP";
                  setForm({ ...form, protocol, port: DEFAULT_PORT[protocol] });
                }}
              >
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="IPP">IPP</SelectItem>
                  <SelectItem value="SOCKET">Raw Socket (9100)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Host / IP address</Label>
              <Input placeholder="192.168.1.50" value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} className="w-[160px]" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Port</Label>
              <Input
                type="number"
                value={form.port}
                onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
                className="w-[90px]"
              />
            </div>
            {form.protocol === "IPP" && (
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">IPP path</Label>
                <Input value={form.ipp_path} onChange={(e) => setForm({ ...form, ipp_path: e.target.value })} className="w-[140px]" />
              </div>
            )}
            {form.protocol === "IPP" && (
              <div className="flex items-center gap-2 pb-2">
                <Switch checked={form.use_tls} onCheckedChange={(checked) => setForm({ ...form, use_tls: checked })} />
                <Label className="text-xs text-muted-foreground">TLS (ipps://)</Label>
              </div>
            )}
            <Button size="sm" onClick={createPrinter}>
              <Plus /> Add Printer
            </Button>
          </div>
          {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Registered Printers</CardTitle>
          <CardDescription>{printers.length} printer(s)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {printers.map((p) => (
            <div key={p.id} className="flex items-center justify-between rounded-lg border px-4 py-3 transition-colors hover:bg-muted/40">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <PrinterIcon size={16} />
                </span>
                <div>
                  <p className="text-sm font-medium">{p.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {p.location || "No location"} &middot; {p.protocol} &middot; {p.host}:{p.port}
                    {p.protocol === "IPP" ? p.ipp_path : ""}
                  </p>
                  {p.last_test_message && (
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      Last test ({formatDateTime(p.last_tested_at!)}): {p.last_test_message}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className={`h-2 w-2 rounded-full ${STATUS_DOT[p.status]}`} />
                  <StatusBadge value={p.status} />
                </span>
                <Button size="sm" variant="outline" onClick={() => testPrinter(p)} disabled={testingId === p.id}>
                  {testingId === p.id ? <Loader2 className="animate-spin" /> : <Radio />}
                  Test Connection
                </Button>
                <button onClick={() => remove(p)} className="text-muted-foreground/50 hover:text-destructive">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          {printers.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No printers registered yet. Add one above by its network address.
            </p>
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}
