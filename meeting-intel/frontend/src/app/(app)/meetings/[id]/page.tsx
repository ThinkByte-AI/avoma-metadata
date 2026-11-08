"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Copy, FileText, NotebookText } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { AudioPlayer, type AudioPlayerHandle } from "@/components/audio-player";
import { NotesMarkdown } from "@/components/notes-markdown";
import { VideoDownloadButton } from "@/components/recording-download";
import { AvailabilityBadges } from "@/components/result-card";
import { EmptyState, ErrorState } from "@/components/states";
import { TranscriptViewer } from "@/components/transcript-viewer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMe } from "@/hooks/use-me";
import { api } from "@/lib/api";
import { displayEmail, formatDate, formatDuration } from "@/lib/format";
import { findActiveSegment } from "@/lib/transcript";
import type { MeetingDetail, Transcript } from "@/lib/types";

function PageSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-7 w-1/2" />
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-14 w-full" />
      <Skeleton className="h-[50vh] w-full" />
    </div>
  );
}

function Participants({ m }: { m: MeetingDetail }) {
  const max = Math.max(1, ...m.participants.map((p) => p.speaking_sec));
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Participants ({m.participants.length})</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {m.participants.length === 0 && <p className="text-sm text-muted-foreground">No identified participants.</p>}
        {m.participants.map((p) => (
          <div key={p.id} className="space-y-1">
            <div className="flex items-center justify-between gap-2 text-sm">
              <Link href={`/participants/${p.id}`} className="truncate hover:underline">{p.name}</Link>
              <span className="shrink-0 text-xs text-muted-foreground">{formatDuration(p.speaking_sec)}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-1.5 flex-1 rounded-full bg-muted">
                <div className="h-1.5 rounded-full bg-primary/70" style={{ width: `${(p.speaking_sec / max) * 100}%` }} />
              </div>
              <Badge variant="outline" className="h-4 px-1 text-[10px] font-normal">{p.is_internal ? "Team" : "External"}</Badge>
            </div>
            {displayEmail(p.email) && <div className="truncate text-xs text-muted-foreground">{displayEmail(p.email)}</div>}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function MeetingView() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tParam = Number(params.get("t"));
  const initialTime = Number.isFinite(tParam) && tParam > 0 ? tParam : undefined;
  const tab = params.get("tab") === "notes" ? "notes" : "transcript";

  const { data: me } = useMe();
  const meeting = useQuery({ queryKey: ["meeting", id], queryFn: () => api.get<MeetingDetail>(`/api/meetings/${id}`) });
  const transcript = useQuery({
    queryKey: ["transcript", id],
    queryFn: () => api.get<Transcript>(`/api/meetings/${id}/transcript`),
    enabled: !!meeting.data?.has_transcript,
  });
  const player = useRef<AudioPlayerHandle>(null);
  const [time, setTime] = useState(initialTime ?? 0);
  const segments = useMemo(() => transcript.data?.segments ?? [], [transcript.data]);
  const activeIndex = useMemo(() => findActiveSegment(segments, time), [segments, time]);

  if (meeting.isPending) return <PageSkeleton />;
  if (meeting.error) return <ErrorState error={meeting.error} onRetry={() => meeting.refetch()} />;
  const m = meeting.data;
  const canDownload = me?.role === "admin" || !!me?.can_download;

  const seek = (t: number) => {
    setTime(t);
    player.current?.seek(t);
    player.current?.play();
  };
  const setTab = (v: string) => {
    const p = new URLSearchParams(params.toString());
    if (v === "notes") p.set("tab", "notes");
    else p.delete("tab");
    p.delete("t");
    router.replace(`${pathname}${p.size ? `?${p}` : ""}`, { scroll: false });
  };

  return (
    <div className="space-y-5">
      <Link href="/meetings" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> All meetings
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <h1 className="text-xl font-semibold tracking-tight">{m.subject}</h1>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span>{formatDate(m.start_at)}</span>
            <span>{formatDuration(m.duration_sec)}</span>
            {m.owner_key && <span>Owner: {m.owner_key}</span>}
            <button
              type="button"
              className="inline-flex items-center gap-1 font-mono text-xs hover:text-foreground"
              onClick={async () => {
                await navigator.clipboard?.writeText(m.id).catch(() => undefined);
                toast.success("Meeting ID copied");
              }}
              title="Copy meeting ID"
            >
              {m.id} <Copy className="size-3" />
            </button>
          </div>
          {m.topics.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {m.topics.map((t) => <Badge key={t} variant="secondary" className="font-normal">{t}</Badge>)}
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <AvailabilityBadges m={m} />
          {canDownload && m.recordings.some((r) => r.kind === "video") && <VideoDownloadButton meetingId={m.id} />}
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 space-y-4">
          {m.has_recording ? (
            <div className="sticky top-16 z-10">
              <AudioPlayer ref={player} meetingId={m.id} canDownload={canDownload} initialTime={initialTime} onTimeUpdate={setTime} />
            </div>
          ) : (
            <EmptyState title="No recording available" description="This meeting has a transcript but no audio in the archive." />
          )}
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="transcript"><FileText className="size-4" /> Transcript</TabsTrigger>
              <TabsTrigger value="notes"><NotebookText className="size-4" /> Notes</TabsTrigger>
            </TabsList>
            <TabsContent value="transcript" className="mt-3">
              {!m.has_transcript ? (
                <EmptyState title="No transcript" description="This meeting has no transcript in the archive." />
              ) : transcript.error ? (
                <ErrorState error={transcript.error} onRetry={() => transcript.refetch()} />
              ) : transcript.isPending ? (
                <Skeleton className="h-[60vh] w-full" />
              ) : (
                <TranscriptViewer segments={segments} activeIndex={activeIndex} onSeek={seek} />
              )}
            </TabsContent>
            <TabsContent value="notes" className="mt-3">
              {m.notes_md ? (
                <Card><CardContent className="pt-5"><NotesMarkdown markdown={m.notes_md} /></CardContent></Card>
              ) : (
                <EmptyState title="No notes" description="Avoma produced no notes for this meeting." />
              )}
            </TabsContent>
          </Tabs>
        </div>
        <aside className="space-y-4">
          <Participants m={m} />
          {m.transcript && (
            <Card>
              <CardContent className="space-y-1 pt-5 text-sm text-muted-foreground">
                <div>{m.transcript.segment_count.toLocaleString()} transcript turns</div>
                <div>{m.transcript.word_count.toLocaleString()} words</div>
              </CardContent>
            </Card>
          )}
        </aside>
      </div>
    </div>
  );
}

export default function MeetingPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <MeetingView />
    </Suspense>
  );
}
