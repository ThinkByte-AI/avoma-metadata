# Meeting Intelligence Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working web app that ingests the Avoma archive in S3 (3,152 meetings) into Postgres and lets signed-in users search, read, listen to and ask AI questions about past meetings.

**Architecture:** FastAPI backend + a separate worker process share one Postgres (pgvector) database. The worker scans S3, parses transcripts/notes, writes segments, and embeds them with Bedrock Titan. The API serves hybrid search (full text + trigram + vector, fused with RRF), meeting/participant reads, presigned audio URLs and a GLM 5 (Bedrock) assistant with citations. A Next.js app proxies `/api/*` to the backend so auth is a same-origin httpOnly cookie.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 (sync, psycopg 3), Alembic, pgvector, boto3, pwdlib[argon2], PyJWT, pytest, moto · Next.js (App Router, current stable), TypeScript, Tailwind, shadcn/ui, lucide-react, Recharts, TanStack Query + Virtual, next-themes, react-markdown, Vitest + Testing Library · Docker Compose, `pgvector/pgvector:pg17`.

**Spec:** `docs/superpowers/specs/2026-11-08-meeting-intel-design.md` (Part A overrides Part B).

## Global Constraints

- All app code lives in `meeting-intel/`. Do not modify anything outside it except adding `docs/`.
- Never write, delete, copy or tag objects in S3. Allowed S3 calls: `ListObjectsV2`, `GetObject` (only `transcript.json`, `notes.md`), `HeadObject`, presign `GetObject`.
- Never download `recording.mp3` / `recording.mp4` server-side.
- No hardcoded bucket, prefixes, meeting IDs, participant names or credentials in code. Config only via env (`app/config.py`).
- Config defaults: `AWS_REGION=ap-south-1`, `S3_PREFIXES=avoma/`, `BEDROCK_EMBED_MODEL=amazon.titan-embed-text-v2:0`, `EMBED_DIM=1024`, `BEDROCK_CHAT_MODEL=zai.glm-5`, `PRESIGN_TTL_SEC=900`, `JWT_TTL_MIN=720`, `EMBED_CONCURRENCY=16`, `APP_MODE=production`. `S3_BUCKET` has no default (required).
- Error responses everywhere: `{"error": {"code": "<snake_case>", "message": "<human text>", "details": <optional>}}`.
- A meeting a user may not access returns **404 `not_found`**, never 403 (do not leak existence).
- Times stored UTC (`timestamptz`); API returns ISO 8601 with `Z`; UI shows the browser's local time.
- Mock data only when `APP_MODE=dev-mock`; sample meetings' subjects start with `[SAMPLE] ` and the UI shows a "Development mode — sample data" banner.
- The chat model is GLM 5 on Bedrock (`zai.glm-5`), called only through the Bedrock **Converse** API (no model-specific request bodies), so changing `BEDROCK_CHAT_MODEL` switches models.
- Backend tests: `cd meeting-intel/backend && uv run --python 3.13 pytest` against the compose DB (`DATABASE_URL_TEST=postgresql+psycopg://mi:mi@localhost:5433/meeting_intel_test`). Frontend tests: `cd meeting-intel/frontend && pnpm test`.

## Review Focus

1. **Guessed IDs by a standard user** — `GET /api/meetings/{id}`, `/transcript`, `/recording`, participant detail, search, suggest and the AI assistant must never return a meeting outside the user's access; direct ID → 404. (Tests in Tasks 9, 10, 16.)
2. **Imperfect transcripts** — `speaker_id` with no matching speaker, speaker with empty/missing email, empty `transcript` list, utterance with empty text or empty `timestamps`. Parse without crashing; unknown speaker named `Speaker <id>`. (Task 5.)
3. **Meetings without a recording (68 real ones)** — detail page shows transcript and "No recording available", recording endpoint returns 404 `recording_not_found`, results show the badge correctly. (Tasks 10, 13.)
4. **Odd search input** — empty `q` with filters only, quotes / `&|!():*` / emoji / 2,000-char strings, `q` that is a meeting UUID. No 500s; empty `q` lists filtered meetings by date. (Task 9.)
5. **Interrupted or overlapping ingestion** — worker killed mid-meeting, second "start" while a job is active, presigned URL expiring mid-playback. Re-runs are idempotent (no duplicate segments/participants), a second start returns 409 `job_active`, the player refetches the URL and resumes at the same second. (Tasks 6, 7, 13.)

---

## File Structure

```
meeting-intel/
  docker-compose.yml            db, backend, worker, frontend
  .env.example  .gitignore  README.md
  infra/iam-policy.json         least-privilege policy (S3 read + Bedrock invoke)
  infra/db-init.sql             creates meeting_intel_test
  docs/deployment.md
  backend/
    pyproject.toml  Dockerfile  alembic.ini
    migrations/env.py  migrations/versions/0001_initial.py
    app/
      main.py                   app factory, routers, error handlers, /api/health
      config.py                 Settings (pydantic-settings)
      db.py                     engine, SessionLocal, get_db
      models.py                 all ORM tables
      errors.py                 ApiError + handlers
      logging.py                JSON logging setup
      auth/security.py          hash/verify password, create/decode JWT
      auth/deps.py              current_user, require_admin
      auth/access.py            access rules (SQL clause + ensure_meeting_access)
      audit.py                  write_audit()
      aws/s3.py                 S3Store
      ingestion/classify.py     FileKind, classify_key()
      ingestion/metadata.py     load_metadata()
      ingestion/transcript.py   parse_transcript()
      ingestion/notes.py        parse_notes()
      ingestion/pipeline.py     scan_bucket(), process_meeting(), embed_meeting()
      ingestion/jobs.py         enqueue/claim/pause/resume, run_job()
      worker.py                 worker loop (python -m app.worker)
      ai/embeddings.py          Embedder protocol, BedrockEmbedder, FakeEmbedder
      ai/chat.py                ChatModel protocol, BedrockChatModel, FakeChatModel
      ai/assistant.py           ask()
      search/schemas.py         SearchRequest, SearchFilters, SearchResponse…
      search/service.py         search(), suggest()
      api/schemas.py            shared response models (MeetingSummary…)
      api/routers/{auth,users,dashboard,analytics,meetings,participants,search,ai,ingestion,system}.py
      devseed.py                dev-mock sample data
    tests/conftest.py  tests/fixtures/{transcript_basic.json,transcript_messy.json,notes_basic.md,csv/…}
    tests/test_*.py
  frontend/
    package.json  Dockerfile  next.config.ts  vitest.config.ts  middleware.ts
    src/lib/{api.ts,types.ts,format.ts,search-params.ts,transcript.ts}
    src/components/{app-sidebar,global-search,dev-banner,highlight-text,filter-bar,result-card,audio-player,transcript-viewer,stat-card,empty-state,error-state}.tsx
    src/components/ui/*         shadcn
    src/app/login/page.tsx
    src/app/(app)/layout.tsx + overview, search, meetings, meetings/[id], participants, participants/[id], assistant, analytics, ingestion, settings
```

---

## Phase 1 — Foundation

### Task 1: Backend skeleton, config, errors, Docker Compose

**Files:**
- Create: `meeting-intel/{docker-compose.yml,.env.example,.gitignore,README.md}`, `meeting-intel/infra/db-init.sql`, `meeting-intel/backend/{pyproject.toml,Dockerfile}`, `backend/app/{main.py,config.py,db.py,errors.py,logging.py}`, `backend/tests/conftest.py`
- Test: `backend/tests/test_app.py`

