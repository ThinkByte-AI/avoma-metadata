"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock, FileText, HardDrive, Mic, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChartCard, ColumnChart, RankedBars, TrendLine, dayLabel, monthLabel } from "@/components/charts/charts";
import { MeetingMeta } from "@/components/result-card";
import { StatCard } from "@/components/stat-card";
import { ErrorState, PageHeader } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { DashboardStats } from "@/lib/types";

const hours = (sec: number) => `${Math.round(sec / 3600).toLocaleString()} h`;

export default function OverviewPage() {
  const router = useRouter();
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.get<DashboardStats>("/api/dashboard/stats"),
  });

  if (error) {
    return (
      <>
        <PageHeader title="Overview" />
        <ErrorState error={error} onRetry={() => refetch()} />
      </>
    );
  }

  const loading = isPending;
  const months = (data?.meetings_by_month ?? []).map((m) => ({ label: m.month, value: m.count }));
  const people = (data?.top_participants ?? []).map((p) => ({ label: p.name, value: p.count, key: p.id }));
  const topics = (data?.top_topics ?? []).map((t) => ({ label: t.topic, value: t.count }));
  const activity = (data?.search_activity ?? []).map((d) => ({ label: d.date, value: d.count }));
  const searches30d = activity.reduce((s, d) => s + d.value, 0);

  return (
    <div className="space-y-6">
      <PageHeader title="Overview" description="Your meeting archive at a glance." />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Meetings" value={data?.total_meetings} icon={CalendarDays} loading={loading} />
        <StatCard label="Recordings" value={data?.total_recordings} icon={Mic} loading={loading} />
        <StatCard label="Participants" value={data?.total_participants} icon={Users} loading={loading} />
        <StatCard label="Transcripts" value={data?.total_transcripts} icon={FileText} loading={loading} />
        <StatCard label="Audio storage" value={data?.audio_storage_bytes} format={formatBytes} icon={HardDrive} loading={loading}
                  hint={data ? `+ ${formatBytes(data.video_storage_bytes)} video` : undefined} />
        <StatCard label="Total duration" value={data?.total_duration_sec} format={hours} icon={Clock} loading={loading} />
      </div>

      <ChartCard title="Meetings by month" description="Number of meetings held each month" loading={loading} empty={!months.length}>
        <ColumnChart data={months} valueName="Meetings" unit="Meetings" labelFormat={monthLabel} />
      </ChartCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Most frequent participants" description="Meetings attended · click a bar to open the person"
                   loading={loading} empty={!people.length}>
          <RankedBars data={people} valueName="Meetings" unit="Meetings attended"
                      onSelect={(id) => router.push(`/participants/${id}`)} />
        </ChartCard>
        <ChartCard title="Most discussed topics" description="Meetings whose notes cover the topic" loading={loading} empty={!topics.length}
                   emptyText="Topics appear once meeting notes are ingested.">
          <RankedBars data={topics} valueName="Meetings" unit="Meetings" />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <ChartCard title="Search activity" description={data ? `${searches30d.toLocaleString()} searches in the last 30 days` : undefined}
                   loading={loading} empty={!activity.length}>
          <TrendLine data={activity} valueName="Searches" unit="Searches" labelFormat={dayLabel} />
        </ChartCard>
        <Card className="gap-3">
          <CardHeader><CardTitle className="text-sm">Recent meetings</CardTitle></CardHeader>
          <CardContent className="space-y-1">
            {loading
              ? Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-10 w-full" />)
              : data?.recent_meetings.length
                ? data.recent_meetings.map((m) => (
                    <Link key={m.id} href={`/meetings/${m.id}`} className="block rounded-md px-2 py-2 hover:bg-muted/60">
                      <div className="truncate text-sm font-medium">{m.subject}</div>
                      <MeetingMeta m={m} />
                    </Link>
                  ))
                : <p className="py-6 text-center text-sm text-muted-foreground">No meetings yet.</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
