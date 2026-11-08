"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDebounced } from "@/hooks/use-debounced";
import { api, qs } from "@/lib/api";
import { displayEmail, formatDate, formatDuration } from "@/lib/format";
import type { Page, ParticipantRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;
type Sort = "meetings_desc" | "name" | "last_seen";

export default function ParticipantsPage() {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("all");
  const [sort, setSort] = useState<Sort>("meetings_desc");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q.trim(), 300);
  useEffect(() => setPage(1), [dq, kind, sort]);

  const params = {
    q: dq || undefined,
    internal: kind === "all" ? undefined : kind === "team",
    sort,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ["participants", params],
    queryFn: () => api.get<Page<ParticipantRow>>(`/api/participants${qs(params)}`),
    placeholderData: keepPreviousData,
  });
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div>
      <PageHeader title="Participants" description={data ? `${data.total.toLocaleString()} people across your meetings` : undefined} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or email" className="h-8 w-64 pl-8"
                 aria-label="Search participants" />
        </div>
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger size="sm" className="h-8 w-36" aria-label="Team or external"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Everyone</SelectItem>
            <SelectItem value="team">Team</SelectItem>
            <SelectItem value="external">External</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sort} onValueChange={(v) => setSort(v as Sort)}>
          <SelectTrigger size="sm" className="h-8 w-40" aria-label="Sort"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="meetings_desc">Most meetings</SelectItem>
            <SelectItem value="last_seen">Most recent</SelectItem>
            <SelectItem value="name">Name A–Z</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : isPending ? (
        <div className="space-y-2">{Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
      ) : data.items.length === 0 ? (
        <EmptyState icon={Users} title="No people found" description="Try a different name or filter." />
      ) : (
        <>
          <div className={cn("overflow-x-auto rounded-lg border transition-opacity", isFetching && "opacity-60")}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead className="hidden md:table-cell">Email</TableHead>
                  <TableHead className="w-24" />
                  <TableHead className="w-24 text-right">Meetings</TableHead>
                  <TableHead className="hidden w-28 text-right sm:table-cell">Speaking</TableHead>
                  <TableHead className="hidden w-32 lg:table-cell">First meeting</TableHead>
                  <TableHead className="hidden w-32 lg:table-cell">Last meeting</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="max-w-[16rem]">
                      <Link href={`/participants/${p.id}`} className="block truncate font-medium hover:underline">{p.name}</Link>
                    </TableCell>
                    <TableCell className="hidden max-w-[16rem] truncate text-muted-foreground md:table-cell">
                      {displayEmail(p.email) ?? "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-normal">{p.is_internal ? "Team" : "External"}</Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{p.meeting_count.toLocaleString()}</TableCell>
                    <TableCell className="hidden text-right text-muted-foreground sm:table-cell">{formatDuration(p.speaking_sec)}</TableCell>
                    <TableCell className="hidden text-muted-foreground lg:table-cell">{formatDate(p.first_meeting_at, false)}</TableCell>
                    <TableCell className="hidden text-muted-foreground lg:table-cell">{formatDate(p.last_meeting_at, false)}</TableCell>
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