**Interfaces:**
- Produces: `get_settings() -> Settings` (cached); `Settings` fields = every env var in Global Constraints plus `DATABASE_URL`, `DATABASE_URL_TEST`, `JWT_SECRET`, `METADATA_DIR` (default `/data/metadata`), `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SEMANTIC_MAX_DISTANCE=0.6`, `COOKIE_SECURE=false`; `s3_prefix_list: list[str]` property splits `S3_PREFIXES` on commas.
- Produces: `create_app() -> FastAPI`; `get_db() -> Iterator[Session]`; `class ApiError(Exception)(status: int, code: str, message: str, details: Any = None)`; helpers `not_found(what: str) -> ApiError`.
- Produces test fixtures in `conftest.py`: `settings_override`, `db` (Session on the test DB; Alembic upgrade once per session, `TRUNCATE … RESTART IDENTITY CASCADE` of all tables after each test), `client` (TestClient with `get_db` overridden).

- [ ] **Step 1: Write compose + env files.** Services: `db` (`pgvector/pgvector:pg17`, `5433:5432`, user/pass/db `mi`/`${POSTGRES_PASSWORD}`/`meeting_intel`, mounts `infra/db-init.sql` into `/docker-entrypoint-initdb.d/`, named volume), `backend` (build `./backend`, `env_file: [{path: ../.env, required: false}, {path: .env, required: true}]`, volume `../csv_files:/data/metadata:ro`, command `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"`, `8000:8000`), `worker` (same image/env/volume, command `python -m app.worker`), `frontend` (Task 11). `.env.example` lists every Settings field with a comment; no real values. `.gitignore`: `.env`, `node_modules/`, `.next/`, `__pycache__/`, `.venv/`, `.pytest_cache/`.
- [ ] **Step 2: Write the failing tests** in `test_app.py`:

```python
def test_health_reports_db_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": "ok"}

def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

def test_validation_error_uses_envelope(client_with_test_routes):
    r = client_with_test_routes.get("/api/_typed", params={"n": "abc"})  # route takes n: int
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"

def test_api_error_handler(client_with_test_routes):
    r = client_with_test_routes.get("/api/_boom")  # route raises ApiError(418, "teapot", "boom")
    assert r.status_code == 418 and r.json() == {"error": {"code": "teapot", "message": "boom", "details": None}}

def test_unhandled_exception_hides_details(client_with_test_routes):
    r = client_with_test_routes.get("/api/_crash")  # route raises RuntimeError("secret")
    assert r.status_code == 500 and "secret" not in r.text
```

`client_with_test_routes` is a conftest fixture that mounts these three throwaway routes on a fresh `create_app()`.

- [ ] **Step 3: Run** `docker compose up -d db` then `uv run --python 3.13 pytest tests/test_app.py -v` → FAIL (no app).
- [ ] **Step 4: Implement** `main.py`, `config.py`, `db.py`, `errors.py`, `logging.py`. Handlers map `ApiError`, `RequestValidationError` (422 `validation_error`, details = pydantic errors), Starlette `HTTPException` (404 → `not_found`, 405 → `method_not_allowed`) and unhandled exceptions (500 `internal_error`, logged with traceback, no detail leaked). JSON logs: one line per request with method, path, status, duration_ms, user_id (if any).
- [ ] **Step 5: Run tests** → PASS. `docker compose build backend` succeeds.
- [ ] **Step 6: Commit** `feat(meeting-intel): backend skeleton, config, compose`.

### Task 2: Database schema and migration

**Files:**
- Create: `backend/app/models.py`, `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/0001_initial.py`
- Test: `backend/tests/test_schema.py`

**Interfaces:**
- Produces ORM classes (exact table/column names; later tasks rely on them):
  - `User` `users`: `id` int PK, `email` text unique (stored lowercased), `name` text, `password_hash` text, `role` text check `admin|user`, `access_scope` text check `own|all` default `own`, `account_label` text null, `can_download` bool default false, `is_active` bool default true, `last_login_at`, `created_at`, `updated_at`.
  - `Meeting` `meetings`: `id` UUID PK (= Avoma meeting uuid, the dedup key), `subject` text, `start_at` timestamptz null, `duration_sec` int null, `owner_key` text null, `accounts` text[] default `{}`, `s3_folder` text, `has_recording` bool, `has_transcript` bool, `has_notes` bool, `notes_md` text null, `topics` text[] default `{}`, `transcription_uuid` UUID null, `duplicate_of` UUID FK→meetings null, `ingest_status` text check `discovered|parsed|indexed|failed|skipped`, `ingest_error` text null, `ingest_attempts` int default 0, `transcript_etag` text null, `notes_etag` text null, `parsed_at`, `indexed_at`, `created_at`, `updated_at`. Indexes: `start_at`, `ingest_status`, GIN `accounts`, GIN trigram `subject`.
  - `Participant` `participants`: `id` int PK, `name` text, `email` text null, `is_internal` bool, `normalized_key` text unique (`email:<lower email>` or `name:<lower, single-spaced name>`). GIN trigram on `name` and `email`.
  - `MeetingParticipant` `meeting_participants`: PK (`meeting_id` FK cascade, `participant_id` FK cascade), `speaker_id` int null, `speaking_sec` numeric default 0, `is_internal` bool. Index `participant_id`.
  - `Recording` `recordings`: `id`, `meeting_id` FK cascade, `kind` check `audio|video`, `s3_key` unique, `size_bytes` bigint, `storage_class` text, `etag` text, `content_type` text; unique (`meeting_id`,`kind`).
  - `Transcript` `transcripts`: `id`, `meeting_id` FK cascade unique, `s3_key`, `transcription_uuid` UUID null, `etag`, `segment_count`, `word_count`, `speaker_count`, `last_word_sec` numeric, `source_modified_at` timestamptz null.
  - `TranscriptSegment` `transcript_segments`: `id` bigint PK, `meeting_id` FK cascade, `transcript_id` FK cascade null, `kind` check `utterance|note`, `seq` int, `participant_id` FK null, `speaker_name` text null, `section` text null, `start_sec`/`end_sec` numeric null, `text` text, `tsv` tsvector **generated always as** `to_tsvector('english', text)` stored, `embedding` `vector(1024)` null; unique (`meeting_id`,`kind`,`seq`); GIN `tsv`; HNSW `embedding vector_cosine_ops`; btree (`meeting_id`,`start_sec`).
  - `IngestionJob` `ingestion_jobs`: `id`, `kind` check `initial|sync|retry`, `status` check `queued|running|paused|completed|failed|cancelled`, `requested_by` FK users null, `stats` jsonb default `{}`, `error` text null, `created_at`, `started_at`, `finished_at`, `heartbeat_at`. Partial unique index on `(true)` where `status in ('queued','running','paused')` (only one active job).
  - `SearchHistory` `search_history`: `id`, `user_id` FK cascade, `query` text, `filters` jsonb, `mode` text, `result_count` int, `created_at`; index (`user_id`,`created_at desc`).
  - `AuditLog` `audit_logs`: `id`, `user_id` FK null, `action` text, `target_type` text null, `target_id` text null, `details` jsonb, `ip` text null, `created_at`; index `created_at`.
- Migration `0001` runs `CREATE EXTENSION IF NOT EXISTS vector; … pg_trgm;` first.

- [ ] **Step 1: Write failing tests** in `test_schema.py`: `test_extensions_installed` (`vector`, `pg_trgm` in `pg_extension`); `test_tsv_generated` (insert segment text "Revenue grew" → `tsv @@ to_tsquery('english','revenue')` true); `test_segment_unique_per_meeting_kind_seq` (second insert same triple → IntegrityError); `test_only_one_active_job` (two `queued` jobs → IntegrityError; `queued` + `completed` OK); `test_participant_normalized_key_unique`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** models + hand-written migration (autogenerate misses generated columns/HNSW/partial index — write them explicitly). `migrations/env.py` reads `DATABASE_URL` from Settings.
- [ ] **Step 4: Run** `uv run alembic upgrade head` on the dev DB and the tests → PASS. `alembic downgrade base` then `upgrade head` works.
- [ ] **Step 5: Commit** `feat(meeting-intel): database schema`.

