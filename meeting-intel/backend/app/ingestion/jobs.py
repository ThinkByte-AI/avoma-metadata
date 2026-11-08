"""Postgres-backed ingestion jobs: enqueue, claim, pause/resume, run."""
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.aws.s3 import S3Store
from app.config import get_settings
from app.errors import ApiError
from app.ingestion.metadata import MeetingMeta
from app.ingestion.pipeline import process_meeting, scan_bucket
from app.models import IngestionJob

log = logging.getLogger("app.ingestion.jobs")

ACTIVE_STATUSES = ("queued", "running", "paused")
STALE_AFTER = timedelta(minutes=10)


def active_job(db: Session) -> IngestionJob | None:
    return db.scalar(select(IngestionJob).where(IngestionJob.status.in_(ACTIVE_STATUSES)).order_by(IngestionJob.id))


def enqueue_job(db: Session, kind: str, user_id: int | None) -> IngestionJob:
    if active_job(db) is not None:
        raise ApiError(409, "job_active", "An ingestion job is already queued or running.")
    job = IngestionJob(kind=kind, status="queued", requested_by=user_id, stats={})
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "job_active", "An ingestion job is already queued or running.") from None
    return job


def claim_next_job(db: Session) -> IngestionJob | None:
    job = db.scalar(
        select(IngestionJob)
        .where(IngestionJob.status == "queued")
        .order_by(IngestionJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        db.rollback()
        return None
    now = datetime.now(UTC)
    job.status, job.heartbeat_at = "running", now
    job.started_at = job.started_at or now
    db.commit()
    return job


def set_status(db: Session, job_id: int, status: str) -> IngestionJob:
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise ApiError(404, "not_found", "Job not found")
    if status == "running" and job.started_at is None:
        status = "queued"  # resumed before the worker ever picked it up
    job.status = status
    if status in ("completed", "failed", "cancelled"):
        job.finished_at = datetime.now(UTC)
    db.commit()
    return job


def requeue_stale_jobs(db: Session, older_than: timedelta = STALE_AFTER) -> int:
    """A job left 'running' by a worker that died goes back to the queue."""
    cutoff = datetime.now(UTC) - older_than
    res = db.execute(
        update(IngestionJob)
        .where(IngestionJob.status == "running", IngestionJob.heartbeat_at < cutoff)
        .values(status="queued")
    )
    db.commit()
    return res.rowcount or 0


def _current_status(db: Session, job_id: int) -> str:
    return db.scalar(select(IngestionJob.status).where(IngestionJob.id == job_id))


def _wait_while_paused(db: Session, job_id: int, poll_sec: float) -> str:
    while True:
        status = _current_status(db, job_id)
        db.commit()
        if status != "paused":
            return status
        db.execute(update(IngestionJob).where(IngestionJob.id == job_id).values(heartbeat_at=datetime.now(UTC)))
        db.commit()
        time.sleep(poll_sec)


def _save(db: Session, job_id: int, stats: dict, **values: Any) -> None:
    db.execute(
        update(IngestionJob)
        .where(IngestionJob.id == job_id)
        .values(stats=dict(stats), heartbeat_at=datetime.now(UTC), **values)
    )
    db.commit()


def run_job(
    db_factory: sessionmaker,
    job_id: int,
    store: S3Store,
    embedder: Any,
    meta_loader: Callable[[], dict],
    poll_sec: float = 2.0,
) -> None:
    prefixes = get_settings().s3_prefix_list
    with db_factory() as db:
        job = db.get(IngestionJob, job_id)
        if job is None:
            return
        try:
            meta: dict[Any, MeetingMeta] = meta_loader()
            scan = scan_bucket(db, store, prefixes, meta, only_failed=(job.kind == "retry"))
            stats = {k: v for k, v in scan.__dict__.items() if k != "to_process"}
            stats.update(to_process=len(scan.to_process), processed=0, meetings_parsed=0,
                         meetings_indexed=0, meetings_failed=0)
            _save(db, job_id, stats)

            cancelled = False
            for mid in scan.to_process:
                if _wait_while_paused(db, job_id, poll_sec) == "cancelled":
                    cancelled = True
                    break
                ok = process_meeting(db, store, mid, meta.get(mid))
                if ok:
                    stats["meetings_parsed"] += 1
                    if embedder is not None:
                        from app.ingestion.pipeline import embed_meeting  # noqa: PLC0415

                        ok = embed_meeting(db, embedder, mid)
                        stats["meetings_indexed"] += ok
                stats["meetings_failed"] += not ok
                stats["processed"] += 1
                _save(db, job_id, stats)

            final = "cancelled" if cancelled else "completed"
            _save(db, job_id, stats, status=final, finished_at=datetime.now(UTC))
            log.info("job finished", extra={"job_id": job_id, "status": final, **stats})
        except Exception as e:
            db.rollback()
            log.exception("job failed", extra={"job_id": job_id})
            db.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(status="failed", error=f"{type(e).__name__}: {e}"[:2000], finished_at=datetime.now(UTC))
            )
            db.commit()
