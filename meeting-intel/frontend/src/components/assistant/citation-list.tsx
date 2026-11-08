"use client";

import { NotebookText, Play } from "lucide-react";
import Link from "next/link";
import { formatDate, formatTimestamp } from "@/lib/format";
import type { Citation } from "@/lib/types";
import { cn } from "@/lib/utils";

export function citationAnchorId(messageId: string, n: number) {
  return `cite-${messageId}-${n}`;
}

function speakerLabel(c: Citation): string {
  if (!c.speaker_name) return "Meeting notes";
  // Conversation windows carry several speakers ("Alice Tester, Bob Client").
  return c.speaker_name.includes(",") ? `Conversation: ${c.speaker_name}` : c.speaker_name;
}

export function CitationList({
  messageId,
  citations,
  highlighted,
}: {
  messageId: string;
  citations: Citation[];
  highlighted: number | null;
}) {
  if (!citations.length) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Sources</p>
      <ol className="grid gap-2 sm:grid-cols-2">
        {citations.map((c) => {
          const hasTime = c.start_sec !== null && c.start_sec !== undefined;
          const href = hasTime
            ? `/meetings/${c.meeting_id}?t=${Math.floor(c.start_sec as number)}`
            : `/meetings/${c.meeting_id}?tab=notes`;
          return (
            <li
              key={c.n}
              id={citationAnchorId(messageId, c.n)}
              className={cn(
                "scroll-mt-24 rounded-lg border bg-card p-3 text-sm transition-shadow",
                highlighted === c.n && "ring-2 ring-primary/60",
              )}
            >
              <div className="flex items-start gap-2">
                <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded bg-primary/10 text-[11px] font-semibold text-primary">
                  {c.n}
                </span>
                <div className="min-w-0 flex-1 space-y-1">
                  <Link href={`/meetings/${c.meeting_id}`} className="block truncate font-medium hover:underline">
                    {c.subject}
                  </Link>
                  <div className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
                    <span>{formatDate(c.start_at, false)}</span>
                    <span className="truncate">{speakerLabel(c)}</span>
                    {hasTime && <span className="font-mono">{formatTimestamp(c.start_sec as number)}</span>}
                  </div>
                  <p className="line-clamp-4 whitespace-pre-line text-xs leading-relaxed text-muted-foreground">{c.excerpt}</p>
                  <Link
                    href={href}
                    className="inline-flex items-center gap-1 pt-0.5 text-xs font-medium text-primary hover:underline"
                  >
                    {hasTime ? (
                      <>
                        <Play className="size-3" /> Open recording at {formatTimestamp(c.start_sec as number)}
                      </>
                    ) : (
                      <>
                        <NotebookText className="size-3" /> Open meeting notes
                      </>
                    )}
                  </Link>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
