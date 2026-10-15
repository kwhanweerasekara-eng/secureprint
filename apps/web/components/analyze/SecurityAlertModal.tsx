"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { RiskMeter } from "@/components/ui/RiskMeter";
import { ClassificationBadge } from "@/components/status-badges";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { categoryLabel } from "@/lib/utils";
import type { DetectionSummary } from "@/types";

export function SecurityAlertModal({
  riskScore,
  classification,
  detections,
  busy,
  onCancel,
  onMask,
}: {
  riskScore: number;
  classification: string;
  detections: DetectionSummary[];
  busy: boolean;
  onCancel: () => void;
  onMask: () => void;
}) {
  const severe = classification === "RESTRICTED";

  return (
    <Dialog open onOpenChange={() => {}}>
      <DialogContent showCloseButton={false} className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <span className={`flex h-8 w-8 items-center justify-center rounded-full ${severe ? "bg-destructive/10 text-destructive" : "bg-amber-500/10 text-amber-600"}`}>
              <AlertTriangle size={17} />
            </span>
            <DialogTitle>SecurePrint Security Alert</DialogTitle>
          </div>
          <DialogDescription>
            Sensitive information was detected in this document. Printing the original document may expose
            sensitive information.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">Risk Score</p>
            <RiskMeter score={riskScore} />
          </div>

          <div className="flex items-center gap-2">
            <p className="text-xs font-medium text-muted-foreground">Classification</p>
            <ClassificationBadge value={classification} />
          </div>

          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">Detected</p>
            <div className="space-y-1.5">
              {detections.map((d) => (
                <div key={d.category} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{categoryLabel(d.category)}</span>
                  <span className="font-semibold tabular-nums">{d.count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" className="flex-1" onClick={onCancel} disabled={busy}>
            Cancel Print
          </Button>
          <Button variant={severe ? "destructive" : "default"} className="flex-1" onClick={onMask} disabled={busy}>
            {busy ? "Processing…" : "Mask & Continue"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
