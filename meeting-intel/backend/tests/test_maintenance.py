import uuid

from app.maintenance import recompute_topics
from app.models import Meeting


def test_recompute_topics_from_stored_notes(db):
    a = Meeting(id=uuid.uuid4(), subject="A", s3_folder="x/", topics=["1. Old Numbered"],
                notes_md="# A\n## 1. Pricing Review\n- x\n## Decision\n- y\n")
    b = Meeting(id=uuid.uuid4(), subject="B", s3_folder="y/", topics=["Pricing Review"],
                notes_md="# B\n## Pricing review\n- x\n")
    c = Meeting(id=uuid.uuid4(), subject="C", s3_folder="z/", topics=[], notes_md=None)
    db.add_all([a, b, c])
    db.commit()
    assert recompute_topics(db) == 1
    db.refresh(a)
    assert a.topics == ["Pricing Review"]
