# Deploying to AWS

Nothing here has been run. It is a guide for when you decide on hosting and cost.

## Why host it in AWS

The archive and Bedrock are in `ap-south-1`. From a home connection (~200 KB/s) the first full embedding pass takes
hours; inside AWS it takes minutes, and audio streams straight from S3 to the viewer either way.

## Option A — one EC2 instance with Docker Compose (simplest)

- Instance: `t3.large` (2 vCPU, 8 GB) in `ap-south-1`, 50 GB gp3. About $65/month on demand.
- Attach an **IAM role** with `infra/iam-policy.json` (replace `REPLACE_WITH_S3_BUCKET`). Do not put access keys in `.env`.
- Install Docker, copy this folder plus `../data/metadata/` (keeping the same relative layout), set `.env` (`COOKIE_SECURE=true`), `docker compose up -d --build`.
- Put it behind HTTPS: an Application Load Balancer with an ACM certificate (or Caddy on the instance) forwarding to port 3100.
- Back up the `pgdata` volume with daily EBS snapshots (Data Lifecycle Manager).

## Option B — managed services (more robust)

| Piece | Service |
| --- | --- |
| Database | RDS for PostgreSQL 17 (`db.t4g.medium`, pgvector is supported), encryption at rest on, automated backups |
| API + worker | ECS Fargate: one service for `backend` (2 tasks), one for `worker` (1 task); same image, different command |
| Frontend | ECS Fargate service from `frontend/Dockerfile`, `BACKEND_URL` = internal API address |
| Entry point | ALB with ACM certificate; route all traffic to the frontend (it forwards `/api/*` to the API) |
| Secrets | `JWT_SECRET`, admin bootstrap, DB password in Secrets Manager, injected as env vars |
| Permissions | Task role with `infra/iam-policy.json` |
| Logs | `awslogs` driver → CloudWatch Logs (the API and worker already log one JSON object per line) |
| Alarms | CloudWatch alarms on 5xx rate, worker task restarts, RDS CPU/storage |

Run migrations once per release: `alembic upgrade head` (the backend container already does this on start).

## Settings to change for production

| Variable | Value |
| --- | --- |
| `COOKIE_SECURE` | `true` (HTTPS only) |
| `JWT_SECRET` | a new random value (not the local one) |
| `APP_MODE` | `production` |
| `ADMIN_PASSWORD` | strong; change it after first sign-in |

Encryption: S3 and RDS encrypt at rest; TLS is terminated at the ALB; presigned audio links expire after 15 minutes.
