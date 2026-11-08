"""Build MeetingSummary objects for a list of meeting ids in two queries."""
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import MeetingSummary, ParticipantRef
from app.models import Meeting, MeetingParticipant, Participant

MAX_LISTED_PARTICIPANTS = 8


def build_summaries(db: Session, meeting_ids: list[uuid.UUID]) -> dict[uuid.UUID, MeetingSummary]:
    if not meeting_ids:
        return {}
    meetings = {m.id: m for m in db.scalars(select(Meeting).where(Meeting.id.in_(meeting_ids)))}
    rows = db.execute(
        select(MeetingParticipant.meeting_id, Participant.id, Participant.name, Participant.email,
               Participant.is_internal)
        .join(Participant, Participant.id == MeetingParticipant.participant_id)
        .where(MeetingParticipant.meeting_id.in_(meeting_ids))
        # external people first (they are usually the "who was this with" answer), then by talk time
        .order_by(MeetingParticipant.meeting_id, Participant.is_internal, MeetingParticipant.speaking_sec.desc(),
                  Participant.name)
    ).all()
    people: dict[uuid.UUID, list[ParticipantRef]] = defaultdict(list)
    for mid, pid, name, email, internal in rows:
        people[mid].append(ParticipantRef(id=pid, name=name, email=email, is_internal=internal))

    out = {}
    for mid, m in meetings.items():
        plist = people.get(mid, [])
        out[mid] = MeetingSummary(
            id=m.id, subject=m.subject, start_at=m.start_at, duration_sec=m.duration_sec, owner_key=m.owner_key,
            has_recording=m.has_recording, has_transcript=m.has_transcript, participant_count=len(plist),
            participants=plist[:MAX_LISTED_PARTICIPANTS], topics=list(m.topics or []),
        )
    return out
