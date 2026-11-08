"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search, SearchX, Sparkles } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState, type FormEvent } from "react";
import { FilterBar } from "@/components/filter-bar";
import { ResultCard } from "@/components/result-card";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { activeFilterCount, requestToSearchParams, searchParamsToRequest } from "@/lib/search-params";
import type { SearchMode, SearchRequest, SearchResponse, SearchSort } from "@/lib/types";
import { cn } from "@/lib/utils";

const MODES: { value: SearchMode; label: string; hint: string }[] = [
  { value: "auto", label: "Auto", hint: "Keywords, people, titles and meaning combined" },
  { value: "keyword", label: "Keyword", hint: "Exact words in transcripts and notes" },
  { value: "semantic", label: "Meaning", hint: "Find passages about the idea, even with different words" },
];

const SORTS: { value: SearchSort; label: string }[] = [
  { value: "relevance", label: "Most relevant" },
  { value: "date_desc", label: "Newest first" },
  { value: "date_asc", label: "Oldest first" },
  { value: "duration_desc", label: "Longest first" },
];

function ResultsSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="space-y-2 rounded-lg border p-4">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-3 w-3/5" />
          <Skeleton className="h-12 w-full" />
        </div>
      ))}
    </div>
  );
}

function SearchView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const req = useMemo(() => searchParamsToRequest(new URLSearchParams(params.toString())), [params]);
  const [draft, setDraft] = useState(req.q);
  useEffect(() => setDraft(req.q), [req.q]);

  const navigate = (next: SearchRequest) => {
    const s = requestToSearchParams(next).toString();
    router.push(s ? `${pathname}?${s}` : pathname);
  };
  const update = (patch: Partial<SearchRequest>) => navigate({ ...req, page: 1, ...patch });

  const hasInput = req.q.trim() !== "" || activeFilterCount(req.filters) > 0;
  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ["search", req],
    queryFn: () => api.post<SearchResponse>("/api/search", req),
    placeholderData: keepPreviousData,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    update({ q: draft.trim() });
  };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-5">
      <form onSubmit={submit} className="relative">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" />
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Search a name, email, title, keyword — or ask “what did we decide about pricing?”"
          className="h-12 pl-11 pr-24 text-base"
          aria-label="Search meetings"
        />
        <Button type="submit" className="absolute right-1.5 top-1/2 -translate-y-1/2">Search</Button>
      </form>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="radiogroup" aria-label="Search mode" className="inline-flex rounded-md border p-0.5">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={req.mode === m.value}
              title={m.hint}
              onClick={() => update({ mode: m.value })}
              className={cn(
                "rounded px-3 py-1 text-sm text-muted-foreground transition-colors",
                req.mode === m.value && "bg-primary text-primary-foreground",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
        <Select value={req.sort} onValueChange={(v) => update({ sort: v as SearchSort })}>
          <SelectTrigger size="sm" className="h-8 w-40" aria-label="Sort"><SelectValue /></SelectTrigger>
          <SelectContent>{SORTS.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
        </Select>
      </div>

      <FilterBar filters={req.filters} onChange={(filters) => update({ filters })} />

      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : isPending ? (
        <ResultsSkeleton />
      ) : data && data.results.length === 0 ? (
        <EmptyState
          icon={SearchX}
          title={hasInput ? "No meetings match" : "No meetings yet"}
          description={hasInput ? "Try fewer filters or different words." : "Once the archive is ingested, meetings show up here."}
        />
      ) : data ? (
        <div className={cn("space-y-3 transition-opacity", isFetching && "opacity-60")}>
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            {data.total.toLocaleString()} {data.total === 1 ? "meeting" : "meetings"}
            {req.q && <> · {(data.took_ms / 1000).toFixed(2)} s</>}
            {data.results.some((r) => r.matches.some((m) => m.match_type !== "keyword")) && (
              <span className="inline-flex items-center gap-1 text-sky-600 dark:text-sky-400">
                <Sparkles className="size-3.5" /> includes meaning-based matches
              </span>
            )}
          </p>
          {data.results.map((hit) => <ResultCard key={hit.meeting.id} hit={hit} />)}
          {pages > 1 && (
            <nav className="flex items-center justify-center gap-3 pt-2" aria-label="Pagination">
              <Button variant="outline" size="sm" disabled={req.page <= 1} onClick={() => navigate({ ...req, page: req.page - 1 })}>
                <ChevronLeft className="size-4" /> Previous
              </Button>
              <span className="text-sm text-muted-foreground">Page {req.page} of {pages}</span>
              <Button variant="outline" size="sm" disabled={req.page >= pages} onClick={() => navigate({ ...req, page: req.page + 1 })}>
                Next <ChevronRight className="size-4" />
              </Button>
            </nav>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<ResultsSkeleton />}>
      <SearchView />
    </Suspense>
  );
}
