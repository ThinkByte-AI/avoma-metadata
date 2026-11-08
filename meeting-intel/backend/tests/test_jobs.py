import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.errors import ApiError
from app.ingestion.jobs import claim_next_job, enqueue_job, requeue_stale_jobs, run_job, set_status
from app.models import IngestionJob, Meeting
from tests.test_pipeline import A, B, FIX, _put, bucket, meta, store  # noqa: F401  (fixtures)


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def _run(factory, job_id, store, meta, **kw):
    run_job(factory, job_id, store, None, lambda: meta, poll_sec=0.05, **kw)


def test_enqueue_and_claim(db, factory):
    job = enqueue_job(db, "initial", None)
    assert job.status == "queued"
    with factory() as s:
        claimed = claim_next_job(s)
        assert claimed.id == job.id and claimed.status == "running" and claimed.started_at is not None
    with factory() as s:
        assert claim_next_job(s) is None


def test_second_enqueue_raises_job_active(db):
    enqueue_job(db, "initial", None)
    with pytest.raises(ApiError) as e:
        enqueue_job(db, "sync", None)
    assert e.value.status == 409 and e.value.code == "job_active"


def test_claim_skips_locked(db, factory):
    job = enqueue_job(db, "initial", None)
    locker = factory()
    locker.execute(text("SELECT id FROM ingestion_jobs WHERE id = :id FOR UPDATE"), {"id": job.id})
    try:
        with factory() as s:
            assert claim_next_job(s) is None
    finally:
        locker.rollback()
        locker.close()
    with factory() as s:
        assert claim_next_job(s).id == job.id


def test_run_job_processes_and_records_stats(db, factory, store, meta):
    job = enqueue_job(db, "initial", None)
    with factory() as s:
        claim_next_job(s)
    _run(factory, job.id, store, meta)
    db.expire_all()
    j = db.get(IngestionJob, job.id)
    assert j.status == "completed" and j.finished_at is not None and j.error is None
    s = j.stats
    assert (s["objects_scanned"], s["audio_files"], s["transcript_files"], s["meetings_identified"], s["duplicates"]) == (11, 2, 4, 4, 2)
    assert (s["to_process"], s["processed"], s["meetings_parsed"], s["meetings_failed"]) == (3, 3, 3, 0)
    assert (s["phase"], s["to_embed"], s["embedded"]) == ("done", 0, 0)  # no embedder: parse only
    assert db.get(Meeting, A).ingest_status == "parsed"


def test_run_job_parses_everything_before_embedding(db, factory, store, meta):
    from app.ai.embeddings import FakeEmbedder

    order: list[str] = []
    real_fetch = store.fetch

    def spy_fetch(key):
        order.append("parse")
        return real_fetch(key)

    class Spy(FakeEmbedder):
        def embed_documents(self, texts):
            order.append("embed")
            return super().embed_documents(texts)

    store.fetch = spy_fetch
    job = enqueue_job(db, "initial", None)
    with factory() as s:
        claim_next_job(s)
    run_job(factory, job.id, store, Spy(), lambda: meta, poll_sec=0.05)
    assert "embed" in order and "parse" not in order[order.index("embed"):]
    db.expire_all()
    st = db.get(IngestionJob, job.id).stats
    assert (st["phase"], st["to_embed"], st["embedded"], st["meetings_indexed"]) == ("done", 3, 3, 3)


def test_pause_then_resume_finishes_job(db, factory, store, meta):
    job = enqueue_job(db, "initial", None)
    with factory() as s:
        claim_next_job(s)

    first_fetch, release = threading.Event(), threading.Event()
    real_fetch = store.fetch

    def gated(key):
        if not first_fetch.is_set():
            first_fetch.set()
            release.wait(5)
        return real_fetch(key)

    store.fetch = gated
    t = threading.Thread(target=_run, args=(factory, job.id, store, meta))
    t.start()
    assert first_fetch.wait(5)
    set_status(db, job.id, "paused")
    release.set()
    time.sleep(0.5)
    db.expire_all()
    j = db.get(IngestionJob, job.id)
    assert j.status == "paused" and j.stats["processed"] == 1
    time.sleep(0.3)
    db.expire_all()
    assert db.get(IngestionJob, job.id).stats["processed"] == 1  # stays put while paused
    set_status(db, job.id, "running")
    t.join(10)
    assert not t.is_alive()
    db.expire_all()
    j = db.get(IngestionJob, job.id)
    assert j.status == "completed" and j.stats["processed"] == 3


def test_retry_processes_only_failed(db, factory, store, bucket, meta):  # noqa: F811
    _put(bucket, f"avoma/2025/03/{B}/transcript.json", "{not json")
    job = enqueue_job(db, "initial", None)
    with factory() as s:
        claim_next_job(s)
    _run(factory, job.id, store, meta)
    db.expire_all()
    assert db.get(Meeting, B).ingest_status == "failed"

    _put(bucket, f"avoma/2025/03/{B}/transcript.json", (FIX / "transcript_messy.json").read_text(encoding="utf-8"))
    retry = enqueue_job(db, "retry", None)
    with factory() as s:
        claim_next_job(s)
    _run(factory, retry.id, store, meta)
    db.expire_all()
    r = db.get(IngestionJob, retry.id)
    assert r.status == "completed" and r.stats["to_process"] == 1 and r.stats["meetings_parsed"] == 1
    assert db.get(Meeting, B).ingest_status == "parsed"


def test_scan_error_marks_job_failed(db, factory, bucket, meta):  # noqa: F811
    from app.aws.s3 import S3Store

    job = enqueue_job(db, "initial", None)
    with factory() as s:
        claim_next_job(s)
    _run(factory, job.id, S3Store("missing-bucket", "ap-south-1"), meta)
    db.expire_all()
    j = db.get(IngestionJob, job.id)
    assert j.status == "failed" and "NoSuchBucket" in j.error and j.finished_at is not None


def test_stale_running_job_requeued_on_worker_start(db):
    old = IngestionJob(kind="initial", status="running", heartbeat_at=datetime.now(UTC) - timedelta(minutes=20))
    db.add(old)
    db.commit()
    assert requeue_stale_jobs(db) == 1
    db.refresh(old)
    assert old.status == "queued"


def test_fresh_running_job_not_requeued(db):
    job = IngestionJob(kind="initial", status="running", heartbeat_at=datetime.now(UTC))
    db.add(job)
    db.commit()
    assert requeue_stale_jobs(db) == 0
    assert db.scalar(select(IngestionJob.status)) == "running"


def test_resume_of_orphaned_paused_job_requeues_it(db):
    job = IngestionJob(kind="initial", status="paused", started_at=datetime.now(UTC) - timedelta(hours=1),
                       heartbeat_at=datetime.now(UTC) - timedelta(minutes=30))
    db.add(job)
    db.commit()
    assert set_status(db, job.id, "running").status == "queued"  # its worker is gone; let a new one claim it


def test_resume_of_live_paused_job_keeps_running(db):
    job = IngestionJob(kind="initial", status="paused", started_at=datetime.now(UTC), heartbeat_at=datetime.now(UTC))
    db.add(job)
    db.commit()
    assert set_status(db, job.id, "running").status == "running"
