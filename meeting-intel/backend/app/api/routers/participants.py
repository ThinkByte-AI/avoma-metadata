import re
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import MeetingSummary, Page, _iso_z
from app.api.summaries import build_summaries
from app.auth.access import accessible_meeting_ids
from app.auth.deps import current_user
from app.db import get_db
from app.errors import not_found
from app.models import Meeting, MeetingParticipant, Participant, TranscriptSegment, User
from app.search.service import _like

router = APIRouter(prefix="/api/participants", tags=["participants"])

MP, P = MeetingParticipant, Participant


def _stats_query(user: User):
    visible = accessible_meeting_ids(user)
    return (
        select(P.id, P.name, P.email, P.is_internal,
               func.count(MP.meeting_id).label("meeting_count"),
               func.coalesce(func.sum(MP.speaking_sec), 0).label("speaking_sec"),
               func.min(Meeting.start_at).label("first_meeting_at"),
               func.max(Meeting.start_at).label("last_meeting_at"))
        .join(MP, MP.participant_id == P.id)
        .join(Meeting, Meeting.id == MP.meeting_id)
        .where(MP.meeting_id.in_(visible))
        .group_by(P.id)
    )


def _row(r) -> dict:
    return {"id": r.id, "name": r.name, "email": r.email, "is_internal": r.is_internal,
            "meeting_count": r.meeting_count, "speaking_sec": float(r.speaking_sec),
            "first_meeting_at": _iso_z(r.first_meeting_at) if r.first_meeting_at else None,
            "last_meeting_at": _iso_z(r.last_meeting_at) if r.last_meeting_at else None}


_SORTS = {
    "meetings_desc": lambda q: (q.c.meeting_count.desc(), func.lower(q.c.name)),
    "name": lambda q: (func.lower(q.c.name),),
    "last_seen": lambda q: (q.c.last_meeting_at.desc().nulls_last(), func.lower(q.c.name)),
}


@router.get("")
def list_participants(
    q: str | None = Query(None, max_length=200),
    internal: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: Literal["meetings_desc", "name", "last_seen"] = "meetings_desc",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    base = _stats_query(user)
    if q and q.strip():
        like = _like(q.strip())
        base = base.where(or_(P.name.ilike(like, escape="\\"), P.email.ilike(like, escape="\\")))
    if internal is not None:
        base = base.where(P.is_internal.is_(internal))
    sq = base.subquery()
    total = db.scalar(select(func.count()).select_from(sq))
    rows = db.execute(select(sq).order_by(*_SORTS[sort](sq), sq.c.id).offset((page - 1) * page_size).limit(page_size))
    return {"total": total, "page": page, "page_size": page_size, "items": [_row(r) for r in rows]}


@router.get("/{participant_id}")
def get_participant(participant_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    r = db.execute(_stats_query(user).where(P.id == participant_id)).first()
    if r is None:
        raise not_found("participant")
    visible = accessible_meeting_ids(user)
    ids = list(db.scalars(
        select(Meeting.id).join(MP, MP.meeting_id == Meeting.id)
        .where(MP.participant_id == participant_id, Meeting.id.in_(visible))
        .order_by(Meeting.start_at.desc().nulls_last()).limit(20)
    ))
    summaries = build_summaries(db, ids)

    mentions = []
    first = re.sub(r"[^\w]", "", (r.name.split() or [""])[0])
    if len(first) >= 2:
        tsq = func.plainto_tsquery("english", first)
        seg_rows = db.execute(
            select(TranscriptSegment.id, TranscriptSegment.meeting_id, TranscriptSegment.start_sec,
                   TranscriptSegment.speaker_name, TranscriptSegment.text, Meeting.subject, Meeting.start_at)
            .join(Meeting, Meeting.id == TranscriptSegment.meeting_id)
            .where(TranscriptSegment.tsv.op("@@")(tsq), TranscriptSegment.meeting_id.in_(visible),
                   or_(TranscriptSegment.participant_id.is_(None), TranscriptSegment.participant_id != participant_id))
            .order_by(Meeting.start_at.desc().nulls_last(), TranscriptSegment.seq).limit(30)
        )
        mentions = [{"meeting_id": str(s.meeting_id), "subject": s.subject,
                     "start_at": _iso_z(s.start_at) if s.start_at else None, "segment_id": s.id,
                     "start_sec": float(s.start_sec) if s.start_sec is not None else None,
                     "speaker_name": s.speaker_name, "text": s.text} for s in seg_rows]

    meetings_page = Page[MeetingSummary](total=r.meeting_count, page=1, page_size=20, items=[summaries[i] for i in ids])
    return {**_row(r), "meetings": meetings_page.model_dump(mode="json"), "mentions": mentions}
