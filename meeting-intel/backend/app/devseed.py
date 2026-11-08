"""Development-mode sample data. Only runs when APP_MODE=dev-mock; every subject starts with "[SAMPLE] ".

Run: `python -m app.devseed` (the API also seeds on startup in dev-mock mode).
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.ai.embeddings import FakeEmbedder
from app.config import get_settings
from app.models import Meeting, MeetingParticipant, Participant, TranscriptSegment

log = logging.getLogger("app.devseed")
SAMPLE_PREFIX = "[SAMPLE] "
_NS = uuid.UUID("6f1c3a52-5b3a-4c0e-9a7e-1d2b3c4d5e6f")

_PEOPLE = {
    "ana": ("Ana Sample", "ana@sample.invalid", True),
    "raj": ("Raj Sample", "raj@sample.invalid", True),
    "lee": ("Lee Client", "lee@client.sample.invalid", False),
}

_MEETINGS = [
    ("Quarterly revenue review", 2, 2400, [
        ("ana", "Revenue grew eight percent this quarter."), ("lee", "We want to understand the new pricing tiers."),
        ("raj", "The pricing change goes live next month."),
    ], ["Revenue", "Pricing"]),
    ("Client onboarding kickoff", 9, 1800, [
        ("raj", "Welcome, we will finish onboarding before the project deadline."),
        ("lee", "Our documents will arrive on Monday."),
    ], ["Onboarding"]),
    ("Cloud infrastructure planning", 35, 3000, [
        ("ana", "We should move the database to managed hosting."),
        ("raj", "Increasing the infrastructure budget makes sense."),
    ], ["Infrastructure"]),
    ("Marketing strategy session", 80, 2700, [
        ("lee", "The marketing plan focuses on search and paid ads."),
        ("ana", "Let us track leads by region every week."),
    ], ["Marketing"]),
    ("Weekly team sync", 120, 900, [
        ("raj", "Action item: share the status report by Friday."),
        ("ana", "I will follow up with the client about the launch date."),
    ], ["Status"]),
]


def seed_dev_data(db: Session) -> int:
    """Create the sample meetings. Returns how many were created (0 if they already exist)."""
    if get_settings().app_mode != "dev-mock":
        raise RuntimeError("Sample data can only be created when APP_MODE=dev-mock.")
    if db.scalar(select(exists().where(Meeting.subject.startswith(SAMPLE_PREFIX)))):
        return 0

    emb = FakeEmbedder(get_settings().embed_dim)
    now = datetime.now(UTC)
    pid = {}
    for key, (name, email, internal) in _PEOPLE.items():
        p = db.scalar(select(Participant).where(Participant.normalized_key == f"email:{email}"))
        if p is None:
            p = Participant(name=name, email=email, is_internal=internal, normalized_key=f"email:{email}")
            db.add(p)
            db.flush()
        pid[key] = p.id

    for i, (title, days, dur, lines, topics) in enumerate(_MEETINGS):
        subject = SAMPLE_PREFIX + title
        mid = uuid.uuid5(_NS, title)
        db.add(Meeting(id=mid, subject=subject, start_at=now - timedelta(days=days), duration_sec=dur,
                       owner_key="Sample", accounts=["Sample"], s3_folder=f"sample/{mid}/", has_recording=False,
                       has_transcript=True, has_notes=False, topics=topics, ingest_status="indexed",
                       indexed_at=now))
        db.flush()
        spoke: dict[str, float] = {}
        t = 5.0
        for seq, (who, text) in enumerate(lines):
            end = t + 4 + len(text.split()) * 0.4
            spoke[who] = spoke.get(who, 0) + (end - t)
            name = _PEOPLE[who][0]
            db.add(TranscriptSegment(
                meeting_id=mid, kind="utterance", seq=seq, participant_id=pid[who], speaker_name=name,
                start_sec=t, end_sec=end, text=text,
            ))
            t = end + 1
        chunk_text = "\n".join(f"{_PEOPLE[w][0]}: {txt}" for w, txt in lines)
        db.add(TranscriptSegment(
            meeting_id=mid, kind="chunk", seq=0, participant_ids=sorted({pid[w] for w, _ in lines}),
            speaker_name=", ".join(dict.fromkeys(_PEOPLE[w][0] for w, _ in lines)), start_sec=5.0, end_sec=t,
            text=chunk_text, embedding=emb.embed_documents([f"{subject} | {chunk_text}"])[0],
        ))
        for who, sec in spoke.items():
            db.add(MeetingParticipant(meeting_id=mid, participant_id=pid[who], speaking_sec=round(sec, 2),
                                      is_internal=_PEOPLE[who][2]))
    db.commit()
    log.warning("development sample data created", extra={"meetings": len(_MEETINGS)})
    return len(_MEETINGS)


if __name__ == "__main__":
    from app.db import get_session_factory

    with get_session_factory()() as session:
        print(f"created {seed_dev_data(session)} sample meetings")
