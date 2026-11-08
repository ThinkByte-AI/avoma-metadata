"""Ingestion worker: `python -m app.worker`. Picks queued jobs from Postgres and runs them."""
import logging
import time
from pathlib import Path

from app.aws.s3 import get_store
from app.config import get_settings
from app.db import get_session_factory
from app.ingestion.jobs import claim_next_job, requeue_stale_jobs, run_job
from app.ingestion.metadata import load_metadata
from app.logging import setup_logging

log = logging.getLogger("app.worker")
IDLE_SLEEP_SEC = 3.0


def build_embedder():
    """Returns the embedding provider, or None when not configured (wired in Task 8)."""
    try:
        from app.ai.embeddings import get_embedder  # noqa: PLC0415
    except ImportError:
        return None
    return get_embedder(get_settings())


def main() -> None:
    s = get_settings()
    setup_logging(s.log_level)
    factory = get_session_factory()
    store = get_store()
    embedder = build_embedder()
    meta_dir = Path(s.metadata_dir)

    with factory() as db:
        n = requeue_stale_jobs(db)
        if n:
            log.warning("requeued stale jobs", extra={"count": n})
    log.info("worker started", extra={"bucket": s.s3_bucket, "embedder": type(embedder).__name__})

    while True:
        with factory() as db:
            job = claim_next_job(db)
            job_id = job.id if job else None
        if job_id is None:
            time.sleep(IDLE_SLEEP_SEC)
            continue
        log.info("job claimed", extra={"job_id": job_id})
        run_job(factory, job_id, store, embedder, lambda: load_metadata(meta_dir))


if __name__ == "__main__":
    main()
