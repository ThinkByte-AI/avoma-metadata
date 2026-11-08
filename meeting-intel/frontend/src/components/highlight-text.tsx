import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function mergeRanges(ranges: [number, number][]): [number, number][] {
  const sorted = ranges.filter(([s, e]) => e > s).sort((a, b) => a[0] - b[0]);
  const out: [number, number][] = [];
  for (const [s, e] of sorted) {
    const last = out[out.length - 1];
    if (last && s <= last[1]) last[1] = Math.max(last[1], e);
    else out.push([s, e]);
  }
  return out;
}

/** Renders text with <mark> around the ranges. Text is always rendered as text, never as HTML. */
export function HighlightText({
  text,
  ranges,
  variant = "keyword",
  className,
}: {
  text: string;
  ranges: [number, number][];
  variant?: "keyword" | "semantic";
  className?: string;
}) {
  const parts: ReactNode[] = [];
  let pos = 0;
  for (const [rs, re] of mergeRanges(ranges)) {
    const s = Math.max(0, Math.min(rs, text.length));
    const e = Math.max(s, Math.min(re, text.length));
    if (s === e) continue;
    if (s > pos) parts.push(text.slice(pos, s));
    parts.push(
      <mark
        key={s}
        data-variant={variant}
        className={cn(
          "rounded-sm text-inherit",
          variant === "keyword"
            ? "bg-amber-200/80 px-0.5 dark:bg-amber-400/30"
            : "bg-transparent underline decoration-sky-500/60 decoration-2 underline-offset-4",
        )}
      >
        {text.slice(s, e)}
      </mark>,
    );
    pos = e;
  }
  if (pos < text.length) parts.push(text.slice(pos));
  return <span className={className}>{parts}</span>;
}