### Task 3: Authentication, users, roles, audit log

**Files:**
- Create: `app/auth/{security.py,deps.py}`, `app/audit.py`, `app/api/routers/{auth.py,users.py}`
- Modify: `app/main.py` (routers; startup bootstrap admin)
- Test: `tests/test_auth.py`, `tests/test_users.py`

**Interfaces:**
- Produces: `hash_password(p: str) -> str`, `verify_password(p: str, h: str) -> bool`, `create_token(user_id: int) -> str`, `decode_token(t: str) -> int` (raises `ApiError(401,'unauthenticated')`).
- Produces deps: `current_user(request, db) -> User` (reads cookie `mi_session`; inactive user → 401), `require_admin(user=Depends(current_user)) -> User` (403 `forbidden`).
- Produces: `write_audit(db, user_id: int | None, action: str, target_type: str | None = None, target_id: str | None = None, details: dict | None = None, ip: str | None = None) -> None`.
- Endpoints: `POST /api/auth/login {email,password}` → 200 `UserOut` + sets cookie `mi_session` (httpOnly, SameSite=Lax, Secure=`COOKIE_SECURE`, Max-Age=`JWT_TTL_MIN*60`); bad creds → 401 `invalid_credentials` (same message for unknown email and wrong password). `POST /api/auth/logout` → 204, clears cookie. `GET /api/auth/me` → `UserOut`. Admin only: `GET /api/users`, `POST /api/users {email,name,password,role,access_scope,account_label,can_download}`, `PATCH /api/users/{id}` (any of those fields + `is_active`; password optional). `UserOut = {id,email,name,role,access_scope,account_label,can_download,is_active,last_login_at}`.
- Startup: if `users` is empty and `ADMIN_EMAIL`+`ADMIN_PASSWORD` set → create admin (scope `all`, `can_download` true). Password rule: ≥ 10 chars (422 otherwise).

- [ ] **Step 1: Failing tests:** `test_login_sets_httponly_cookie`, `test_login_wrong_password_401_generic`, `test_login_unknown_email_same_message`, `test_me_requires_cookie_401`, `test_inactive_user_rejected`, `test_standard_user_cannot_list_users_403`, `test_admin_creates_user_and_email_lowercased`, `test_short_password_422`, `test_login_writes_audit_row` (`action == "auth.login"`), `test_bootstrap_admin_created_once`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Audit actions used app-wide: `auth.login`, `auth.login_failed`, `user.create`, `user.update`, `recording.access`, `ingestion.start|pause|resume|retry|sync`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): auth, users, audit log`.

### Task 4: S3 access and file classification

**Files:**
- Create: `app/aws/s3.py`, `app/ingestion/classify.py`, `app/api/routers/system.py`
- Test: `tests/test_classify.py`, `tests/test_s3.py`

**Interfaces:**
- Produces: `class FileKind(StrEnum): TRANSCRIPT, NOTES_MD, NOTES_JSON, AUDIO, VIDEO, UNKNOWN`; `@dataclass ClassifiedKey(kind: FileKind, meeting_id: UUID | None, folder: str | None)`; `classify_key(key: str, prefixes: list[str]) -> ClassifiedKey`. Rule: key must start with a configured prefix and match `<prefix>(\d{4})/(\d{2})/(<uuid>)/<name>` with month 01–12 and a valid UUID; names `transcript.json`→TRANSCRIPT, `notes.md`→NOTES_MD, `notes.json`→NOTES_JSON, `recording.mp3|.m4a|.wav`→AUDIO, `recording.mp4|.webm`→VIDEO; anything else → UNKNOWN with `meeting_id=None`.
- Produces: `@dataclass S3Object(key: str, size: int, etag: str, storage_class: str, last_modified: datetime)`; `class S3Store(bucket: str, region: str, client=None)` with `iter_objects(prefixes: list[str]) -> Iterator[S3Object]` (paginated), `get_json(key) -> Any`, `get_text(key) -> str`, `presign_get(key: str, content_type: str, ttl: int, download_name: str | None = None) -> str`, `check() -> dict` (`{"ok": bool, "bucket": str, "region": str, "error": str | None}` via `head_bucket`). boto3 client built with `Config(retries={"mode": "adaptive", "max_attempts": 8})`.
- Endpoint (admin): `GET /api/system/status` → `{"aws": S3Store.check(), "bucket", "prefixes", "region", "embed_model", "chat_model", "app_mode", "db": "ok"}`.

- [ ] **Step 1: Failing tests.** `test_classify.py` (parametrized): `avoma/2025/02/8b4873e1-42b7-4fbc-8414-02205d45fdbf/transcript.json` → TRANSCRIPT with that UUID; `…/recording.mp3` → AUDIO; `…/recording.mp4` → VIDEO; `_bootstrap/ec2_run.log` → UNKNOWN; `avoma/2025/13/<uuid>/transcript.json` → UNKNOWN; `avoma/2025/02/not-a-uuid/transcript.json` → UNKNOWN; `avoma/2025/02/<uuid>/random.txt` → UNKNOWN; `other/2025/02/<uuid>/transcript.json` with prefixes `["avoma/"]` → UNKNOWN. `test_s3.py` (moto `mock_aws`): `test_iter_objects_paginates` (1,005 objects), `test_presign_sets_response_content_type` (URL contains `response-content-type=audio%2Fmpeg`), `test_presign_download_sets_disposition`, `test_check_reports_missing_bucket`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): S3 store and file classification`.

## Phase 2 — Data processing

### Task 5: Metadata, transcript and notes parsers

**Files:**
- Create: `app/ingestion/{metadata.py,transcript.py,notes.py}`, `tests/fixtures/{transcript_basic.json,transcript_messy.json,notes_basic.md}`, `tests/fixtures/csv/{meetings_deduped.csv,meetings_deduped2.csv,meetings_Alice.csv,meetings_Bob.csv,meetings_2yr.csv}`
- Test: `tests/test_parsers.py`

Fixtures are synthetic, shaped exactly like spec A2–A4 (invented names like "Alice Tester").

**Interfaces:**
- `@dataclass MeetingMeta(subject: str, start_at: datetime | None, duration_sec: int | None, owner_key: str | None, transcription_uuid: UUID | None, accounts: list[str])`; `load_metadata(dir: Path) -> dict[UUID, MeetingMeta]`. Reads `meetings_deduped*.csv` sorted by name (first occurrence wins) for subject/start/duration (`duration_min*60`, rounded)/owner_key/transcription_uuid; then every other `meetings_*.csv` that has an `owner` column adds that `owner` to `accounts` (sorted, unique). Missing dir → `{}` and a warning log.
- `@dataclass Speaker(id: int, name: str, email: str | None, is_internal: bool)`; `@dataclass Segment(seq: int, speaker_id: int | None, speaker_name: str, start_sec: float, end_sec: float, text: str, word_count: int)`; `@dataclass ParsedTranscript(transcription_uuid: UUID | None, meeting_uuid: UUID | None, modified: datetime | None, speakers: list[Speaker], segments: list[Segment], last_word_sec: float)`; `parse_transcript(raw: Any) -> ParsedTranscript`.
  - Accept a list (use element 0) or a dict. Merge consecutive utterances with the same `speaker_id` into one segment until it would exceed 220 words; `start_sec` = first word time, `end_sec` = last word time of the merged run (if an utterance has no timestamps, inherit the previous end; first segment defaults 0.0). Drop utterances whose text is empty after strip. Email `""` → None. Unknown `speaker_id` → name `Speaker <id>`, not internal.
