"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronDown, ChevronUp, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { HighlightText } from "@/components/highlight-text";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDebounced } from "@/hooks/use-debounced";
import { formatTimestamp } from "@/lib/format";
import { filterSegments } from "@/lib/transcript";
import type { TranscriptSegment } from "@/lib/types";
import { cn } from "@/lib/utils";

const SPEAKER_COLORS = [
  "text-sky-700 dark:text-sky-400",
  "text-emerald-700 dark:text-emerald-400",
  "text-violet-700 dark:text-violet-400",
  "text-amber-700 dark:text-amber-400",
  "text-rose-700 dark:text-rose-400",
  "text-teal-700 dark:text-teal-400",
  "text-indigo-700 dark:text-indigo-400",
  "text-orange-700 dark:text-orange-400",
];

function useSpeakerColors(segments: TranscriptSegment[]) {
  return useMemo(() => {
    const map = new Map<string, string>();
    for (const s of segments) {
      const k = s.speaker_name ?? "?";
      if (!map.has(k)) map.set(k, SPEAKER_COLORS[map.size % SPEAKER_COLORS.length]);
    }
    return map;
  }, [segments]);
}

export function TranscriptViewer({
  segments,
  activeIndex,
  onSeek,
  initialQuery = "",
}: {
  segments: TranscriptSegment[];
  activeIndex: number;
  onSeek: (t: number) => void;
  initialQuery?: string;
}) {
  const parentRef = useRef<HTMLDivElement>(null);
  const lastUserScroll = useRef(0);
  const [query, setQuery] = useState(initialQuery);
  const dq = useDebounced(query, 150);
  const matches = useMemo(() => filterSegments(segments, dq), [segments, dq]);
  const matchRanges = useMemo(() => new Map(matches.map((m) => [m.index, m.ranges])), [matches]);
  const [matchPos, setMatchPos] = useState(0);
  const colors = useSpeakerColors(segments);

  const virtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 76,
    overscan: 8,
  });

  // Follow playback unless the reader scrolled in the last few seconds.
  useEffect(() => {
    if (activeIndex >= 0 && Date.now() - lastUserScroll.current > 4000) {
      virtualizer.scrollToIndex(activeIndex, { align: "center" });
    }
  }, [activeIndex, virtualizer]);

  useEffect(() => setMatchPos(0), [dq]);
  const jump = (pos: number) => {
    if (!matches.length) return;
    const p = (pos + matches.length) % matches.length;
    setMatchPos(p);
    lastUserScroll.current = Date.now();
    virtualizer.scrollToIndex(matches[p].index, { align: "center" });
  };

  const markUserScroll = () => {
    lastUserScroll.current = Date.now();
  };

  return (
    <div className="flex min-h-0 flex-col rounded-lg border">
      <div className="flex items-center gap-2 border-b p-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && jump(e.shiftKey ? matchPos - 1 : matchPos + 1)}
            placeholder="Search in transcript"
            className="h-8 pl-8 text-sm"
            aria-label="Search in transcript"
          />
        </div>
        {dq.trim() && (
          <>
            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
              {matches.length ? `${matchPos + 1} of ${matches.length}` : "No matches"}
            </span>
            <Button size="icon" variant="ghost" className="size-8" onClick={() => jump(matchPos - 1)} aria-label="Previous match" disabled={!matches.length}>
              <ChevronUp className="size-4" />
            </Button>
            <Button size="icon" variant="ghost" className="size-8" onClick={() => jump(matchPos + 1)} aria-label="Next match" disabled={!matches.length}>
              <ChevronDown className="size-4" />
            </Button>
          </>
        )}
      </div>
      <div
        ref={parentRef}
        onWheel={markUserScroll}
        onTouchMove={markUserScroll}
        className="h-[60vh] overflow-y-auto"
        role="list"
        aria-label="Transcript"
      >
        <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
          {virtualizer.getVirtualItems().map((row) => {
            const s = segments[row.index];
            const active = row.index === activeIndex;
            const ranges = matchRanges.get(row.index);
            const isCurrentMatch = matches[matchPos]?.index === row.index;
            return (
              <div
                key={s.id}
                data-index={row.index}
                ref={virtualizer.measureElement}
                role="listitem"
                className="absolute left-0 top-0 w-full"
                style={{ transform: `translateY(${row.start}px)` }}
              >
                <button
                  type="button"
                  onClick={() => onSeek(s.start_sec)}
                  className={cn(
                    "flex w-full gap-3 border-l-2 border-transparent px-3 py-2.5 text-left transition-colors hover:bg-muted/60",
                    active && "border-primary bg-accent",
                    isCurrentMatch && "ring-1 ring-inset ring-amber-400",
                  )}
                  aria-current={active ? "true" : undefined}
                >
                  <span className="w-12 shrink-0 pt-0.5 font-mono text-[11px] tabular-nums text-muted-foreground">
                    {formatTimestamp(s.start_sec)}
                  </span>
                  <span className="min-w-0 text-sm leading-relaxed">
                    <span className={cn("mr-1.5 font-medium", colors.get(s.speaker_name ?? "?"))}>
                      {s.speaker_name ?? "Unknown speaker"}
                    </span>
                    {ranges ? <HighlightText text={s.text} ranges={ranges} /> : s.text}
                  </span>
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
