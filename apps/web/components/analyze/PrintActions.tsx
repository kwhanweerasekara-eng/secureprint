"use client";

import { useEffect, useState } from "react";
import { Download, Printer as PrinterIcon, Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import { openAndPrint } from "@/lib/printing";
import type { Printer } from "@/types";

export function PrintActions({ jobId, onPrinted }: { jobId: string; onPrinted?: () => void }) {
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Printer[]>("/api/v1/printers")
      .then(setPrinters)
      .catch(() => {});
  }, []);

  async function printViaBrowser() {
    await api.post(`/api/v1/jobs/${jobId}/print`);
    openAndPrint(api.fileUrl(`/api/v1/jobs/${jobId}/document`));
    onPrinted?.();
  }

  async function sendToPrinter() {
    if (!selected) return;
    setSending(true);
    setError(null);
    try {
      await api.post(`/api/v1/jobs/${jobId}/print`, { printer_id: selected });
      onPrinted?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delivery to printer failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        <a href={api.fileUrl(`/api/v1/jobs/${jobId}/document?download=1`)} download={`${jobId}_sanitized.pdf`}>
          <Button variant="outline">
            <Download /> Download
          </Button>
        </a>
        <Button onClick={printViaBrowser}>
          <PrinterIcon /> Print via Browser
        </Button>
      </div>

      {printers.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-t pt-3">
          <span className="text-xs text-muted-foreground">or send directly to a network printer:</span>
          <Select value={selected} onValueChange={(v) => setSelected(v ?? "")}>
            <SelectTrigger className="w-[220px]">
              <SelectValue placeholder="Choose a printer" />
            </SelectTrigger>
            <SelectContent>
              {printers.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name} ({p.protocol} &middot; {p.host})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={sendToPrinter} disabled={!selected || sending}>
            {sending ? <Loader2 className="animate-spin" /> : <Send />}
            Send
          </Button>
        </div>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
