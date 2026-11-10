# Meeting Intelligence Dashboard

Search, read, listen to and ask questions about the Avoma meeting archive stored in S3.

| Part | What it is |
| --- | --- |
| `backend/` | FastAPI API + ingestion worker (Python 3.13, Postgres 17 + pgvector, Amazon Bedrock) |
| `frontend/` | Next.js 16 dashboard (React 19, Tailwind, shadcn/ui, Recharts) |
| `docker-compose.yml` | Local stack: `db`, `backend`, `worker`, `frontend` |
| `infra/iam-policy.json` | Least-privilege AWS policy for the app (S3 read + Bedrock invoke) |
| `docs/deployment.md` | How to host it on AWS |

## How it works

1. **Ingestion** (worker) lists `s3://$S3_BUCKET/$S3_PREFIXES`, classifies every object, and for each meeting folder
   (`avoma/<YYYY>/<MM>/<meeting-uuid>/`) reads `transcript.json` and `notes.md`. Recordings are never downloaded.
   Titles, dates, durations and owners come from the CSVs in `../data/metadata` (mounted at `METADATA_DIR`).
2. Pass 1 stores meetings, participants, speaker turns (keyword search) and Avoma's notes.
   Pass 2 embeds ~150-word conversation windows and note sections with Titan v2 (512 dims) for meaning-based search.
3. **Search** fuses Postgres full-text, trigram name/title matching and pgvector similarity (Reciprocal Rank Fusion),
   grouped by meeting, filtered by the viewer's access.
4. **AI assistant** (GLM 5 on Bedrock) calls a search tool, then answers only from numbered passages and cites them.
5. **Playback** uses 15-minute presigned S3 links to `recording.mp3`; the transcript follows the audio.

Access: admins see everything. Standard users see meetings that appeared in their Avoma account (`account_label`)
or that they attended (their email), unless an admin gives them "all meetings" scope.

## Run it locally

Prerequisites: Docker Desktop, AWS credentials that can read the bucket and call Bedrock in `ap-south-1`.

```bash
cp .env.example .env     # set S3_BUCKET, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD (10+ chars)
docker compose up -d --build
```

- App: http://localhost:3100 (sign in with ADMIN_EMAIL / ADMIN_PASSWORD; the first admin is created on startup)
- API docs: http://localhost:8000/api/docs
- AWS credentials: the standard chain (env vars, profile, or IAM role). Compose also reads `../.env` if present.

Then open **Data Ingestion → Start initial ingestion**. Keyword search works as soon as pass 1 reaches a meeting;
meaning-based search and the assistant improve as pass 2 completes. Re-run **Start incremental sync** any time:
unchanged meetings are skipped (S3 ETags).

Frontend without Docker: `cd frontend && pnpm install && BACKEND_URL=http://localhost:8000 PORT=3100 pnpm dev`.

## Tests

```bash
docker compose up -d db
cd backend && uv run pytest          # API, ingestion, search, assistant (uses database meeting_intel_test)
cd frontend && pnpm test             # components and helpers (Vitest)
```

## Development mode with sample data

Set `APP_MODE=dev-mock`. The API then creates five meetings titled `[SAMPLE] …` and every page shows a
"Development mode — sample data" banner. Never use this with the real archive.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Data Ingestion shows AWS "error" | Credentials, bucket name, region; `docker compose logs worker` |
| Search works but "meaning" results are missing | Pass 2 not finished yet; Bedrock access to `amazon.titan-embed-text-v2:0` |
| Assistant says it is unavailable | Bedrock access to `zai.glm-5` in `ap-south-1`; rate limit is 20 questions/min/user |
| Audio does not play | The meeting has no `recording.mp3`, or the browser blocked the S3 domain |
| Slow ingestion | Embedding is download-bound (~20 KB per window); hosting in AWS makes it minutes |

Design and plan: `../docs/superpowers/specs/2026-11-08-meeting-intel-design.md`,
`../docs/superpowers/plans/2026-11-08-meeting-intel.md`.