- `@dataclass NoteSection(heading: str, text: str)`; `@dataclass ParsedNotes(title: str | None, start_at: datetime | None, sections: list[NoteSection], topics: list[str], markdown: str)`; `parse_notes(md: str) -> ParsedNotes`. `topics` = `##` headings excluding (case-insensitive) `Participants`, `Key Takeaways`, `Action Items`, `Next Steps`, `Summary`; trimmed, title-cased, ≤ 80 chars, unique in order.

- [ ] **Step 1: Failing tests:** `test_metadata_first_deduped_file_wins`, `test_metadata_accounts_from_owner_column` (uuid in Alice + Bob CSVs → `["Alice","Bob"]`), `test_metadata_missing_dir_returns_empty`, `test_parse_basic_transcript` (assert exact segment count, first segment speaker/start/end/text from the fixture), `test_merges_same_speaker_runs`, `test_splits_runs_over_220_words`, `test_messy_transcript_unknown_speaker_and_empty_text` (fixture includes speaker_id 9 not in speakers, an empty-text utterance, an utterance with `timestamps: []`, a speaker with `email: ""`), `test_empty_transcript_list` (0 segments, `last_word_sec == 0`), `test_parse_notes_title_date_topics` (topics == `["Spending And Revenue"]` for the fixture), `test_notes_without_title`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): metadata, transcript and notes parsers`.

### Task 6: Ingestion pipeline (scan, process, dedupe, status)

**Files:**
- Create: `app/ingestion/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `S3Store`, `classify_key`, `load_metadata`, `parse_transcript`, `parse_notes`, `Embedder` (Task 8; until then pass `None` and skip embedding).
- Produces:
  - `@dataclass ScanResult(objects_scanned: int, audio_files: int, transcript_files: int, notes_files: int, unknown_files: int, meetings_identified: int, duplicates: int, to_process: list[UUID])`.
  - `scan_bucket(db, store: S3Store, prefixes: list[str], meta: dict[UUID, MeetingMeta], only_failed: bool = False) -> ScanResult`: groups objects by meeting id; if the same id appears under two folders, keep the lexicographically first folder and count the rest in `duplicates`; upserts `meetings` (subject from meta → notes title later → `"Untitled meeting"`; `has_*` flags; `accounts`; `owner_key`; `s3_folder`) and `recordings`. Meetings sharing a non-null `transcription_uuid` with an earlier id: set `duplicate_of`, `ingest_status='skipped'`, count as duplicate. `to_process` = meetings (not skipped) where status ≠ `indexed` **or** stored `transcript_etag`/`notes_etag` differ from S3 (`only_failed=True` → only status `failed`).
  - `process_meeting(db, store, meeting_id: UUID, meta: MeetingMeta | None) -> None`: one transaction: fetch `transcript.json` + `notes.md` (if present), parse, upsert participants (by `normalized_key`; keep first non-null email; `is_internal` true if any source says so), replace this meeting's `meeting_participants` (speaking_sec = Σ(end−start) per speaker) and `transcript_segments` (utterances with `participant_id`, then note sections as `kind='note'`, `start_sec` null, `section`=heading), upsert `transcripts`; fill `start_at`/`duration_sec` fallbacks (notes date; `ceil(last_word_sec)`); set `topics`, `notes_md`, etags, `ingest_status='parsed'`, `parsed_at`. On any exception: rollback, then set `ingest_status='failed'`, `ingest_error` (first 2,000 chars), `ingest_attempts += 1`, and re-raise nothing (return).
  - `embed_meeting(db, embedder: Embedder, meeting_id: UUID) -> int`: embeds segments of that meeting (utterances and notes) with `embedding IS NULL` whose text has ≥ 4 whitespace-separated words; embed text = `f"{subject} | {speaker_name or section}: {text}"` truncated to 8,000 chars; sets status `indexed` + `indexed_at`; returns count. Failure → status `failed` as above.

