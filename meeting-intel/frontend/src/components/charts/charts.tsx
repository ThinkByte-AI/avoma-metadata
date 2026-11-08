"use client";

// Small Recharts wrappers that follow the dataviz rules used across the app:
// one hue per single-series chart (categorical slot 1), thin marks with 4px rounded data-ends
// anchored to the baseline, recessive axes/grid, hover tooltip on every mark, and a legend +
// table view for multi-series charts (several light-mode slots sit below 3:1 contrast).
import { Table2, BarChart3 } from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
  type TooltipValueType,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

// Reference palette, categorical slots 1-6 (validated light + dark, adjacent pairs).
// Light and dark steps are selected per mode, not flipped.
export const VIZ_VARS = cn(
  "[--series-1:#2a78d6] [--series-2:#eb6834] [--series-3:#1baf7a] [--series-4:#eda100] [--series-5:#e87ba4] [--series-6:#008300]",
  "dark:[--series-1:#3987e5] dark:[--series-2:#d95926] dark:[--series-3:#199e70] dark:[--series-4:#c98500] dark:[--series-5:#d55181] dark:[--series-6:#008300]",
);
export const SERIES = [1, 2, 3, 4, 5, 6].map((i) => `var(--series-${i})`);

const AXIS_TICK = { fill: "var(--muted-foreground)", fontSize: 11 };
const AXIS_LABEL = { fill: "var(--muted-foreground)", fontSize: 11 };

export function ChartCard({
  title,
  description,
  loading,
  empty,
  emptyText = "No data for this period yet.",
  action,
  children,
  className,
}: {
  title: string;
  description?: string;
  loading?: boolean;
  empty?: boolean;
  emptyText?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("gap-3", className)}>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
        <div className="space-y-1">
          <CardTitle className="text-sm">{title}</CardTitle>
          {description && <CardDescription className="text-xs">{description}</CardDescription>}
        </div>
        {action}
      </CardHeader>
      <CardContent className={VIZ_VARS}>
        {loading ? (
          <Skeleton className="h-56 w-full" />
        ) : empty ? (
          <div className="flex h-40 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
            {emptyText}
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

function TooltipBox({ title, rows }: { title?: ReactNode; rows: { color?: string; name: ReactNode; value: ReactNode }[] }) {
  return (
    <div className="rounded-md border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md">
      {title && <div className="mb-1 font-medium">{title}</div>}
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          {r.color && <span className="size-2 shrink-0 rounded-full" style={{ background: r.color }} aria-hidden />}
          <span className="text-muted-foreground">{r.name}</span>
          <span className="ml-auto pl-3 font-medium tabular-nums">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

function makeTooltip(valueName: string, format: (n: number) => string, labelFormat?: (l: string) => string) {
  return function ChartTooltip({ active, payload, label }: TooltipContentProps<TooltipValueType, string | number>) {
    if (!active || !payload?.length) return null;
    return (
      <TooltipBox
        title={labelFormat ? labelFormat(String(label)) : String(label)}
        rows={payload.map((p) => ({
          color: payload.length > 1 ? (p.color as string) : undefined,
          name: payload.length > 1 ? p.name : valueName,
          value: format(Number(p.value)),
        }))}
      />
    );
  };
}

/** One measure over ordered categories (months, days): vertical bars. */
export function ColumnChart({
  data,
  valueName,
  unit,
  format = (n) => n.toLocaleString(),
  labelFormat,
  height = 240,
}: {
  data: { label: string; value: number }[];
  valueName: string;
  unit: string;
  format?: (n: number) => string;
  labelFormat?: (l: string) => string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={labelFormat}
               interval="preserveStartEnd" minTickGap={12} />
        <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={44} allowDecimals={false}
               label={{ value: unit, angle: -90, position: "insideLeft", style: AXIS_LABEL, offset: 0 }} />
        <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.6 }} content={makeTooltip(valueName, format, labelFormat)} />
        <Bar dataKey="value" name={valueName} fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={36} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** One measure across named items, ranked: horizontal bars. */
export function RankedBars({
  data,
  valueName,
  unit,
  format = (n) => n.toLocaleString(),
  onSelect,
}: {
  data: { label: string; value: number; key?: string | number }[];
  valueName: string;
  unit: string;
  format?: (n: number) => string;
  onSelect?: (key: string | number) => void;
}) {
  const height = Math.max(120, data.length * 28 + 36);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 16, left: 0 }} barCategoryGap={2}>
        <CartesianGrid horizontal={false} stroke="var(--border)" />
        <XAxis type="number" tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false}
               label={{ value: unit, position: "insideBottom", offset: -10, style: AXIS_LABEL }} />
        <YAxis type="category" dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} width={150}
               tickFormatter={(v: string) => (v.length > 22 ? `${v.slice(0, 21)}…` : v)} />
        <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.6 }} content={makeTooltip(valueName, format)} />
        <Bar
          dataKey="value"
          name={valueName}
          fill={SERIES[0]}
          radius={[0, 4, 4, 0]}
          maxBarSize={18}
          className={onSelect ? "cursor-pointer" : undefined}
          onClick={onSelect ? (d: { payload?: { key?: string | number } }) => d.payload?.key !== undefined && onSelect(d.payload.key) : undefined}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** One measure over time: a 2px line with a hover crosshair. */
