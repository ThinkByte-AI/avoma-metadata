import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function StatCard({
  label,
  value,
  format = (n) => n.toLocaleString(),
  icon: Icon,
  hint,
  loading = false,
}: {
  label: string;
  value: number | undefined | null;
  format?: (n: number) => string;
  icon?: LucideIcon;
  hint?: string;
  loading?: boolean;
}) {
  return (
    <Card className="gap-0 py-0">
      <CardContent className="space-y-1.5 p-4">
        <div className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
          <span>{label}</span>
          {Icon && <Icon className="size-4" aria-hidden />}
        </div>
        {loading ? (
          <Skeleton className="h-7 w-24" />
        ) : (
          <div className="text-2xl font-semibold tracking-tight tabular-nums">
            {value === undefined || value === null ? "—" : format(value)}
          </div>
        )}
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}