- [ ] **Step 1: Failing tests** (moto bucket seeded from fixtures + `_bootstrap/ec2_run.log` + one junk key): `test_scan_counts_and_ignores_unknown`, `test_scan_creates_meetings_with_metadata_and_accounts`, `test_duplicate_folder_counted_once`, `test_shared_transcription_uuid_marked_duplicate`, `test_meeting_without_recording_has_flag_false`, `test_process_meeting_writes_segments_participants_notes`, `test_reprocess_is_idempotent` (run twice → same row counts), `test_unchanged_indexed_meeting_not_in_to_process`, `test_changed_etag_requeues`, `test_corrupt_json_marks_failed_and_continues`, `test_never_reads_recordings` (wrap `store.client` and assert no `get_object` on keys ending `.mp3`/`.mp4`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Use `INSERT … ON CONFLICT` for meetings/participants/recordings; delete + bulk insert for a meeting's segments inside the same transaction.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): ingestion pipeline`.

### Task 7: Jobs, worker, ingestion API

**Files:**
- Create: `app/ingestion/jobs.py`, `app/worker.py`, `app/api/routers/ingestion.py`
- Test: `tests/test_jobs.py`, `tests/test_ingestion_api.py`

**Interfaces:**
- Produces: `enqueue_job(db, kind: str, user_id: int | None) -> IngestionJob` (active job exists → `ApiError(409,'job_active')`), `claim_next_job(db) -> IngestionJob | None` (`SELECT … WHERE status='queued' ORDER BY id FOR UPDATE SKIP LOCKED`, sets `running`, `started_at`), `set_status(db, job_id, status)`, `run_job(db_factory, job_id, store, embedder, meta_loader) -> None`.
- `JobOut{id, kind, status, stats, error, requested_by, created_at, started_at, finished_at}`. `stats` keys (all ints): `objects_scanned, audio_files, transcript_files, notes_files, unknown_files, meetings_identified, duplicates, to_process, processed, meetings_parsed, meetings_indexed, meetings_failed`.
- `run_job`: scan (for `retry`, `only_failed=True`) → write scan counters to `stats` (`to_process = len(ScanResult.to_process)`) → for each meeting in `to_process`: re-read job status; if `paused` wait (poll 2 s) until `running`/`cancelled`; `process_meeting` then `embed_meeting`; update `stats.processed`, `meetings_parsed`, `meetings_indexed`, `meetings_failed`, `heartbeat_at` every meeting. Ends `completed` (even with some failed meetings) or `failed` (scan-level error, message in `error`).
- `worker.py`: loop forever: on start, mark jobs stuck in `running` with `heartbeat_at` older than 10 min as `queued` (crash recovery); claim → run; sleep 3 s when idle. Meetings processed with a thread pool of `EMBED_CONCURRENCY` for the embed step only.
- Endpoints (admin): `POST /api/ingestion/start` (kind `initial`), `POST /api/ingestion/sync` (kind `sync`), `POST /api/ingestion/retry` (kind `retry`), `POST /api/ingestion/pause`, `POST /api/ingestion/resume` → `JobOut`. `GET /api/ingestion/status` → `{"current_job": JobOut | null, "last_completed_job": JobOut | null, "totals": {"meetings": int, "indexed": int, "parsed": int, "failed": int, "skipped": int, "discovered": int, "segments": int, "embedded_segments": int}, "failed_meetings": [{"id","subject","error","attempts"}] (≤ 50), "last_sync_at": iso | null, "bucket": str, "prefixes": list[str]}`. Each action writes an audit row.

- [ ] **Step 1: Failing tests:** `test_second_start_returns_409`, `test_claim_skips_locked`, `test_pause_then_resume_finishes_job` (run job in a thread, pause after first meeting, assert `processed` stops growing, resume, assert `completed`), `test_retry_processes_only_failed`, `test_stale_running_job_requeued_on_worker_start`, `test_status_totals_match_db`, `test_standard_user_cannot_start_403`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): ingestion jobs, worker and API`.

## Phase 3 — Search

### Task 8: Embeddings provider

**Files:**
- Create: `app/ai/embeddings.py`
- Modify: `app/worker.py` (build embedder), `app/ingestion/pipeline.py` (no change to signatures)
- Test: `tests/test_embeddings.py`

**Interfaces:**
- `class Embedder(Protocol): dim: int; def embed_documents(self, texts: list[str]) -> list[list[float]]; def embed_query(self, text: str) -> list[float]`.
- `BedrockEmbedder(model_id: str, region: str, dim: int, concurrency: int)`: Titan v2 body `{"inputText": t, "dimensions": dim, "normalize": true}`; `embed_documents` fans out over a thread pool of `concurrency`; on `ThrottlingException` back off (adaptive retries in botocore `Config` + up to 5 manual retries with jitter).
- `FakeEmbedder(dim=1024)`: deterministic — lowercase word tokens, each hashed (`hashlib.blake2b`) to an index, bag-of-words then L2-normalize. Used by tests and `APP_MODE=dev-mock`.
- `get_embedder(settings) -> Embedder`.

- [ ] **Step 1: Failing tests:** `test_fake_embedder_deterministic_and_normalized`, `test_fake_similar_texts_closer` (cos("revenue growth plan","plan for revenue growth") > cos(…,"hello good evening")), `test_bedrock_embedder_request_body` (botocore `Stubber` expects the exact body above and returns a 1024 vector), `test_bedrock_embedder_retries_throttle`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS; extend `test_pipeline.py` with `test_embed_meeting_sets_indexed` using `FakeEmbedder`.
- [ ] **Step 5: Commit** `feat(meeting-intel): Bedrock embeddings`.

### Task 9: Access rules + hybrid search API

**Files:**
- Create: `app/auth/access.py`, `app/search/{schemas.py,service.py}`, `app/api/schemas.py`, `app/api/routers/search.py`
- Test: `tests/test_access.py`, `tests/test_search.py`

**Interfaces:**
- `accessible_meeting_clause(user: User) -> ColumnElement[bool]`: admin or `access_scope=='all'` → `true()`; else `Meeting.accounts.any(user.account_label)` OR EXISTS participant with `lower(email)=user.email` in `meeting_participants`. Always also `Meeting.duplicate_of IS NULL`.
- `ensure_meeting_access(db, user, meeting_id: UUID) -> Meeting` (raises `not_found("meeting")`).
- `api/schemas.py`: `ParticipantRef{id,name,email,is_internal}`, `MeetingSummary{id,subject,start_at,duration_sec,owner_key,has_recording,has_transcript,participant_count,participants: list[ParticipantRef] (≤ 8, internal last),topics}`, `Page[T]{total,page,page_size,items}`.
- `search/schemas.py`:
  - `SearchFilters{participant_ids: list[int]=[], speaker_ids: list[int]=[], owner: str|None, title: str|None, date_preset: Literal["today","7d","30d","6m","1y","all"]|None, date_from: date|None, date_to: date|None, min_duration_min: int|None, max_duration_min: int|None, has_recording: bool|None, has_transcript: bool|None}` (explicit dates override preset; `date_to` inclusive to 23:59:59 UTC).
  - `SearchRequest{q: str = "" (max 2000), filters: SearchFilters = {}, mode: Literal["auto","keyword","semantic"]="auto", sort: Literal["relevance","date_desc","date_asc","duration_desc"]="relevance", page: int ≥1 = 1, page_size: 1..50 = 20}`.
  - `SegmentMatch{segment_id,kind,speaker_name,section,start_sec,text,highlights: list[tuple[int,int]],match_type: Literal["keyword","semantic","both"]}`; `MeetingHit{meeting: MeetingSummary, score: float, match_types: list[str], matches: list[SegmentMatch] (≤ 3)}`; `SearchResponse{total,page,page_size,results: list[MeetingHit],took_ms,semantic_used: bool}`.
- `search(db, user, req: SearchRequest, embedder: Embedder | None) -> SearchResponse`; `suggest(db, user, q: str) -> {"participants": list[ParticipantRef] (≤5), "meetings": list[{"id","subject","start_at"}] (≤5), "recent": list[str] (≤5)}`.
- Algorithm (all candidate queries restricted by the access clause + filters):
  1. Empty `q`: page through filtered meetings; sort `relevance` behaves as `date_desc`; `matches=[]`.
  2. Keyword list (mode ≠ semantic): top 200 segments by `ts_rank_cd(tsv, websearch_to_tsquery('english', q))`.
  3. Semantic list (mode ≠ keyword, embedder present, `q` has ≥ 2 words): top 200 by `embedding <=> :qvec` with distance ≤ `SEMANTIC_MAX_DISTANCE`.
  4. Metadata list: meetings where `id::text = q`, or `subject ILIKE %q%`, or `similarity(subject,q) > 0.3`, or a participant with `name ILIKE %q%` / `email ILIKE %q%` / `similarity(name,q) > 0.4`; ranked by best similarity.
  5. Segment RRF score = Σ 1/(60 + rank) over the lists it appears in; meeting score = sum of its top-3 segment scores + 2 × 1/(60 + metadata rank). Sort meetings by score (or by the requested sort), paginate in Python.
  6. Highlights: run `ts_headline('english', text, query, 'StartSel=\x02,StopSel=\x03,HighlightAll=true')` on returned keyword matches and convert sentinel pairs to `(start,end)` offsets into the plain text; semantic-only matches → one range covering the whole text.
  7. Page 1 with non-empty `q` or any filter → insert `search_history` row.
- Endpoints: `POST /api/search` → `SearchResponse`; `GET /api/search/suggest?q=` → suggest; `GET /api/search/history?limit=20` → `[{id, query, filters, result_count, created_at}]` (own rows only).

- [ ] **Step 1: Failing tests** (seed 4 meetings via `process_meeting` + `FakeEmbedder`; users: admin, Alice `account_label='Alice'`, Carol with email matching a participant, Dave with no access): `test_admin_sees_all`, `test_account_label_access`, `test_participant_email_access`, `test_no_access_user_gets_zero_results`, `test_keyword_search_finds_and_highlights` (assert highlight range text == "revenue"), `test_semantic_search_matches_paraphrase`, `test_meeting_uuid_query_returns_that_meeting`, `test_person_partial_name`, `test_filters_combined_participant_and_date_and_keyword`, `test_date_preset_7d`, `test_empty_q_lists_by_date`, `test_special_characters_no_500` (parametrized: `'"unclosed'`, `"a & | ! ( ) :*"`, `"🙂"`, `"x"*2000`), `test_pagination_totals`, `test_history_written_once_and_own_only`, `test_suggest_respects_access`, `test_duplicate_meetings_excluded`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): access rules and hybrid search`.

## Phase 4 — Read APIs and dashboard UI

### Task 10: Meetings, participants, dashboard and analytics APIs

**Files:**
- Create: `app/api/routers/{meetings.py,participants.py,dashboard.py,analytics.py}`
- Test: `tests/test_meetings_api.py`, `tests/test_participants_api.py`, `tests/test_dashboard_api.py`

