"use client";

import { format, parseISO } from "date-fns";
import { CalendarRange, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { DateRange } from "react-day-picker";
import { PeoplePicker, useParticipantNames } from "@/components/people-picker";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { activeFilterCount } from "@/lib/search-params";
import type { DatePreset, SearchFilters } from "@/lib/types";

const PRESETS: { value: DatePreset; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "6m", label: "Last 6 months" },
  { value: "1y", label: "Last year" },
  { value: "all", label: "Entire archive" },
];
const DURATIONS = [
  { value: "any", label: "Any length" },
  { value: "0-15", label: "Under 15 min" },
  { value: "15-45", label: "15–45 min" },
  { value: "45-", label: "Over 45 min" },
];

function triState(v: boolean | null | undefined) {
  return v === true ? "yes" : v === false ? "no" : "any";
}
function fromTri(v: string): boolean | undefined {
  return v === "yes" ? true : v === "no" ? false : undefined;
}

/** Text input that only commits on blur/Enter so typing doesn't run a search per keystroke. */
function CommitInput({ value, onCommit, placeholder }: { value?: string | null; onCommit: (v?: string) => void; placeholder: string }) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  const commit = () => onCommit(v.trim() || undefined);
  return (
    <Input
      value={v}
      onChange={(e) => setV(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && commit()}
      placeholder={placeholder}
      className="h-8 w-36 text-sm"
    />
  );
}

export function FilterBar({ filters, onChange }: { filters: SearchFilters; onChange: (f: SearchFilters) => void }) {
  const set = (patch: Partial<SearchFilters>) => {
    const next = { ...filters, ...patch };
    for (const k of Object.keys(next) as (keyof SearchFilters)[]) {
      const v = next[k];
      if (v === undefined || v === null || (Array.isArray(v) && v.length === 0)) delete next[k];
    }
    onChange(next);
  };
  const participantIds = filters.participant_ids ?? [];
  const speakerIds = filters.speaker_ids ?? [];
  const names = useParticipantNames([...new Set([...participantIds, ...speakerIds])]);

  const range: DateRange | undefined = filters.date_from || filters.date_to
    ? { from: filters.date_from ? parseISO(filters.date_from) : undefined, to: filters.date_to ? parseISO(filters.date_to) : undefined }
    : undefined;
  const durValue =
    filters.min_duration_min == null && filters.max_duration_min == null
      ? "any"
      : `${filters.min_duration_min ?? 0}-${filters.max_duration_min ?? ""}`;

  const chips: { key: string; label: string; clear: () => void }[] = [
    ...participantIds.map((id) => ({
      key: `p${id}`, label: `With ${names[id]}`, clear: () => set({ participant_ids: participantIds.filter((x) => x !== id) }),
    })),
    ...speakerIds.map((id) => ({
      key: `s${id}`, label: `Said by ${names[id]}`, clear: () => set({ speaker_ids: speakerIds.filter((x) => x !== id) }),
    })),
    ...(filters.owner ? [{ key: "owner", label: `Owner: ${filters.owner}`, clear: () => set({ owner: undefined }) }] : []),
    ...(filters.title ? [{ key: "title", label: `Title: ${filters.title}`, clear: () => set({ title: undefined }) }] : []),
    ...(range
      ? [{
          key: "range",
          label: `${filters.date_from ?? "…"} → ${filters.date_to ?? "…"}`,
          clear: () => set({ date_from: undefined, date_to: undefined }),
        }]
      : []),
  ];

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <PeoplePicker label="Participants" value={participantIds} onChange={(ids) => set({ participant_ids: ids })} />
        <PeoplePicker label="Speaker" value={speakerIds} onChange={(ids) => set({ speaker_ids: ids })} />

        <Select value={filters.date_preset ?? "all"} onValueChange={(v) => set({ date_preset: v === "all" ? undefined : (v as DatePreset) })}>
          <SelectTrigger size="sm" className="h-8 w-36" aria-label="Date"><SelectValue /></SelectTrigger>
          <SelectContent>
            {PRESETS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
          </SelectContent>
        </Select>

        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="h-8"><CalendarRange className="size-3.5" /> Custom dates</Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="range"
              numberOfMonths={2}
              selected={range}
              defaultMonth={range?.from}
              onSelect={(r) => set({
                date_from: r?.from ? format(r.from, "yyyy-MM-dd") : undefined,
                date_to: r?.to ? format(r.to, "yyyy-MM-dd") : undefined,
              })}
            />
          </PopoverContent>
        </Popover>

        <Select
          value={DURATIONS.some((d) => d.value === durValue) ? durValue : "any"}
          onValueChange={(v) => {
            if (v === "any") return set({ min_duration_min: undefined, max_duration_min: undefined });
            const [a, b] = v.split("-");
            set({ min_duration_min: a ? Number(a) || undefined : undefined, max_duration_min: b ? Number(b) : undefined });
          }}
        >
          <SelectTrigger size="sm" className="h-8 w-32" aria-label="Duration"><SelectValue /></SelectTrigger>
          <SelectContent>{DURATIONS.map((d) => <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>)}</SelectContent>
        </Select>

        <Select value={triState(filters.has_recording)} onValueChange={(v) => set({ has_recording: fromTri(v) })}>
          <SelectTrigger size="sm" className="h-8 w-36" aria-label="Recording"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any recording</SelectItem>
            <SelectItem value="yes">Has recording</SelectItem>
            <SelectItem value="no">No recording</SelectItem>
          </SelectContent>
        </Select>

        <Select value={triState(filters.has_transcript)} onValueChange={(v) => set({ has_transcript: fromTri(v) })}>
          <SelectTrigger size="sm" className="h-8 w-36" aria-label="Transcript"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any transcript</SelectItem>
            <SelectItem value="yes">Has transcript</SelectItem>
            <SelectItem value="no">No transcript</SelectItem>
          </SelectContent>
        </Select>

        <CommitInput value={filters.owner} onCommit={(v) => set({ owner: v })} placeholder="Owner" />
        <CommitInput value={filters.title} onCommit={(v) => set({ title: v })} placeholder="Title contains" />

        {activeFilterCount(filters) > 0 && (
          <Button variant="ghost" size="sm" className="h-8" onClick={() => onChange({})}>Clear all</Button>
        )}
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((c) => (
            <span key={c.key} className="inline-flex items-center gap-1 rounded-full border bg-muted/50 py-0.5 pl-2.5 pr-1 text-xs">
              {c.label}
              <button type="button" onClick={c.clear} aria-label={`Remove ${c.label}`} className="rounded-full p-0.5 hover:bg-background">
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
