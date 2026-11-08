// The search page keeps its whole state in the URL (shareable, back/forward work).
import type { DatePreset, SearchFilters, SearchMode, SearchRequest, SearchSort } from "./types";

export const PAGE_SIZE = 20;

export const DEFAULT_REQUEST: SearchRequest = {
  q: "",
  filters: {},
  mode: "auto",
  sort: "relevance",
  page: 1,
  page_size: PAGE_SIZE,
};

const MODES: SearchMode[] = ["auto", "keyword", "semantic"];
const SORTS: SearchSort[] = ["relevance", "date_desc", "date_asc", "duration_desc"];
const PRESETS: DatePreset[] = ["today", "7d", "30d", "6m", "1y", "all"];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function ids(v: string | null): number[] | undefined {
  if (!v) return undefined;
  const out = v.split(",").map((x) => Number(x.trim())).filter((n) => Number.isInteger(n) && n > 0);
  return out.length ? out : undefined;
}

function int(v: string | null): number | undefined {
  if (v === null || v.trim() === "") return undefined;
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 ? n : undefined;
}

function bool(v: string | null): boolean | undefined {
  return v === "1" ? true : v === "0" ? false : undefined;
}

export function searchParamsToRequest(p: URLSearchParams): SearchRequest {
  const f: SearchFilters = {};
  const set = <K extends keyof SearchFilters>(k: K, v: SearchFilters[K] | undefined) => {
    if (v !== undefined) f[k] = v;
  };
  set("participant_ids", ids(p.get("participants")));
  set("speaker_ids", ids(p.get("speakers")));
  set("owner", p.get("owner") || undefined);
  set("title", p.get("title") || undefined);
  const preset = p.get("preset") as DatePreset | null;
  set("date_preset", preset && PRESETS.includes(preset) ? preset : undefined);
  const from = p.get("from");
  const to = p.get("to");
  set("date_from", from && DATE_RE.test(from) ? from : undefined);
  set("date_to", to && DATE_RE.test(to) ? to : undefined);
  set("min_duration_min", int(p.get("mindur")));
  set("max_duration_min", int(p.get("maxdur")));
  set("has_recording", bool(p.get("rec")));
  set("has_transcript", bool(p.get("tx")));

  const mode = p.get("mode") as SearchMode | null;
  const sort = p.get("sort") as SearchSort | null;
  const page = int(p.get("page"));
  return {
    q: p.get("q") ?? "",
    filters: f,
    mode: mode && MODES.includes(mode) ? mode : "auto",
    sort: sort && SORTS.includes(sort) ? sort : "relevance",
    page: page && page >= 1 ? page : 1,
    page_size: PAGE_SIZE,
  };
}

export function requestToSearchParams(r: SearchRequest): URLSearchParams {
  const p = new URLSearchParams();
  const f = r.filters;
  if (r.q) p.set("q", r.q);
  if (r.mode !== "auto") p.set("mode", r.mode);
  if (r.sort !== "relevance") p.set("sort", r.sort);
  if (r.page > 1) p.set("page", String(r.page));
  if (f.participant_ids?.length) p.set("participants", f.participant_ids.join(","));
  if (f.speaker_ids?.length) p.set("speakers", f.speaker_ids.join(","));
  if (f.owner) p.set("owner", f.owner);
  if (f.title) p.set("title", f.title);
  if (f.date_preset) p.set("preset", f.date_preset);
  if (f.date_from) p.set("from", f.date_from);
  if (f.date_to) p.set("to", f.date_to);
  if (f.min_duration_min != null) p.set("mindur", String(f.min_duration_min));
  if (f.max_duration_min != null) p.set("maxdur", String(f.max_duration_min));
  if (f.has_recording != null) p.set("rec", f.has_recording ? "1" : "0");
  if (f.has_transcript != null) p.set("tx", f.has_transcript ? "1" : "0");
  return p;
}

export function activeFilterCount(f: SearchFilters): number {
  return Object.values(f).filter((v) => v !== undefined && v !== null && !(Array.isArray(v) && v.length === 0)).length;
}
