"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarDays, Clock, MessageSquareQuote, Play, Search } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense } from "react";
import { MeetingMeta } from "@/components/result-card";
import { StatCard } from "@/components/stat-card";
import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { displayEmail, formatDate, formatDuration, formatTimestamp } from "@/lib/format";
import type { ParticipantDetail } from "@/lib/types";

function DetailSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-7 w-64" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-20" />)}
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function ParticipantView() {
  const { id } = useParams<{ id: string }>();
  const { data: p, isPending, error, refetch } = useQuery({
    queryKey: ["participant", Number(id)],
    queryFn: () => api.get<ParticipantDetail>(`/api/participants/${id}`),
  });

  if (isPending) return <DetailSkeleton />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const email = displayEmail(p.email);
  const shown = p.meetings.items.length;

  return (
    <div className="space-y-6">
      <Link href="/participants" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Participants
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">{p.name}</h1>
            <Badge variant="outline" className="font-normal">{p.is_internal ? "Team" : "External"}</Badge>
          </div>
          {email && <p className="text-sm text-muted-foreground">{email}</p>}
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href={`/search?participants=${p.id}`}><Search className="size-4" /> Search their meetings</Link>
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Meetings" value={p.meeting_count} icon={CalendarDays} />
        <StatCard label="Speaking time" value={p.speaking_sec} format={formatDuration} icon={Clock} />
        <StatCard label="First meeting" value={p.first_meeting_at ? 1 : null} format={() => formatDate(p.first_meeting_at, false)} />
        <StatCard label="Last meeting" value={p.last_meeting_at ? 1 : null} format={() => formatDate(p.last_meeting_at, false)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="text-sm">
              Meetings {p.meeting_count > shown && <span className="font-normal text-muted-foreground">· latest {shown} of {p.meeting_count}</span>}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {shown === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">No meetings.</p>
            ) : (
              p.meetings.items.map((m) => (
                <Link key={m.id} href={`/meetings/${m.id}`} className="block rounded-md px-2 py-2 hover:bg-muted/60">
                  <div className="truncate text-sm font-medium">{m.subject}</div>
                  <MeetingMeta m={m} />
                </Link>
              ))
            )}
            {p.meeting_count > shown && (
              <Link href={`/search?participants=${p.id}`} className="block px-2 pt-2 text-sm text-muted-foreground hover:text-foreground">
                See all {p.meeting_count.toLocaleString()} meetings →
              </Link>
            )}
          </CardContent>
        </Card>

        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="text-sm">Mentioned by others</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {p.mentions.length === 0 ? (
              <EmptyState icon={MessageSquareQuote} title="No mentions found"
                          description={`No one else said “${p.name.split(" ")[0]}” in meetings you can see.`} />
            ) : (
              p.mentions.map((x) => (
                <Link
                  key={x.segment_id}
                  href={x.start_sec != null ? `/meetings/${x.meeting_id}?t=${Math.floor(x.start_sec)}` : `/meetings/${x.meeting_id}?tab=notes`}
                  className="flex gap-3 rounded-md px-2 py-2 hover:bg-muted/60"
                >
                  <span className="mt-0.5 inline-flex h-6 shrink-0 items-center gap-1 rounded border bg-background px-1.5 font-mono text-[11px] text-muted-foreground">
                    <Play className="size-3" /> {x.start_sec != null ? formatTimestamp(x.start_sec) : "Notes"}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-xs text-muted-foreground">
                      {x.speaker_name ?? "Notes"} · {x.subject} · {formatDate(x.start_at, false)}
                    </span>
                    <span className="line-clamp-2 text-sm">{x.text}</span>
                  </span>
                </Link>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function ParticipantPage() {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <ParticipantView />
    </Suspense>
  );
}