**Interfaces:**
- `GET /api/meetings?page&page_size&sort(date_desc|date_asc|duration_desc|title)&title&participant_id&owner&date_from&date_to&has_recording` → `Page[MeetingSummary]`.
- `GET /api/meetings/{id}` → `MeetingDetail = MeetingSummary + {participants: list[ParticipantRef + speaking_sec] (all), notes_md, recordings: list[{kind,size_bytes}], transcript: {segment_count,word_count} | null, ingest_status, accounts}`.
- `GET /api/meetings/{id}/transcript` → `{meeting_id, speakers: list[ParticipantRef + speaking_sec], segments: list[{id,seq,speaker_name,participant_id,start_sec,end_sec,text}]}` (utterances only, ordered by `seq`); no transcript → 404 `transcript_not_found`.
- `GET /api/meetings/{id}/recording?kind=audio|video&download=false` → `{url, expires_at, content_type, kind}`; content types `audio/mpeg`, `video/mp4`; `download=true` requires `can_download` or admin (403 `download_not_allowed`) and sets disposition `"<subject>-<YYYY-MM-DD>.<ext>"` (filename sanitised to `[A-Za-z0-9 ._-]`); missing → 404 `recording_not_found`; writes audit `recording.access` with kind + download flag.
- `GET /api/participants?q&internal&page&page_size&sort(meetings_desc|name|last_seen)` → `Page[{id,name,email,is_internal,meeting_count,speaking_sec,first_meeting_at,last_meeting_at}]` (counts over accessible meetings; participants with 0 accessible meetings omitted).
- `GET /api/participants/{id}` → the row above + `meetings: Page[MeetingSummary]` (first 20, date desc) + `mentions: list[{meeting_id,subject,start_at,segment_id,start_sec,speaker_name,text}]` (≤ 30 segments in accessible meetings whose `tsv` matches the participant's first name, spoken by someone else).
- `GET /api/dashboard/stats` → `{total_meetings, total_recordings (meetings with audio), total_participants, total_transcripts, audio_storage_bytes (Σ audio), video_storage_bytes (Σ video), total_duration_sec, meetings_by_month: [{month:"YYYY-MM", count}], top_participants: [{id,name,count}] (10, external + internal), top_topics: [{topic,count}] (10), recent_meetings: list[MeetingSummary] (5), search_activity: [{date:"YYYY-MM-DD", count}] (last 30 days, zero-filled)}`, scoped to accessible meetings, cached 60 s per access scope key (`cachetools.TTLCache`).
- `GET /api/analytics?date_from&date_to` → `{hours_by_month: [{month, hours}], meetings_by_owner: [{owner, count}], speaking_leaders: [{participant_id,name,hours}] (15), topics_by_month: [{month, topic, count}] (top 6 topics overall), internal_vs_external_speaking: {internal_hours, external_hours}}`.

- [ ] **Step 1: Failing tests:** `test_meeting_detail_404_for_inaccessible`, `test_transcript_ordered_with_speakers`, `test_recording_presign_audio_content_type`, `test_recording_missing_404`, `test_download_requires_permission_403`, `test_recording_access_audited`, `test_meetings_list_filters_and_sort`, `test_participants_counts_scoped_to_access`, `test_participant_detail_mentions`, `test_participant_with_no_accessible_meetings_404`, `test_dashboard_stats_values` (exact numbers for the seeded fixtures), `test_dashboard_scoped_for_standard_user`, `test_analytics_shapes`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): meetings, participants, dashboard APIs`.

### Task 11: Frontend foundation (layout, theme, auth, API client)

**Files:**
- Create: `meeting-intel/frontend/*` via `pnpm create next-app@latest frontend --ts --tailwind --eslint --app --src-dir --use-pnpm --import-alias "@/*"`, then `pnpm dlx shadcn@latest init` and add components: button input label card badge dialog command popover calendar select dropdown-menu table tabs skeleton slider sheet separator tooltip sonner avatar scroll-area switch checkbox.
- Create: `next.config.ts` (rewrite `/api/:path*` → `${BACKEND_URL}/api/:path*`; `output: "standalone"`), `middleware.ts`, `Dockerfile`, `vitest.config.ts`, `src/lib/{api.ts,types.ts,format.ts}`, `src/components/{app-sidebar.tsx,dev-banner.tsx,empty-state.tsx,error-state.tsx,theme-toggle.tsx}`, `src/app/login/page.tsx`, `src/app/(app)/layout.tsx`, `src/app/providers.tsx`
- Modify: `meeting-intel/docker-compose.yml` (frontend service, `3000:3000`, `BACKEND_URL=http://backend:8000`)
- Test: `src/lib/api.test.ts`, `src/lib/format.test.ts`

**Interfaces:**
- `class ApiError extends Error {status: number; code: string; details?: unknown}`; `apiFetch<T>(path: string, init?: RequestInit & {json?: unknown}) -> Promise<T>` (sends `credentials: "include"`; parses the error envelope; on 401 from any path except `/api/auth/*` redirects to `/login?next=<current>`).
- `types.ts` mirrors every backend response model named in Tasks 3, 7, 9, 10 (same field names, snake_case).
- `format.ts`: `formatDuration(sec: number | null) -> string` (`"1h 05m"`, `"42m"`, `"—"`), `formatTimestamp(sec: number) -> string` (`"4:05"`, `"1:02:09"`), `formatBytes(n: number) -> string` (`"53.3 GB"`), `formatDate(iso: string) -> string` (locale date + time).
- `middleware.ts`: no `mi_session` cookie → redirect to `/login` for every route except `/login`, `/_next/*`, `/api/*`, static files.
- Layout: left sidebar (collapsible; sheet on < 768 px) with the 8 items in spec order — Overview, Search Meetings, All Meetings, Participants, AI Assistant, Analytics, Data Ingestion, Settings — hide Data Ingestion for non-admins; top bar with the global search trigger (Task 12), theme toggle (light/dark/system via `next-themes`), user menu with sign-out. `DevBanner` shows when `GET /api/system/info` (public, returns `{app_mode}`; add to `system.py`) says `dev-mock`.
- Visual style: neutral zinc palette, Inter via `next/font`, 14 px base, 8 px spacing grid, subtle borders, no heavy shadows (Linear/Stripe feel).

- [ ] **Step 1: Failing tests:** `api.test.ts` — parses `{"error":{"code":"not_found","message":"…"}}` into `ApiError` with `status 404, code "not_found"`; non-JSON 502 → `code "bad_gateway"`; JSON body sent with `content-type: application/json`. `format.test.ts` — exact strings above, plus `formatDuration(0) === "0m"`, `formatTimestamp(59.9) === "0:59"`.
- [ ] **Step 2: Run** `pnpm test` → FAIL.
- [ ] **Step 3: Implement**; login page posts to `/api/auth/login`, shows `invalid_credentials` message inline, then `router.replace(next ?? "/overview")`.
- [ ] **Step 4: Run** `pnpm test` and `pnpm build` → PASS. Manual: `docker compose up` → login with bootstrap admin works, sidebar renders in light and dark.
- [ ] **Step 5: Commit** `feat(meeting-intel): frontend foundation`.

### Task 12: Global search, Search page, filters, results

**Files:**
- Create: `src/lib/search-params.ts`, `src/components/{global-search.tsx,filter-bar.tsx,result-card.tsx,highlight-text.tsx}`, `src/app/(app)/search/page.tsx`
- Test: `src/lib/search-params.test.ts`, `src/components/highlight-text.test.tsx`

**Interfaces:**
- `searchParamsToRequest(p: URLSearchParams) -> SearchRequest` and `requestToSearchParams(r: SearchRequest) -> URLSearchParams` (keys: `q, mode, sort, page, participants (comma ids), speakers, owner, title, preset, from, to, mindur, maxdur, rec (1/0), tx (1/0)`; defaults omitted). Round-trip must be lossless.
- `<HighlightText text: string, ranges: [number, number][], variant: "keyword" | "semantic" />` — renders text with `<mark>` for ranges (React nodes; never `dangerouslySetInnerHTML`), merging overlaps; `semantic` uses a softer underline style.
- `<GlobalSearch />` — Ctrl/⌘+K opens a command dialog: as you type (debounce 200 ms) shows `suggest` groups People / Meetings / Recent searches; Enter → `/search?q=…`; picking a person → `/search?participants=<id>`; picking a meeting → `/meetings/<id>`.
- Search page: big search input at top, mode toggle (Auto / Keyword / Meaning), `FilterBar` (participant multi-select using `/api/participants?q=`, speaker multi-select, owner, title, date presets Today/7d/30d/6m/1y/All + custom range calendar, duration min/max, recording/transcript toggles, a "Clear all" button and per-filter removable chips), sort select, results list of `ResultCard`, pagination. URL is the source of truth. States: skeleton while loading, empty state ("No meetings match. Try fewer filters or different words."), error state with retry.
- `ResultCard` shows: subject (link), meeting ID (short, copy button), date, duration, participant avatars/names (+N), recording/transcript badges, up to 3 matches each with speaker, `formatTimestamp(start_sec)` link to `/meetings/<id>?t=<start_sec>`, `HighlightText`.

- [ ] **Step 1: Failing tests:** round-trip test for a request using every field; defaults produce empty params; `HighlightText` marks exactly "revenue" in "Revenue grew" for range `[0,7]`, merges `[[0,3],[2,5]]`, escapes `<script>` text as text.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** tests + `pnpm build` → PASS. Manual: search with filters, refresh keeps state, back button restores previous search.
- [ ] **Step 5: Commit** `feat(meeting-intel): search UI`.

### Task 13: All Meetings list, Meeting details, audio player, transcript viewer

**Files:**
- Create: `src/lib/transcript.ts`, `src/components/{audio-player.tsx,transcript-viewer.tsx}`, `src/app/(app)/meetings/page.tsx`, `src/app/(app)/meetings/[id]/page.tsx`
- Test: `src/lib/transcript.test.ts`, `src/components/audio-player.test.tsx`

**Interfaces:**
- `findActiveSegment(segments: {start_sec: number}[], t: number) -> number` (binary search; index of last segment with `start_sec <= t`, `-1` before the first).
- `filterSegments(segments, query: string) -> {index: number, ranges: [number, number][]}[]` (case-insensitive substring matches).
- `<AudioPlayer meetingId: string, initialTime?: number, canDownload: boolean, onTimeUpdate(t: number), ref exposes {seek(t: number), play()} />` — fetches `/api/meetings/{id}/recording?kind=audio`; controls: play/pause, seek bar, current/total time, volume + mute, speed (0.75, 1, 1.25, 1.5, 1.75, 2), download (only if `canDownload`; fetches `download=true` URL). On `<audio>` `error` (expired URL): refetch URL once, restore `currentTime`, keep playing state. Keyboard: Space play/pause, ←/→ ±5 s when focused.
- `<TranscriptViewer segments, activeIndex, onSeek(t) />` — virtualized list (`@tanstack/react-virtual`); each row: speaker name (colour per speaker), `formatTimestamp`, text; active row highlighted and auto-scrolled into view unless the user scrolled in the last 4 s; search box with match count and next/prev; clicking a row calls `onSeek(start_sec)`.
- Meeting page: header (subject, ID with copy, date/time, duration, owner, participants list with internal/external tag and speaking time), tabs **Transcript** / **Notes** (render `notes_md` with `react-markdown`, no raw HTML) — notes tab shows Key Takeaways and Action Items as written by Avoma. Player sticky at the top of the transcript column; `?t=` seeks on load. No recording → "No recording available" card, transcript still shown. Meetings list page: table (`Page[MeetingSummary]`) with sort, title filter, date range, has-recording toggle, pagination.
- Admin/`can_download` users see download buttons for audio and video.

- [ ] **Step 1: Failing tests:** `findActiveSegment` (empty list → -1; t before first → -1; exact start → that index; between → previous; after last → last); `filterSegments` counts; `audio-player.test.tsx` — mock fetch + `HTMLMediaElement`: on `error` event refetches the URL once and restores `currentTime` to the previous value; download button hidden when `canDownload=false`; a 404 `recording_not_found` response renders "No recording available" and no controls.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** tests + `pnpm build` → PASS. Manual on real data (after Task 18 ingestion or a partial run): clicking a line jumps audio; playback moves the highlight.
- [ ] **Step 5: Commit** `feat(meeting-intel): meeting details, player and transcript`.

### Task 14: Overview, Analytics and Participants pages

**Files:**
- Create: `src/components/stat-card.tsx`, `src/app/(app)/overview/page.tsx`, `src/app/(app)/analytics/page.tsx`, `src/app/(app)/participants/page.tsx`, `src/app/(app)/participants/[id]/page.tsx`
- Test: `src/components/stat-card.test.tsx`

**Interfaces:**
- Overview (`/api/dashboard/stats`): stat cards — Meetings, Recordings, Participants, Transcripts, Audio storage (`formatBytes`), Total duration (hours); charts — meetings by month (bar), top participants (horizontal bar), top topics (horizontal bar), search activity last 30 days (line); recent meetings list. Each chart: one series colour, axis labels with units, tooltips, empty state when no data.
- Analytics (`/api/analytics` + date range picker): hours by month (bar), meetings by owner (horizontal bar), speaking leaders (horizontal bar, hours), topics by month (line per topic, ≤ 6), internal vs external speaking (two-number stat, not a pie).
- Participants: searchable, sortable table (name, email, internal/external, meetings, speaking time, first/last meeting), pagination. Detail: header stats, meetings table, "Mentions" list linking to `/meetings/<id>?t=<start_sec>`.
- Skeletons for every async block.

- [ ] **Step 1: Failing test:** `StatCard` renders label, formatted value and a skeleton when `loading`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Load the `dataviz` skill before writing chart code.
- [ ] **Step 4: Run** tests + `pnpm build` → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): overview, analytics, participants`.

### Task 15: Admin ingestion panel and Settings

**Files:**
- Create: `src/app/(app)/ingestion/page.tsx`, `src/app/(app)/settings/page.tsx`
- Test: `src/app/(app)/ingestion/progress.test.ts` (pure helper in `src/lib/ingestion.ts`)

**Interfaces:**
- `progressPercent(stats: Record<string, number>) -> number` (`processed / to_process`, 0 when unknown, capped at 100).
- Ingestion page (admin; non-admin gets the 403 error state): AWS connection card from `/api/system/status` (OK / error text, bucket, region, prefixes, models); counters from `/api/ingestion/status` (objects scanned, audio files, transcript files, meetings identified, indexed, failed, duplicates, last sync time); progress bar; buttons Start initial ingestion / Pause / Resume / Retry failed / Start incremental sync, enabled according to `current_job.status`; failed meetings table with error text; polls every 3 s while a job is active, 30 s otherwise. No button can delete anything.
- Settings: Profile (name, email, role, theme). Admin-only Users section: table + create/edit dialog for `email, name, password, role, access_scope, account_label (select from distinct meeting accounts via `GET /api/meetings/accounts` → `list[str]`; add to meetings router), can_download, is_active`.

- [ ] **Step 1: Failing test:** `progressPercent` (`{processed: 5, to_process: 10}` → 50; missing → 0; overflow → 100).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** (+ backend `GET /api/meetings/accounts` with a test `test_accounts_list_admin_only`; declare this route before `/api/meetings/{id}`).
- [ ] **Step 4: Run** tests + `pnpm build` → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): ingestion panel and settings`.

## Phase 5 — AI

### Task 16: AI assistant backend

**Files:**
- Create: `app/ai/{chat.py,assistant.py}`, `app/api/routers/ai.py`
- Test: `tests/test_assistant.py`

Model: GLM 5 via Bedrock Converse with `toolConfig` (verified: returns `stopReason: "tool_use"` with correct `toolUse.input`). GLM may add `reasoningContent` blocks to `output.message.content`; keep them in the message history sent back to the model but never show them to users or parse citations from them. Read only `text` blocks for the answer.

**Interfaces:**
- `class ChatModel(Protocol): model_id: str; def converse(self, system: str, messages: list[dict], tools: list[dict] | None, max_tokens: int) -> dict` (returns the raw Converse `output.message` + `stopReason`). `BedrockChatModel(model_id, region)`; `FakeChatModel(script: list[dict])` replays scripted turns.
- `AskRequest{question: str (1..2000), filters: SearchFilters | None, history: list[{role: "user"|"assistant", content: str}] (≤ 6)}`; `Citation{n: int, meeting_id, subject, start_at, speaker_name, start_sec, segment_id, excerpt}`; `AskResponse{answer_markdown: str, citations: list[Citation], evidence_found: bool, model: str, took_ms: int}`.
- `ask(db, user, req, embedder, chat) -> AskResponse`:
  - One tool `search_meetings{query: str, speaker: str?, participant: str?, date_from: "YYYY-MM-DD"?, date_to?, limit: int ≤ 15}`; the handler resolves `speaker`/`participant` names to participant ids via trigram similarity (> 0.4, accessible meetings only), runs `search()` with the user's access and request filters merged, and returns numbered sources (global counter across calls) each with subject, date, speaker, timestamp and the segment text plus the previous and next segment for context.
  - Loop at most 4 tool rounds, then force a final answer without tools.
  - System prompt (exact intent): answer only from the numbered sources; cite every claim as `[n]`; if sources do not contain the answer say so plainly; never invent names, dates, numbers or meetings; group by meeting when comparing; today's date is given.
  - If the tool returned zero sources in total → skip the final call and return `answer_markdown = "I couldn't find anything in the meeting archive about that."`, `evidence_found = false`, `citations = []`.
  - `citations` = only sources whose `[n]` appears in the answer, in order of first appearance; markers pointing at unknown numbers are removed from the text.
- `POST /api/ai/ask` → `AskResponse` (any signed-in user); Bedrock errors → 502 `ai_unavailable`.

- [ ] **Step 1: Failing tests** (FakeChatModel + FakeEmbedder + seeded meetings): `test_ask_returns_cited_sources_only`, `test_unknown_citation_number_stripped`, `test_no_evidence_skips_model_and_says_so`, `test_tool_results_respect_access` (Dave asks → zero sources even though the text exists), `test_speaker_name_resolved_to_filter`, `test_tool_round_limit_forces_final_answer`, `test_bedrock_error_returns_502`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS. Live check (manual, after real ingestion): ask "Which meetings discussed revenue?" → answer with ≥ 1 citation whose meeting opens.
- [ ] **Step 5: Commit** `feat(meeting-intel): AI assistant with citations`.

### Task 17: AI assistant UI

**Files:**
- Create: `src/app/(app)/assistant/page.tsx`, `src/components/citation-list.tsx`, `src/lib/citations.ts`
- Test: `src/lib/citations.test.ts`

**Interfaces:**
- `splitCitations(markdown: string) -> ({type: "text", value: string} | {type: "cite", n: number})[]`.
- Page: chat thread (user/assistant bubbles), input with Enter to send / Shift+Enter newline, example questions from the spec as starter chips, optional filter popover (date preset + participant) passed as `filters`, "Searching the archive…" state, answer rendered as markdown with `[n]` turned into small superscript buttons that scroll to the citation; citation cards show subject, date, speaker, timestamp, excerpt, and **Open recording at 4:05** → `/meetings/<id>?t=<start_sec>`. `evidence_found=false` → neutral "No matching evidence" callout. Conversation kept in page state (last 6 turns sent as `history`).

- [ ] **Step 1: Failing test:** `splitCitations("Revenue grew [1][3].")` → text, cite 1, cite 3, text "."; ignores `[x]` and `[10a]`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** tests + `pnpm build` → PASS.
- [ ] **Step 5: Commit** `feat(meeting-intel): AI assistant UI`.

## Phase 6 — Production

### Task 18: Hardening, dev-mock mode, docs, real ingestion and verification

**Files:**
- Create: `app/devseed.py`, `infra/iam-policy.json`, `docs/deployment.md`
- Modify: `README.md`, `docker-compose.yml` (prod profile: no source mounts, `restart: unless-stopped`, healthchecks), `app/main.py` (simple per-user rate limit on `/api/ai/ask`: 20/min → 429 `rate_limited`)
- Test: `tests/test_devseed.py`, `tests/test_rate_limit.py`

**Interfaces:**
- `seed_dev_data(db) -> int` — only when `APP_MODE=dev-mock` (otherwise raises); creates 5 meetings with subjects `[SAMPLE] …`, synthetic participants/segments, embeddings via `FakeEmbedder`; idempotent.
- `iam-policy.json`: `s3:ListBucket` on `arn:aws:s3:::${S3_BUCKET}` (placeholder text, user fills in), `s3:GetObject` on `arn:aws:s3:::${S3_BUCKET}/*`, `bedrock:InvokeModel` on the Titan embedding model ARN and the `zai.glm-5` model ARN in `ap-south-1`. No write actions.
- `README.md`: what it is, prerequisites, `cp .env.example .env`, `docker compose up -d`, first login, how to run ingestion, tests, dev-mock mode, troubleshooting (AWS status card, Bedrock access).
- `deployment.md`: options (single EC2 with compose, or ECS Fargate + RDS Postgres with pgvector), required IAM role, env vars, HTTPS (`COOKIE_SECURE=true`), backups, CloudWatch logs (JSON logs to stdout → awslogs driver). Not executed.

- [ ] **Step 1: Failing tests:** `test_devseed_refuses_in_production`, `test_devseed_idempotent_and_labelled`, `test_ai_rate_limit_429`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**, then run the full suites: `uv run pytest` and `pnpm test && pnpm build` → all PASS.
- [ ] **Step 4: Real ingestion (verification, not a test).** Bring up the stack with the real bucket; Start initial ingestion from the UI; wait for `completed`. Verify with SQL and record the numbers in the final report:
  - `SELECT count(*) FROM meetings WHERE duplicate_of IS NULL` → expect **3,152** (minus any genuine duplicates found, each explained).
  - `… WHERE has_recording` → **3,084**; `… WHERE has_transcript` → **3,152**; `… WHERE has_notes` → **3,109**.
  - `SELECT ingest_status, count(*) FROM meetings GROUP BY 1` → all `indexed` except listed failures (each failure's error reviewed).
  - `SELECT count(*) FROM transcript_segments WHERE embedding IS NULL AND kind='utterance' AND array_length(regexp_split_to_array(text,'\s+'),1) >= 4` → **0**.
  - Run **Start incremental sync** again → `to_process` is 0 and it finishes in under 2 minutes (no reprocessing).
  - Spot-check 3 real meetings in the UI: transcript matches `transcript.json`, audio plays, clicking a line seeks.
  - Run each of the spec's 5 semantic example queries and the AI example questions; note which return useful results; tune `SEMANTIC_MAX_DISTANCE` if semantic hits are empty or noisy, and record the final value.
  - Do not report ingestion as complete unless every check above was run and its output is shown.
- [ ] **Step 5: Commit** `feat(meeting-intel): hardening, docs, verification`.
