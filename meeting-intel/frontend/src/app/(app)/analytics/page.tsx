"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ChartCard, ColumnChart, MultiLineChart, RankedBars, monthLabel } from "@/components/charts/charts";
import { ErrorState, PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, qs } from "@/lib/api";
import type { Analytics } from "@/lib/types";

const hrs = (n: number) => `${n.toLocaleString(undefined, { maximumFractionDigits: 1 })} h`;

export default function AnalyticsPage() {
  const router = useRouter();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const params = { date_from: from || undefined, date_to: to || undefined };
  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ["analytics", params],
    queryFn: () => api.get<Analytics>(`/api/analytics${qs(params)}`),
    placeholderData: keepPreviousData,
  });

  const topicSeries = useMemo(() => {
    const rows = data?.topics_by_month ?? [];
    const totals = new Map<string, number>();
    for (const r of rows) totals.set(r.topic, (totals.get(r.topic) ?? 0) + r.count);
    const series = [...totals.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([t]) => t);
    const byMonth = new Map<string, Record<string, string | number>>();
    for (const r of rows) {
      const row = byMonth.get(r.month) ?? { month: r.month };
      row[r.topic] = r.count;
      byMonth.set(r.month, row);
    }
    const table = [...byMonth.values()].sort((a, b) => String(a.month).localeCompare(String(b.month)));
    for (const row of table) for (const s of series) row[s] ??= 0;
    return { series, table };
  }, [data]);

  const loading = isPending;
  const iv = data?.internal_vs_external_speaking;
  const totalTalk = iv ? iv.internal_hours + iv.external_hours : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Trends across the meetings you can access."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-8 w-40" aria-label="From date" />
            <span className="text-sm text-muted-foreground">to</span>
            <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-8 w-40" aria-label="To date" />
            {(from || to) && (
              <Button variant="ghost" size="sm" onClick={() => { setFrom(""); setTo(""); }}>Clear</Button>
            )}
          </div>
        }
      />
      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <div className={isFetching && !loading ? "space-y-4 opacity-70 transition-opacity" : "space-y-4"}>
          <ChartCard title="Meeting hours by month" description="Total scheduled meeting time" loading={loading}
                     empty={!data?.hours_by_month.length}>
            <ColumnChart data={(data?.hours_by_month ?? []).map((m) => ({ label: m.month, value: m.hours }))}
                         valueName="Hours" unit="Hours" format={hrs} labelFormat={monthLabel} />
          </ChartCard>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Meetings by owner" description="Avoma account that recorded the meeting" loading={loading}
                       empty={!data?.meetings_by_owner.length}>
              <RankedBars data={(data?.meetings_by_owner ?? []).slice(0, 15).map((o) => ({ label: o.owner, value: o.count }))}
                          valueName="Meetings" unit="Meetings" />
            </ChartCard>
            <ChartCard title="Who talks the most" description="Total speaking time · click a bar to open the person"
                       loading={loading} empty={!data?.speaking_leaders.length}>
              <RankedBars
                data={(data?.speaking_leaders ?? []).map((p) => ({ label: p.name, value: Math.round(p.hours * 10) / 10, key: p.participant_id }))}
                valueName="Speaking time" unit="Hours spoken" format={hrs}
                onSelect={(id) => router.push(`/participants/${id}`)}
              />
            </ChartCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <ChartCard title="Topics over time" description="Meetings per month for the most discussed topics" loading={loading}
                       empty={!topicSeries.series.length} emptyText="Topics appear once meeting notes are ingested.">
              <MultiLineChart rows={topicSeries.table} series={topicSeries.series} unit="Meetings" labelFormat={monthLabel} />
            </ChartCard>
            <Card className="gap-3">
              <CardHeader><CardTitle className="text-sm">Team vs external speaking</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                {loading || !iv ? (
                  <Skeleton className="h-24 w-full" />
                ) : (
                  <>
                    <div>
                      <div className="text-xs text-muted-foreground">Team</div>
                      <div className="text-2xl font-semibold tabular-nums">{hrs(iv.internal_hours)}</div>
                      {totalTalk > 0 && <div className="text-xs text-muted-foreground">{Math.round((iv.internal_hours / totalTalk) * 100)}% of speaking time</div>}
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">External (clients, guests)</div>
                      <div className="text-2xl font-semibold tabular-nums">{hrs(iv.external_hours)}</div>
                      {totalTalk > 0 && <div className="text-xs text-muted-foreground">{Math.round((iv.external_hours / totalTalk) * 100)}% of speaking time</div>}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
