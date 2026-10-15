import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const toneText: Record<string, string> = {
  default: "text-foreground",
  danger: "text-[#e30000]",
  warning: "text-[#b25000]",
  success: "text-[#248a3d]",
};

export function StatCard({
  label,
  value,
  icon,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  tone?: "default" | "danger" | "warning" | "success";
}) {
  return (
    <Card size="sm" className="[--card-spacing:--spacing(5)]">
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center justify-between text-muted-foreground">
          <p className="text-[13px] font-medium">{label}</p>
          {icon && <span className="[&_svg]:size-4">{icon}</span>}
        </div>
        <p className={cn("text-[40px] leading-none font-medium tracking-[-0.03em] tabular-nums", toneText[tone])}>
          {value}
        </p>
      </CardContent>
    </Card>
  );
}
