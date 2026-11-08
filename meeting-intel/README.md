# Meeting Intelligence Dashboard

Search, read, listen to and ask questions about the Avoma meeting archive stored in S3.

- `backend/` — FastAPI API + ingestion worker (Python 3.13, Postgres + pgvector, Bedrock)
- `frontend/` — Next.js dashboard
- `docker-compose.yml` — local stack (db, backend, worker, frontend)

## Quick start (local)

```bash
cp .env.example .env        # fill in S3_BUCKET, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD
docker compose up -d
```

AWS credentials come from the standard AWS chain. For local dev, compose also reads `../.env`
(the archive repo's key file) if it exists.

## Tests

```bash
docker compose up -d db
cd backend && uv run pytest
```

Design and plan: `../docs/superpowers/specs/2026-11-08-meeting-intel-design.md`,
`../docs/superpowers/plans/2026-11-08-meeting-intel.md`.
