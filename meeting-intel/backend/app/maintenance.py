"""One-off maintenance commands.

    python -m app.maintenance recompute-topics   # re-derive meetings.topics from stored notes (no S3 reads)
"""
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.notes import parse_notes
from app.models import Meeting


def recompute_topics(db: Session) -> int:
    """Re-derive topics from each meeting's stored notes. Returns how many meetings changed."""
    changed = 0
    for m in db.scalars(select(Meeting).where(Meeting.notes_md.is_not(None))):
        topics = parse_notes(m.notes_md).topics
        if topics != list(m.topics or []):
            m.topics = topics
            changed += 1
    db.commit()
    return changed


if __name__ == "__main__":
    from app.db import get_session_factory

    if sys.argv[1:] != ["recompute-topics"]:
        sys.exit(__doc__)
    with get_session_factory()() as session:
        print(f"topics updated for {recompute_topics(session)} meetings")
