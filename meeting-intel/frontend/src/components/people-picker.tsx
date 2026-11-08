"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useDebounced } from "@/hooks/use-debounced";
import { api, qs } from "@/lib/api";
import { displayEmail } from "@/lib/format";
import type { Page, ParticipantDetail, ParticipantRow } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Names for participant ids that came from the URL. */
export function useParticipantNames(ids: number[]): Record<number, string> {
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["participant", id],
      queryFn: () => api.get<ParticipantDetail>(`/api/participants/${id}`),
      staleTime: 5 * 60_000,
    })),
  });
  const out: Record<number, string> = {};
  ids.forEach((id, i) => {
    out[id] = results[i]?.data?.name ?? `#${id}`;
  });
  return out;
}

export function PeoplePicker({
  value,
  onChange,
  label,
}: {
  value: number[];
  onChange: (ids: number[]) => void;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim(), 200);
  const { data, isFetching } = useQuery({
    queryKey: ["participants-pick", dq],
    queryFn: () => api.get<Page<ParticipantRow>>(`/api/participants${qs({ q: dq || undefined, page_size: 20 })}`),
    enabled: open,
  });
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className={cn("h-8 justify-between gap-1", value.length && "border-primary/40")}>
          {label}
          {value.length > 0 && <span className="rounded bg-primary px-1 text-[10px] text-primary-foreground">{value.length}</span>}
          <ChevronsUpDown className="size-3.5 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput value={q} onValueChange={setQ} placeholder="Name or email…" />
          <CommandList>
            <CommandEmpty>{isFetching ? "Searching…" : "No people found."}</CommandEmpty>
            <CommandGroup>
              {data?.items.map((p) => (
                <CommandItem key={p.id} value={String(p.id)} onSelect={() => toggle(p.id)}>
                  <Check className={cn("size-4", value.includes(p.id) ? "opacity-100" : "opacity-0")} />
                  <div className="min-w-0">
                    <div className="truncate">{p.name}</div>
                    {displayEmail(p.email) && <div className="truncate text-xs text-muted-foreground">{displayEmail(p.email)}</div>}
                  </div>
                  <span className="ml-auto text-xs text-muted-foreground">{p.meeting_count}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
