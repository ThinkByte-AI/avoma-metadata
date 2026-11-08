"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, History, Search, User } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useState } from "react";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useDebounced } from "@/hooks/use-debounced";
import { api, qs } from "@/lib/api";
import { displayEmail, formatDate } from "@/lib/format";
import type { Suggestions } from "@/lib/types";

export function GlobalSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim(), 200);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Pages stay mounted when hidden; close the palette when this layout is hidden.
  useLayoutEffect(() => () => setOpen(false), []);

  const { data } = useQuery({
    queryKey: ["suggest", dq],
    queryFn: () => api.get<Suggestions>(`/api/search/suggest${qs({ q: dq })}`),
    enabled: open,
    staleTime: 15_000,
  });

  const go = (href: string) => {
    setOpen(false);
    setQ("");
    router.push(href);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex h-9 w-full max-w-md items-center gap-2 rounded-md border bg-muted/40 px-3 text-sm text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Search className="size-4" aria-hidden />
        <span className="flex-1 truncate text-left">Search meetings, people, topics…</span>
        <kbd className="hidden rounded border bg-background px-1.5 font-mono text-[10px] sm:inline">Ctrl K</kbd>
      </button>
      <CommandDialog open={open} onOpenChange={setOpen} title="Search" description="Search meetings, people and topics">
        <Command shouldFilter={false}>
          <CommandInput
            value={q}
            onValueChange={setQ}
            placeholder="Search names, emails, titles, topics or ask a question…"
          />
          <CommandList>
            <CommandEmpty>Type to search the archive.</CommandEmpty>
            {q.trim() && (
              <CommandGroup heading="Search">
                <CommandItem value={`search:${q}`} onSelect={() => go(`/search${qs({ q: q.trim() })}`)}>
                  <Search className="size-4" /> Search for “{q.trim()}”
                </CommandItem>
              </CommandGroup>
            )}
            {!!data?.participants.length && (
              <CommandGroup heading="People">
                {data.participants.map((p) => (
                  <CommandItem key={p.id} value={`p:${p.id}`} onSelect={() => go(`/search?participants=${p.id}`)}>
                    <User className="size-4" />
                    <span className="truncate">{p.name}</span>
                    {displayEmail(p.email) && <span className="ml-auto truncate text-xs text-muted-foreground">{displayEmail(p.email)}</span>}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {!!data?.meetings.length && (
              <CommandGroup heading="Meetings">
                {data.meetings.map((m) => (
                  <CommandItem key={m.id} value={`m:${m.id}`} onSelect={() => go(`/meetings/${m.id}`)}>
                    <CalendarDays className="size-4" />
                    <span className="truncate">{m.subject}</span>
                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">{formatDate(m.start_at, false)}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {!!data?.recent.length && (
              <CommandGroup heading="Recent searches">
                {data.recent.map((r) => (
                  <CommandItem key={r} value={`r:${r}`} onSelect={() => go(`/search${qs({ q: r })}`)}>
                    <History className="size-4" /> {r}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </CommandDialog>
    </>
  );
}
