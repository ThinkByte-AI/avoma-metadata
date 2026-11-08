// Mirrors the backend response models (snake_case, same field names).

export type Role = "admin" | "user";
export type Scope = "own" | "all";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  access_scope: Scope;
  account_label: string | null;
  can_download: boolean;
  is_active: boolean;
  last_login_at: string | null;
}

export interface ParticipantRef {
  id: number;
  name: string;
  email: string | null;
  is_internal: boolean;
}

export interface ParticipantWithTime extends ParticipantRef {
  speaking_sec: number;
}

export interface MeetingSummary {
  id: string;
  subject: string;
  start_at: string | null;
  duration_sec: number | null;
  owner_key: string | null;
  has_recording: boolean;
  has_transcript: boolean;
  participant_count: number;
  participants: ParticipantRef[];
  topics: string[];
}

export interface Page<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface MeetingDetail extends Omit<MeetingSummary, "participants"> {
  participants: ParticipantWithTime[];
  notes_md: string | null;
  recordings: { kind: "audio" | "video"; size_bytes: number }[];
  transcript: { segment_count: number; word_count: number } | null;
  ingest_status: string;
  accounts: string[];
}

export interface TranscriptSegment {
  id: number;
  seq: number;
  speaker_name: string | null;
  participant_id: number | null;
  start_sec: number;
  end_sec: number;
  text: string;
}

export interface Transcript {
  meeting_id: string;
  speakers: ParticipantWithTime[];
  segments: TranscriptSegment[];
}

export interface RecordingUrl {
  url: string;
  expires_at: string;
  content_type: string;
  kind: "audio" | "video";
}

// --- search -----------------------------------------------------------------

export type DatePreset = "today" | "7d" | "30d" | "6m" | "1y" | "all";
export type SearchMode = "auto" | "keyword" | "semantic";
export type SearchSort = "relevance" | "date_desc" | "date_asc" | "duration_desc";

export interface SearchFilters {
  participant_ids?: number[];
  speaker_ids?: number[];
  owner?: string | null;
  title?: string | null;
  date_preset?: DatePreset | null;
  date_from?: string | null;
  date_to?: string | null;
  min_duration_min?: number | null;
  max_duration_min?: number | null;
  has_recording?: boolean | null;
  has_transcript?: boolean | null;
}

export interface SearchRequest {
  q: string;
  filters: SearchFilters;
  mode: SearchMode;
  sort: SearchSort;
  page: number;
  page_size: number;
}

export interface SegmentMatch {
  segment_id: number;
  kind: "utterance" | "note";
  speaker_name: string | null;
  section: string | null;
  start_sec: number | null;
  text: string;
  highlights: [number, number][];
  match_type: "keyword" | "semantic" | "both";
}

export interface MeetingHit {
  meeting: MeetingSummary;
  score: number;
  match_types: string[];
  matches: SegmentMatch[];
}

export interface SearchResponse {
  total: number;
  page: number;
  page_size: number;
  results: MeetingHit[];
  took_ms: number;
  semantic_used: boolean;
}

export interface Suggestions {
  participants: ParticipantRef[];
  meetings: { id: string; subject: string; start_at: string | null }[];
  recent: string[];
}

export interface SearchHistoryItem {
  id: number;
  query: string;
  filters: SearchFilters;
  mode: SearchMode;
  result_count: number;
  created_at: string;
}

// --- participants -------------------------------------------------------------

export interface ParticipantRow extends ParticipantRef {
  meeting_count: number;
  speaking_sec: number;
  first_meeting_at: string | null;
  last_meeting_at: string | null;
}

export interface Mention {
  meeting_id: string;
  subject: string;
  start_at: string | null;
  segment_id: number;
  start_sec: number | null;
  speaker_name: string | null;
  text: string;
}

export interface ParticipantDetail extends ParticipantRow {
  meetings: Page<MeetingSummary>;
  mentions: Mention[];
}

// --- dashboard / analytics ------------------------------------------------------

export interface DashboardStats {
  total_meetings: number;
  total_recordings: number;
  total_participants: number;
  total_transcripts: number;
  audio_storage_bytes: number;
  video_storage_bytes: number;
  total_duration_sec: number;
  meetings_by_month: { month: string; count: number }[];
  top_participants: { id: number; name: string; count: number }[];
  top_topics: { topic: string; count: number }[];
  recent_meetings: MeetingSummary[];
  search_activity: { date: string; count: number }[];
}

export interface Analytics {
  hours_by_month: { month: string; hours: number }[];
  meetings_by_owner: { owner: string; count: number }[];
  speaking_leaders: { participant_id: number; name: string; hours: number }[];
  topics_by_month: { month: string; topic: string; count: number }[];
  internal_vs_external_speaking: { internal_hours: number; external_hours: number };
}

// --- ingestion / system --------------------------------------------------------

export type JobStatus = "queued" | "running" | "paused" | "completed" | "failed" | "cancelled";

export interface Job {
  id: number;
  kind: "initial" | "sync" | "retry";
  status: JobStatus;
  stats: Record<string, number>;
  error: string | null;
  requested_by: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface IngestionStatus {
  current_job: Job | null;
  last_completed_job: Job | null;
  totals: {
    meetings: number;
    indexed: number;
    parsed: number;
    failed: number;
    skipped: number;
    discovered: number;
    segments: number;
    embedded_segments: number;
  };
  failed_meetings: { id: string; subject: string; error: string | null; attempts: number }[];
  last_sync_at: string | null;
  bucket: string;
  prefixes: string[];
}

export interface SystemStatus {
  aws: { ok: boolean; bucket: string; region: string; error: string | null };
  bucket: string;
  prefixes: string[];
  region: string;
  embed_model: string;
  chat_model: string;
  app_mode: "production" | "dev-mock";
  db: "ok" | "error";
}

// --- AI assistant -----------------------------------------------------------------

export interface Citation {
  n: number;
  meeting_id: string;
  subject: string;
  start_at: string | null;
  speaker_name: string | null;
  start_sec: number | null;
  segment_id: number;
  excerpt: string;
}

export interface AskResponse {
  answer_markdown: string;
  citations: Citation[];
  evidence_found: boolean;
  model: string;
  took_ms: number;
}
