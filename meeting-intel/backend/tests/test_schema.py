import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError, StatementError

from app.models import IngestionJob, Meeting, Participant, TranscriptSegment


def _meeting(db) -> Meeting:
    m = Meeting(
        id=uuid.uuid4(),
        subject="Weekly sync",
        s3_folder="avoma/2025/02/x/",
        has_recording=False,
        has_transcript=True,
        has_notes=False,
    )
    db.add(m)
    db.flush()
    return m


def test_extensions_installed(db):
    names = {r[0] for r in db.execute(text("SELECT extname FROM pg_extension"))}
    assert {"vector", "pg_trgm"} <= names


def test_meeting_defaults(db):
    m = _meeting(db)
    db.refresh(m)
    assert m.ingest_status == "discovered" and m.accounts == [] and m.topics == [] and m.ingest_attempts == 0
    assert m.created_at is not None


def test_tsv_generated(db):
    m = _meeting(db)
    db.add(TranscriptSegment(meeting_id=m.id, kind="utterance", seq=0, text="Revenue grew"))
    db.flush()
    n = db.execute(
        text("SELECT count(*) FROM transcript_segments WHERE tsv @@ to_tsquery('english', 'revenue')")
    ).scalar()
    assert n == 1


def test_segment_unique_per_meeting_kind_seq(db):
    m = _meeting(db)
    db.add(TranscriptSegment(meeting_id=m.id, kind="utterance", seq=0, text="a"))
    db.flush()
    db.add(TranscriptSegment(meeting_id=m.id, kind="utterance", seq=0, text="b"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_segment_kind_checked(db):
    m = _meeting(db)
    db.add(TranscriptSegment(meeting_id=m.id, kind="bogus", seq=0, text="a"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_embedding_dimension_is_1024(db):
    m = _meeting(db)
    db.add(TranscriptSegment(meeting_id=m.id, kind="utterance", seq=0, text="a", embedding=[0.1, 0.2, 0.3]))
    with pytest.raises((DataError, StatementError)):
        db.flush()


def test_only_one_active_job(db):
    db.add(IngestionJob(kind="initial", status="queued"))
    db.flush()
    db.add(IngestionJob(kind="sync", status="queued"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_active_and_completed_jobs_can_coexist(db):
    db.add_all([IngestionJob(kind="initial", status="completed"), IngestionJob(kind="sync", status="running")])
    db.flush()
    assert db.execute(text("SELECT count(*) FROM ingestion_jobs")).scalar() == 2


def test_participant_normalized_key_unique(db):
    db.add(Participant(name="Alice", email="a@x.com", is_internal=False, normalized_key="email:a@x.com"))
    db.flush()
    db.add(Participant(name="Alice T", email="a@x.com", is_internal=False, normalized_key="email:a@x.com"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_deleting_meeting_cascades_segments(db):
    m = _meeting(db)
    db.add(TranscriptSegment(meeting_id=m.id, kind="utterance", seq=0, text="a"))
    db.flush()
    db.execute(text("DELETE FROM meetings WHERE id = :id"), {"id": m.id})
    assert db.execute(text("SELECT count(*) FROM transcript_segments")).scalar() == 0
