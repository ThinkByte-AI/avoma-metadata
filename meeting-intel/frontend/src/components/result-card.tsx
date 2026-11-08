"use client";

import { Copy, FileText, Mic, MicOff, NotebookText, Play, Sparkles, Users } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { HighlightText } from "@/components/highlight-text";
import { Badge } from "@/components/ui/badge";
import { formatDate, formatDuration, formatTimestamp } from "@/lib/format";
import type { MeetingHit, MeetingSummary, SegmentMatch } from "@/lib/types";

export function MeetingMeta({ m }: { m: MeetingSummary }) {
  const shown = m.participants.slice(0, 4).map((p) => p.name);
  const more = m.participant_count - shown.length;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <span>{formatDate(m.start_at)}</span>
      <span>{formatDuration(m.duration_sec)}</span>
      {m.participant_count > 0 && (
        <span className="inline-flex items-center gap-1">
          <Users className="size-3" aria-hidden />
          {shown.join(", ")}
          {more > 0 && ` +${more}`}
        </span>
      )}
      {m.owner_key && <span>Owner: {m.owner_key}</span>}
    </div>
  );
}

export function AvailabilityBadges({ m }: { m: MeetingSummary }) {
  return (
    <div className="flex gap-1.5">
      <Badge variant={m.has_recording ? "secondary" : "outline"} className="gap-1 font-normal">
        {m.has_recording ? <Mic className="size-3" /> : <MicOff className="size-3" />}
        {m.has_recording ? "Recording" : "No recording"}
      </Badge>
      <Badge variant={m.has_transcript ? "secondary" : "outline"} className="gap-1 font-normal">
        <FileText className="size-3" />
        {m.has_transcript ? "Transcript" : "No transcript"}
      </Badge>
    </div>
  );
}

function MatchRow({ meetingId, match }: { meetingId: string; match: SegmentMatch }) {
  const isNote = match.kind === "note";
  const who = isNote ? `Notes · ${match.section ?? "Summary"}` : match.speaker_name ?? "Unknown speaker";
  const href = match.start_sec != null ? `/meetings/${meetingId}?t=${Math.floor(match.start_sec)}` : `/meetings/${meetingId}?tab=notes`;
  return (
    <li className="group flex gap-3 rounded-md px-2 py-1.5 hover:bg-muted/60">
      <Link
        href={href}
        className="mt-0.5 inline-flex h-6 shrink-0 items-center gap-1 rounded border bg-background px-1.5 font-mono text-[11px] text-muted-foreground group-hover:border-primary/40 group-hover:text-foreground"
        aria-label={isNote ? "Open meeting notes" : `Play from ${formatTimestamp(match.start_sec ?? 0)}`}
      >
        {isNote ? <NotebookText className="size-3" /> : <Play className="size-3" />}
        {isNote ? "Notes" : formatTimestamp(match.start_sec ?? 0)}
      </Link>
      <div className="min-w-0 text-sm">
        <div className="mb-0.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          {who}
          {match.match_type !== "keyword" && (
            <span className="inline-flex items-center gap-0.5 text-sky-600 dark:text-sky-400" title="Matched by meaning">
              <Sparkles className="size-3" /> related
            </span>
          )}
        </div>
        <p className="line-clamp-3 whitespace-pre-line leading-relaxed">
          <HighlightText
            text={match.text}
            ranges={match.highlights}
            variant={match.match_type === "keyword" || match.match_type === "both" ? "keyword" : "semantic"}
          />
        </p>
      </div>
    </li>
  );
}

export function ResultCard({ hit }: { hit: MeetingHit }) {
  const m = hit.meeting;
  const copyId = async () => {
    await navigator.clipboard?.writeText(m.id).catch(() => undefined);
    toast.success("Meeting ID copied");
  };
  return (
    <article className="rounded-lg border bg-card p-4 transition-shadow hover:shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <Link href={`/meetings/${m.id}`} className="block truncate font-medium hover:underline">
            {m.subject}
          </Link>
          <MeetingMeta m={m} />
        </div>
        <AvailabilityBadges m={m} />
      </div>
      <button
        type="button"
        onClick={copyId}
        className="mt-1 inline-flex items-center gap-1 font-mono text-[11px] text-muted-foreground hover:text-foreground"
        title="Copy meeting ID"
      >
        {m.id.slice(0, 8)} <Copy className="size-3" />
      </button>
      {hit.matches.length > 0 && (
        <ul className="mt-2 space-y-0.5 border-t pt-2">
          {hit.matches.map((x) => <MatchRow key={x.segment_id} meetingId={m.id} match={x} />)}
        </ul>
      )}
    </article>
  );
}
