import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import MeetingSummary, Page, ParticipantRef, UtcDT
from app.api.summaries import build_summaries
from app.audit import write_audit
from app.auth.access import ensure_meeting_access
from app.auth.deps import client_ip, current_user
from app.aws.s3 import S3Store, get_store
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Meeting, MeetingParticipant, Participant, Recording, TranscriptSegment, User
from app.search.schemas import SearchFilters
from app.search.service import scope_conditions

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class ParticipantWithTime(ParticipantRef):
    speaking_sec: float


class MeetingDetail(MeetingSummary):
    participants: list[ParticipantWithTime]
    notes_md: str | None
    recordings: list[dict]
    transcript: dict | None
    ingest_status: str
    accounts: list[str]


class TranscriptSegmentOut(BaseModel):
    id: int
    seq: int
    speaker_name: str | None
    participant_id: int | None
    start_sec: float
    end_sec: float
    text: str


class TranscriptOut(BaseModel):
    meeting_id: uuid.UUID
    speakers: list[ParticipantWithTime]
    segments: list[TranscriptSegmentOut]


class RecordingUrl(BaseModel):
    url: str
    expires_at: UtcDT
    content_type: str
    kind: Literal["audio", "video"]


_SORTS = {
    "date_desc": (Meeting.start_at.desc().nulls_last(),),
    "date_asc": (Meeting.start_at.asc().nulls_last(),),
    "duration_desc": (Meeting.duration_sec.desc().nulls_last(),),
    "title": (func.lower(Meeting.subject).asc(),),
}


@router.get("", response_model=Page[MeetingSummary])
def list_meetings(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: Literal["date_desc", "date_asc", "duration_desc", "title"] = "date_desc",
    title: str | None = Query(None, max_length=300),
    participant_id: int | None = None,
    owner: str | None = Query(None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    has_recording: bool | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    f = SearchFilters(title=title, owner=owner, date_from=date_from, date_to=date_to, has_recording=has_recording,
                      participant_ids=[participant_id] if participant_id else [])
    conds = scope_conditions(user, f, datetime.now(UTC))
    total = db.scalar(select(func.count()).select_from(Meeting).where(*conds))
    ids = list(db.scalars(select(Meeting.id).where(*conds).order_by(*_SORTS[sort], Meeting.id)
                          .offset((page - 1) * page_size).limit(page_size)))
    s = build_summaries(db, ids)
    return Page[MeetingSummary](total=total, page=page, page_size=page_size, items=[s[i] for i in ids])


def _people(db: Session, meeting_id: uuid.UUID) -> list[ParticipantWithTime]:
    rows = db.execute(
        select(Participant.id, Participant.name, Participant.email, Participant.is_internal,
               MeetingParticipant.speaking_sec)
        .join(MeetingParticipant, MeetingParticipant.participant_id == Participant.id)
        .where(MeetingParticipant.meeting_id == meeting_id)
        .order_by(Participant.is_internal, MeetingParticipant.speaking_sec.desc(), Participant.name)
    ).all()
    return [ParticipantWithTime(id=r.id, name=r.name, email=r.email, is_internal=r.is_internal,
                                speaking_sec=float(r.speaking_sec)) for r in rows]


@router.get("/{meeting_id}", response_model=MeetingDetail)
def get_meeting(meeting_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = ensure_meeting_access(db, user, meeting_id)
    summary = build_summaries(db, [m.id])[m.id]
    recs = db.execute(select(Recording.kind, Recording.size_bytes).where(Recording.meeting_id == m.id)
                      .order_by(Recording.kind)).all()
    seg_count, words = db.execute(
        select(func.count(), func.coalesce(func.sum(func.array_length(func.regexp_split_to_array(
            func.trim(TranscriptSegment.text), r"\s+"), 1)), 0))
        .where(TranscriptSegment.meeting_id == m.id, TranscriptSegment.kind == "utterance")
    ).one()
    return MeetingDetail(
        **summary.model_dump(exclude={"participants"}),
        participants=_people(db, m.id),
        notes_md=m.notes_md,
        recordings=[{"kind": r.kind, "size_bytes": r.size_bytes} for r in recs],
        transcript={"segment_count": seg_count, "word_count": int(words)} if m.has_transcript or seg_count else None,
        ingest_status=m.ingest_status,
        accounts=list(m.accounts or []),
    )


@router.get("/{meeting_id}/transcript", response_model=TranscriptOut)
def get_transcript(meeting_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = ensure_meeting_access(db, user, meeting_id)
    segs = db.scalars(
        select(TranscriptSegment).where(TranscriptSegment.meeting_id == m.id, TranscriptSegment.kind == "utterance")
        .order_by(TranscriptSegment.seq)
    ).all()
    if not segs:
        raise ApiError(404, "transcript_not_found", "This meeting has no transcript.")
    return TranscriptOut(
        meeting_id=m.id,
        speakers=_people(db, m.id),
        segments=[TranscriptSegmentOut(id=s.id, seq=s.seq, speaker_name=s.speaker_name, participant_id=s.participant_id,
                                       start_sec=float(s.start_sec or 0), end_sec=float(s.end_sec or 0), text=s.text)
                  for s in segs],
    )


_UNSAFE = re.compile(r"[^A-Za-z0-9 ._-]+")


def download_filename(subject: str, start_at: datetime | None, ext: str) -> str:
    base = " ".join(_UNSAFE.sub(" ", subject).split())[:120].strip(" .") or "meeting"
    day = start_at.strftime("%Y-%m-%d") if start_at else "undated"
    return f"{base}-{day}{ext}"


@router.get("/{meeting_id}/recording", response_model=RecordingUrl)
def get_recording(
    meeting_id: uuid.UUID,
    request: Request,
    kind: Literal["audio", "video"] = "audio",
    download: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    store: S3Store = Depends(get_store),
):
    m = ensure_meeting_access(db, user, meeting_id)
    rec = db.scalar(select(Recording).where(Recording.meeting_id == m.id, Recording.kind == kind))
    if rec is None:
        raise ApiError(404, "recording_not_found", f"This meeting has no {kind} recording.")
    if download and not (user.role == "admin" or user.can_download):
        raise ApiError(403, "download_not_allowed", "You don't have permission to download recordings.")
    ttl = get_settings().presign_ttl_sec
    ext = "." + rec.s3_key.rsplit(".", 1)[-1].lower()
    url = store.presign_get(rec.s3_key, rec.content_type, ttl,
                            download_name=download_filename(m.subject, m.start_at, ext) if download else None)
    write_audit(db, user.id, "recording.access", "meeting", str(m.id), {"kind": kind, "download": download},
                client_ip(request))
    db.commit()
    return RecordingUrl(url=url, expires_at=datetime.now(UTC) + timedelta(seconds=ttl), content_type=rec.content_type,
                        kind=kind)
