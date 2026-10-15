import { Progress as ProgressPrimitive } from "@base-ui/react/progress";
import { cn } from "@/lib/utils";

const bandStyles = {
  restricted: { track: "bg-red-500/15", fill: "bg-red-600", text: "text-red-600" },
  confidential: { track: "bg-amber-500/15", fill: "bg-amber-500", text: "text-amber-600" },
  internal: { track: "bg-sky-500/15", fill: "bg-sky-500", text: "text-sky-600" },
  public: { track: "bg-emerald-500/15", fill: "bg-emerald-600", text: "text-emerald-600" },
};

function bandFor(score: number) {
  if (score >= 71) return bandStyles.restricted;
  if (score >= 41) return bandStyles.confidential;
  if (score >= 21) return bandStyles.internal;
  return bandStyles.public;
}

export function RiskMeter({ score, size = "md" }: { score: number; size?: "sm" | "md" | "lg" }) {
  const clamped = Math.min(100, Math.max(0, score));
  const band = bandFor(clamped);
  const heights = { sm: "h-1.5", md: "h-2", lg: "h-2.5" };

  return (
    <ProgressPrimitive.Root value={clamped} className="flex w-full items-center gap-3">
      <ProgressPrimitive.Track className={cn("relative w-full overflow-hidden rounded-full", band.track, heights[size])}>
        <ProgressPrimitive.Indicator className={cn("h-full rounded-full transition-all duration-300", band.fill)} />
      </ProgressPrimitive.Track>
      <span className={cn("shrink-0 text-sm font-semibold tabular-nums", band.text)}>{clamped}/100</span>
    </ProgressPrimitive.Root>
  );
}
