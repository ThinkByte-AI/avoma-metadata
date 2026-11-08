// Progress helpers for the two-phase ingestion job (parse, then embed).

type Stats = Record<string, unknown>;

function pct(done: unknown, total: unknown): number {
  const d = typeof done === "number" ? done : 0;
  const t = typeof total === "number" ? total : 0;
  if (t <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((d / t) * 100)));
}

/** Phase 1, reading transcripts: processed / to_process (0 when unknown, capped at 100). */
export function progressPercent(stats: Stats): number {
  return pct(stats.processed, stats.to_process);
}

/** Phase 2, building semantic vectors: embedded / to_embed (0 when unknown, capped at 100). */
export function embedPercent(stats: Stats): number {
  return pct(stats.embedded, stats.to_embed);
}

export const ACTIVE_JOB_STATUSES = ["queued", "running", "paused"] as const;

export function isActive(status: string | null | undefined): boolean {
  return !!status && (ACTIVE_JOB_STATUSES as readonly string[]).includes(status);
}
