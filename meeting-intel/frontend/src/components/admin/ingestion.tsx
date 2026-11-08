"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Pause, Play, RefreshCw, RotateCcw, XCircle, Zap } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/format";
import { embedPercent, isActive, progressPercent } from "@/lib/ingestion";
import type { IngestionStatus, Job, SystemStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_STYLE: Record<string, string> = {
  queued: "bg-muted text-foreground",
  running: "bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-300",
  paused: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300",
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300",
  failed: "bg-destructive/10 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
};

const PHASE_LABEL: Record<string, string> = {
  parse: "Reading transcripts",
  embed: "Building meaning-based search",
  done: "Finished",
};

function ProgressBar({ value, label }: { value: number; label: string }) {
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
    >
      <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${value}%` }} />
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

function num(stats: Record<string, unknown> | undefined, key: string): number | undefined {
  const v = stats?.[key];
  return typeof v === "number" ? v : undefined;
}

export function AwsStatusCard() {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["system-status"],
    queryFn: () => api.get<SystemStatus>("/api/system/status"),
    refetchInterval: 60_000,
  });
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">AWS connection</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <>
            <div className="flex items-center gap-2">
              {data.aws.ok ? (
                <CheckCircle2 className="size-4 text-emerald-600" aria-hidden />
              ) : (
                <XCircle className="size-4 text-destructive" aria-hidden />
              )}
              <span className="font-medium">{data.aws.ok ? "Connected" : "Not connected"}</span>
            </div>
            {!data.aws.ok && data.aws.error && <p className="break-words text-xs text-destructive">{data.aws.error}</p>}
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-muted-foreground">Bucket</dt>
              <dd className="truncate font-mono">{data.bucket}</dd>
              <dt className="text-muted-foreground">Region</dt>
              <dd className="font-mono">{data.region}</dd>
              <dt className="text-muted-foreground">Prefixes</dt>
              <dd className="font-mono">{data.prefixes.join(", ") || "—"}</dd>
              <dt className="text-muted-foreground">Embeddings</dt>
              <dd className="truncate font-mono">{data.embed_model}</dd>
              <dt className="text-muted-foreground">AI model</dt>
              <dd className="truncate font-mono">{data.chat_model}</dd>
              <dt className="text-muted-foreground">Database</dt>
              <dd>{data.db === "ok" ? "OK" : "Error"}</dd>
            </dl>
          </>
        )}
      </CardContent>
    </Card>
  );
}

type Action = "start" | "sync" | "retry" | "pause" | "resume";
const ACTION_DONE: Record<Action, string> = {
  start: "Initial ingestion queued",
  sync: "Incremental sync queued",
  retry: "Retry of failed meetings queued",
  pause: "Ingestion paused",
  resume: "Ingestion resumed",
};

function JobActions({ status }: { status: IngestionStatus }) {
  const qc = useQueryClient();
  const current = status.current_job;
  const active = isActive(current?.status);
  const run = useMutation({
    mutationFn: (a: Action) => api.post<Job>(`/api/ingestion/${a}`),
    onSuccess: (_job, a) => {
      toast.success(ACTION_DONE[a]);
      void qc.invalidateQueries({ queryKey: ["ingestion-status"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Action failed"),
  });
  const busy = (a: Action) => run.isPending && run.variables === a;
  const btn = (a: Action, label: string, icon: ReactNode, enabled: boolean, variant: "default" | "outline" = "outline") => (
    <Button size="sm" variant={variant} disabled={!enabled || run.isPending} onClick={() => run.mutate(a)}>
      {busy(a) ? <Loader2 className="size-4 animate-spin" /> : icon} {label}
    </Button>
  );
  return (
    <div className="flex flex-wrap gap-2">
      {btn("start", "Start initial ingestion", <Zap className="size-4" />, !active, "default")}
      {btn("sync", "Start incremental sync", <RefreshCw className="size-4" />, !active)}
      {btn("retry", "Retry failed", <RotateCcw className="size-4" />, !active && status.totals.failed > 0)}
      {btn("pause", "Pause", <Pause className="size-4" />, current?.status === "queued" || current?.status === "running")}
      {btn("resume", "Resume", <Play className="size-4" />, current?.status === "paused")}
    </div>
  );
}

function JobProgress({ job }: { job: Job }) {
  const s = job.stats as Record<string, unknown>;
  const phase = typeof s.phase === "string" ? s.phase : undefined;
  const parse = progressPercent(s);
  const embed = embedPercent(s);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">Job #{job.id}</span>
        <span className="text-muted-foreground">({job.kind})</span>
        <Badge className={cn("capitalize", STATUS_STYLE[job.status])}>{job.status}</Badge>
        {phase && job.status !== "completed" && <span className="text-muted-foreground">· {PHASE_LABEL[phase] ?? phase}</span>}
        <span className="ml-auto text-xs text-muted-foreground">
          {job.started_at ? `Started ${formatDate(job.started_at)}` : `Queued ${formatDate(job.created_at)}`}
          {job.finished_at && ` · Finished ${formatDate(job.finished_at)}`}
        </span>
      </div>
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs">
          <span>Step 1 · Reading transcripts</span>
          <span className="tabular-nums text-muted-foreground">
            {formatNumber(num(s, "processed") ?? 0)} / {formatNumber(num(s, "to_process") ?? 0)} · {parse}%
          </span>
        </div>
        <ProgressBar value={parse} label="Reading transcripts" />
      </div>
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs">
          <span>Step 2 · Building meaning-based search</span>
          <span className="tabular-nums text-muted-foreground">
            {formatNumber(num(s, "embedded") ?? 0)} / {formatNumber(num(s, "to_embed") ?? 0)} · {embed}%
          </span>
        </div>
        <ProgressBar value={embed} label="Building meaning-based search" />
      </div>
      {job.error && <p className="break-words rounded-md bg-destructive/5 p-2 text-xs text-destructive">{job.error}</p>}
    </div>
  );
}

function FailedMeetings({ items }: { items: IngestionStatus["failed_meetings"] }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">No failed meetings.</p>;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Meeting</TableHead>
            <TableHead>Error</TableHead>
            <TableHead className="w-20 text-right">Attempts</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((m) => (
            <TableRow key={m.id}>
              <TableCell className="max-w-[16rem]">
                <Link href={`/meetings/${m.id}`} className="block truncate hover:underline">{m.subject}</Link>
              </TableCell>
              <TableCell className="max-w-[28rem] truncate font-mono text-xs text-muted-foreground" title={m.error ?? ""}>
                {m.error ?? "—"}
              </TableCell>
              <TableCell className="text-right tabular-nums">{m.attempts}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function IngestionPanel() {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["ingestion-status"],
    queryFn: () => api.get<IngestionStatus>("/api/ingestion/status"),
    refetchInterval: (q) => (isActive(q.state.data?.current_job?.status) ? 3_000 : 30_000),
  });

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isPending) {
    return (
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const job = data.current_job ?? data.last_completed_job;
  const s = (job?.stats ?? {}) as Record<string, unknown>;
  const t = data.totals;
  const dash = (v: number | undefined) => (v === undefined ? "—" : formatNumber(v));

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0 space-y-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Processing</CardTitle>
            <CardDescription>
              Reads transcripts and notes from S3 (recordings are never downloaded), then builds the meaning-based
              search index. Original files in S3 are never changed.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <JobActions status={data} />
            {job ? <JobProgress job={job} /> : <p className="text-sm text-muted-foreground">No ingestion has run yet.</p>}
          </CardContent>
        </Card>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Objects scanned" value={dash(num(s, "objects_scanned"))} />
          <Stat label="Audio files" value={dash(num(s, "audio_files"))} />
          <Stat label="Transcript files" value={dash(num(s, "transcript_files"))} />
          <Stat label="Meetings identified" value={dash(num(s, "meetings_identified"))} />
          <Stat label="Meetings indexed" value={formatNumber(t.indexed)} hint={`of ${formatNumber(t.meetings)}`} />
          <Stat label="Failed" value={formatNumber(t.failed)} />
          <Stat label="Duplicates" value={dash(num(s, "duplicates") ?? t.skipped)} />
          <Stat label="Last sync" value={<span className="text-sm">{data.last_sync_at ? formatDate(data.last_sync_at) : "Never"}</span>} />
        </div>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Index</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div><div className="text-xs text-muted-foreground">Parsed (not yet indexed)</div>{formatNumber(t.parsed)}</div>
            <div><div className="text-xs text-muted-foreground">Waiting</div>{formatNumber(t.discovered)}</div>
            <div><div className="text-xs text-muted-foreground">Transcript segments</div>{formatNumber(t.segments)}</div>
            <div><div className="text-xs text-muted-foreground">Search vectors</div>{formatNumber(t.embedded_segments)}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Failed meetings ({formatNumber(t.failed)})</CardTitle>
            <CardDescription>Use “Retry failed” to process these again.</CardDescription>
          </CardHeader>
          <CardContent>
            <FailedMeetings items={data.failed_meetings} />
          </CardContent>
        </Card>
      </div>
      <aside className="space-y-4">
        <AwsStatusCard />
      </aside>
    </div>
  );
}
