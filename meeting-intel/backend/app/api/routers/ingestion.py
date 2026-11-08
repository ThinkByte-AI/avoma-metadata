from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth.deps import client_ip, require_admin
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.ingestion.jobs import active_job, enqueue_job, set_status
from app.models import IngestionJob, Meeting, TranscriptSegment, User

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    status: str
    stats: dict
    error: str | None
    requested_by: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def _enqueue(kind: str, action: str, request: Request, admin: User, db: Session) -> IngestionJob:
    job = enqueue_job(db, kind, admin.id)
    write_audit(db, admin.id, action, "ingestion_job", str(job.id), {"kind": kind}, client_ip(request))
    db.commit()
    return job


@router.post("/start", response_model=JobOut)
def start(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _enqueue("initial", "ingestion.start", request, admin, db)


@router.post("/sync", response_model=JobOut)
def sync(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _enqueue("sync", "ingestion.sync", request, admin, db)


@router.post("/retry", response_model=JobOut)
def retry(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _enqueue("retry", "ingestion.retry", request, admin, db)


def _change(status_from: tuple[str, ...], status_to: str, action: str, request: Request, admin: User, db: Session):
    job = active_job(db)
    if job is None or job.status not in status_from:
        raise ApiError(404, "no_active_job", f"There is no job that can be {status_to}.")
    job = set_status(db, job.id, status_to)
    write_audit(db, admin.id, action, "ingestion_job", str(job.id), None, client_ip(request))
    db.commit()
    return job


@router.post("/pause", response_model=JobOut)
def pause(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _change(("queued", "running"), "paused", "ingestion.pause", request, admin, db)


@router.post("/resume", response_model=JobOut)
def resume(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _change(("paused",), "running", "ingestion.resume", request, admin, db)


@router.get("/status")
def status(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    current = active_job(db)
    last = db.scalar(
        select(IngestionJob).where(IngestionJob.status == "completed").order_by(IngestionJob.finished_at.desc()).limit(1)
    )
    by_status = dict(db.execute(select(Meeting.ingest_status, func.count()).group_by(Meeting.ingest_status)).all())
    seg_total, seg_embedded = db.execute(
        select(func.count(), func.count(TranscriptSegment.embedding)).select_from(TranscriptSegment)
    ).one()
    failed = db.scalars(
        select(Meeting).where(Meeting.ingest_status == "failed").order_by(Meeting.updated_at.desc()).limit(50)
    )
    return {
        "current_job": JobOut.model_validate(current).model_dump() if current else None,
        "last_completed_job": JobOut.model_validate(last).model_dump() if last else None,
        "totals": {
            "meetings": sum(by_status.values()),
            **{k: by_status.get(k, 0) for k in ("indexed", "parsed", "failed", "skipped", "discovered")},
            "segments": seg_total,
            "embedded_segments": seg_embedded,
        },
        "failed_meetings": [
            {"id": str(m.id), "subject": m.subject, "error": m.ingest_error, "attempts": m.ingest_attempts}
            for m in failed
        ],
        "last_sync_at": last.finished_at if last else None,
        "bucket": s.s3_bucket,
        "prefixes": s.s3_prefix_list,
    }