export function TrendLine({
  data,
  valueName,
  unit,
  labelFormat,
  height = 200,
}: {
  data: { label: string; value: number }[];
  valueName: string;
  unit: string;
  labelFormat?: (l: string) => string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={labelFormat}
               interval="preserveStartEnd" minTickGap={24} />
        <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={44} allowDecimals={false}
               label={{ value: unit, angle: -90, position: "insideLeft", style: AXIS_LABEL, offset: 0 }} />
        <Tooltip cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }}
                 content={makeTooltip(valueName, (n) => n.toLocaleString(), labelFormat)} />
        <Line type="monotone" dataKey="value" name={valueName} stroke={SERIES[0]} strokeWidth={2} dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Up to six series over the same months. Legend always; table view for exact values. */
export function MultiLineChart({
  rows,
  series,
  unit,
  labelFormat,
}: {
  rows: Record<string, string | number>[];
  series: string[];
  unit: string;
  labelFormat?: (l: string) => string;
}) {
  const [asTable, setAsTable] = useState(false);
  const shown = series.slice(0, SERIES.length);
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setAsTable((t) => !t)}>
          {asTable ? <BarChart3 className="size-3.5" /> : <Table2 className="size-3.5" />}
          {asTable ? "Chart view" : "Table view"}
        </Button>
      </div>
      {asTable ? (
        <div className="max-h-72 overflow-auto rounded-md border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-muted">
              <tr>
                <th className="px-2 py-1.5 text-left font-medium">Month</th>
                {shown.map((s) => <th key={s} className="px-2 py-1.5 text-right font-medium">{s}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={String(r.month)} className="border-t">
                  <td className="px-2 py-1">{labelFormat ? labelFormat(String(r.month)) : String(r.month)}</td>
                  {shown.map((s) => <td key={s} className="px-2 py-1 text-right tabular-nums">{Number(r[s] ?? 0)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="month" tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={labelFormat}
                   interval="preserveStartEnd" minTickGap={16} />
            <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={44} allowDecimals={false}
                   label={{ value: unit, angle: -90, position: "insideLeft", style: AXIS_LABEL, offset: 0 }} />
            <Tooltip cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }}
                     content={makeTooltip(unit, (n) => n.toLocaleString(), labelFormat)} />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 11, color: "var(--muted-foreground)" }} />
            {shown.map((s, i) => (
              <Line key={s} type="monotone" dataKey={s} name={s} stroke={SERIES[i]} strokeWidth={2} dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

/** "2025-02" → "Feb 2025" */
export function monthLabel(m: string): string {
  const [y, mo] = m.split("-").map(Number);
  if (!y || !mo) return m;
  return new Date(Date.UTC(y, mo - 1, 1)).toLocaleDateString(undefined, { month: "short", year: "numeric", timeZone: "UTC" });
}

/** "2026-11-08" → "8 Nov" */
export function dayLabel(d: string): string {
  const dt = new Date(`${d}T00:00:00Z`);
  return Number.isNaN(dt.getTime()) ? d : dt.toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
}
