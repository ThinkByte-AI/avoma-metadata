"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, Mic, MicOff } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDebounced } from "@/hooks/use-debounced";
import { api, qs } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/format";
import type { MeetingSummary, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;
type Sort = "date_desc" | "date_asc" | "duration_desc" | "title";

export default function MeetingsPage() {
  const [title, setTitle] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [rec, setRec] = useState("any");
  const [sort, setSort] = useState<Sort>("date_desc");
  const [page, setPage] = useState(1);
  const dTitle = useDebounced(title.trim(), 300);
  useEffect(() => setPage(1), [dTitle, from, to, rec, sort]);

  const params = {
    page, page_size: PAGE_SIZE, sort, title: dTitle || undefined, date_from: from || undefined, date_to: to || undefined,
    has_recording: rec === "any" ? undefined : rec === "yes",
  };
  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ["meetings", params],
    queryFn: () => api.get<Page<MeetingSummary>>(`/api/meetings${qs(params)}`),
    placeholderData: keepPreviousData,
  });
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div>
      <PageHeader title="All Meetings" description={data ? `${data.total.toLocaleString()} meetings` : undefined} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Filter by title" className="h-8 w-56" />
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-8 w-40" aria-label="From date" />
        <span className="text-sm text-muted-foreground">to</span>
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-8 w-40" aria-label="To date" />
        <Select value={rec} onValueChange={setRec}>
          <SelectTrigger size="sm" className="h-8 w-36" aria-label="Recording"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any recording</SelectItem>
            <SelectItem value="yes">Has recording</SelectItem>
            <SelectItem value="no">No recording</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sort} onValueChange={(v) => setSort(v as Sort)}>
          <SelectTrigger size="sm" className="h-8 w-36" aria-label="Sort"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="date_desc">Newest first</SelectItem>
            <SelectItem value="date_asc">Oldest first</SelectItem>
            <SelectItem value="duration_desc">Longest first</SelectItem>
            <SelectItem value="title">Title A–Z</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : isPending ? (
        <div className="space-y-2">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
      ) : data.items.length === 0 ? (
        <EmptyState icon={CalendarDays} title="No meetings found" description="Try a different title or date range." />
      ) : (
        <>
          <div className={cn("overflow-x-auto rounded-lg border transition-opacity", isFetching && "opacity-60")}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Meeting</TableHead>
                  <TableHead className="w-44">Date</TableHead>
                  <TableHead className="w-24">Duration</TableHead>
                  <TableHead className="hidden lg:table-cell">Participants</TableHead>
                  <TableHead className="hidden w-28 md:table-cell">Owner</TableHead>
                  <TableHead className="w-12 text-center" aria-label="Recording" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="max-w-[22rem]">
                      <Link href={`/meetings/${m.id}`} className="block truncate font-medium hover:underline">{m.subject}</Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(m.start_at)}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDuration(m.duration_sec)}</TableCell>
                    <TableCell className="hidden max-w-[18rem] truncate text-muted-foreground lg:table-cell">
                      {m.participants.slice(0, 3).map((p) => p.name).join(", ")}
                      {m.participant_count > 3 && ` +${m.participant_count - 3}`}
                    </TableCell>
                    <TableCell className="hidden text-muted-foreground md:table-cell">{m.owner_key ?? "—"}</TableCell>
                    <TableCell className="text-center">
                      {m.has_recording
                        ? <Mic className="mx-auto size-4 text-muted-foreground" aria-label="Has recording" />
                        : <MicOff className="mx-auto size-4 text-muted-foreground/50" aria-label="No recording" />}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <nav className="mt-4 flex items-center justify-center gap-3" aria-label="Pagination">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              <ChevronLeft className="size-4" /> Previous
            </Button>
            <span className="text-sm text-muted-foreground">Page {page} of {pages}</span>
            <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Next <ChevronRight className="size-4" />
            </Button>
          </nav>
        </>
      )}
    </div>
  );
}
