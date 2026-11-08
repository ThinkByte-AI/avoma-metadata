from datetime import UTC, datetime, timedelta

from cachetools import TTLCache
from fastapi import APIRouter, Depends
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.api.summaries import build_summaries
from app.auth.access import accessible_meeting_ids
from app.auth.deps import current_user
from app.db import get_db
from app.models import Meeting, MeetingParticipant, Participant, Recording, SearchHistory, User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_cache: TTLCache = TTLCache(maxsize=256, ttl=60)


def clear_stats_cache() -> None:
    _cache.clear()


def scope_key(user: User) -> str:
    return "all" if user.role == "admin" or user.access_scope == "all" else f"user:{user.id}"


def _month(col):
    return func.to_char(func.date_trunc("month", col), "YYYY-MM")


def compute_stats(db: Session, user: User) -> dict:
    visible = accessible_meeting_ids(user)
    in_scope = Meeting.id.in_(visible)
    total, transcripts, duration = db.execute(
        select(func.count(), func.count().filter(Meeting.has_transcript),
               func.coalesce(func.sum(Meeting.duration_sec), 0)).where(in_scope)
    ).one()
    audio_n, audio_b, video_b = db.execute(
        select(func.count(func.distinct(Recording.meeting_id)).filter(Recording.kind == "audio"),
               func.coalesce(func.sum(Recording.size_bytes).filter(Recording.kind == "audio"), 0),
               func.coalesce(func.sum(Recording.size_bytes).filter(Recording.kind == "video"), 0))
        .where(Recording.meeting_id.in_(visible))
    ).one()
    participants = db.scalar(select(func.count(func.distinct(MeetingParticipant.participant_id)))
                             .where(MeetingParticipant.meeting_id.in_(visible)))
    by_month = db.execute(
        select(_month(Meeting.start_at).label("m"), func.count()).where(in_scope, Meeting.start_at.is_not(None))
        .group_by("m").order_by("m")
    ).all()
    top_people = db.execute(
        select(Participant.id, Participant.name, func.count().label("n"))
        .join(MeetingParticipant, MeetingParticipant.participant_id == Participant.id)
        .where(MeetingParticipant.meeting_id.in_(visible))
        .group_by(Participant.id).order_by(func.count().desc(), Participant.name).limit(10)
    ).all()
    topic = func.unnest(Meeting.topics).label("topic")
    topics_sq = select(topic).where(in_scope).subquery()
    top_topics = db.execute(
        select(topics_sq.c.topic, func.count().label("n")).group_by(topics_sq.c.topic)
        .order_by(func.count().desc(), topics_sq.c.topic).limit(10)
    ).all()
    recent_ids = list(db.scalars(select(Meeting.id).where(in_scope).order_by(Meeting.start_at.desc().nulls_last())
                                 .limit(5)))
    recent = build_summaries(db, recent_ids)

    today = datetime.now(UTC).date()
    start = today - timedelta(days=29)
    hist = select(cast(SearchHistory.created_at, Date).label("d"), func.count()).where(
        cast(SearchHistory.created_at, Date) >= start)
    if scope_key(user) != "all":
        hist = hist.where(SearchHistory.user_id == user.id)
    counts = dict(db.execute(hist.group_by("d")).all())
    activity = [{"date": (start + timedelta(days=i)).isoformat(), "count": counts.get(start + timedelta(days=i), 0)}
                for i in range(30)]

    return {
        "total_meetings": total,
        "total_recordings": audio_n,
        "total_participants": participants,
        "total_transcripts": transcripts,
        "audio_storage_bytes": int(audio_b),
        "video_storage_bytes": int(video_b),
        "total_duration_sec": int(duration),
        "meetings_by_month": [{"month": m, "count": n} for m, n in by_month],
        "top_participants": [{"id": p.id, "name": p.name, "count": p.n} for p in top_people],
        "top_topics": [{"topic": t.topic, "count": t.n} for t in top_topics],
        "recent_meetings": [recent[i].model_dump(mode="json") for i in recent_ids],
        "search_activity": activity,
    }


@router.get("/stats")
def dashboard_stats(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    key = scope_key(user)
    if key not in _cache:
        _cache[key] = compute_stats(db, user)
    return _cache[key]
