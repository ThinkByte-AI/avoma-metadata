import pytest
from sqlalchemy import func, select

from app.devseed import SAMPLE_PREFIX, seed_dev_data
from app.models import Meeting, TranscriptSegment


def test_devseed_refuses_in_production(db, settings_override):
    with pytest.raises(RuntimeError, match="dev-mock"):
        seed_dev_data(db)
    assert db.scalar(select(func.count()).select_from(Meeting)) == 0


def test_devseed_idempotent_and_labelled(db, monkeypatch, settings_override):
    from app.config import get_settings

    monkeypatch.setenv("APP_MODE", "dev-mock")
    get_settings.cache_clear()
    assert seed_dev_data(db) == 5
    assert seed_dev_data(db) == 0
    subjects = list(db.scalars(select(Meeting.subject)))
    assert len(subjects) == 5 and all(s.startswith(SAMPLE_PREFIX) for s in subjects)
    assert SAMPLE_PREFIX == "[SAMPLE] "
    assert db.scalar(select(func.count(TranscriptSegment.embedding))) > 0
    assert set(db.scalars(select(Meeting.ingest_status))) == {"indexed"}
