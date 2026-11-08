from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.access import accessible_meeting_clause
from app.auth.deps import current_user
from app.db import get_db
from app.models import Meeting, MeetingParticipant, Participant, User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

TOP_TOPICS = 6


def _month(col):
    return func.to_char(func.date_trunc("month", col), "YYYY-MM")


@router.get("")
def analytics(
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    conds = [accessible_meeting_clause(user)]
    if date_from:
        conds.append(Meeting.start_at >= datetime.combine(date_from, time.min, UTC))
    if date_to:
        conds.append(Meeting.start_at < datetime.combine(date_to + timedelta(days=1), time.min, UTC))
    visible = select(Meeting.id).where(*conds)

    hours = db.execute(
        select(_month(Meeting.start_at).label("m"), func.coalesce(func.sum(Meeting.duration_sec), 0))
        .where(*conds, Meeting.start_at.is_not(None)).group_by("m").order_by("m")
    ).all()
    owner = func.coalesce(Meeting.owner_key, "Unknown").label("owner")
    owners = db.execute(select(owner, func.count()).where(*conds).group_by(owner)
                        .order_by(func.count().desc(), owner)).all()
    leaders = db.execute(
        select(Participant.id, Participant.name, func.sum(MeetingParticipant.speaking_sec).label("s"))
        .join(MeetingParticipant, MeetingParticipant.participant_id == Participant.id)
        .where(MeetingParticipant.meeting_id.in_(visible))
        .group_by(Participant.id).order_by(func.sum(MeetingParticipant.speaking_sec).desc(), Participant.name).limit(15)
    ).all()

    topic = func.unnest(Meeting.topics).label("topic")
    tsq = select(_month(Meeting.start_at).label("m"), topic).where(*conds, Meeting.start_at.is_not(None)).subquery()
    top = [t for (t,) in db.execute(select(tsq.c.topic).group_by(tsq.c.topic)
                                     .order_by(func.count().desc(), tsq.c.topic).limit(TOP_TOPICS))]
    by_month = db.execute(
        select(tsq.c.m, tsq.c.topic, func.count()).where(tsq.c.topic.in_(top)).group_by(tsq.c.m, tsq.c.topic)
        .order_by(tsq.c.m, tsq.c.topic)
    ).all() if top else []

    internal_s, external_s = db.execute(
        select(func.coalesce(func.sum(MeetingParticipant.speaking_sec).filter(MeetingParticipant.is_internal), 0),
               func.coalesce(func.sum(MeetingParticipant.speaking_sec).filter(~MeetingParticipant.is_internal), 0))
        .where(MeetingParticipant.meeting_id.in_(visible))
    ).one()

    return {
        "hours_by_month": [{"month": m, "hours": round(float(s) / 3600, 4)} for m, s in hours],
        "meetings_by_owner": [{"owner": o, "count": n} for o, n in owners],
        "speaking_leaders": [{"participant_id": p.id, "name": p.name, "hours": round(float(p.s) / 3600, 6)}
                             for p in leaders],
        "topics_by_month": [{"month": m, "topic": t, "count": n} for m, t, n in by_month],
        "internal_vs_external_speaking": {"internal_hours": round(float(internal_s) / 3600, 6),
                                          "external_hours": round(float(external_s) / 3600, 6)},
    }
