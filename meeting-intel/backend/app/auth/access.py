"""Who may see which meeting. Every read path (lists, search, detail, audio, AI) goes through here."""
import uuid

from sqlalchemy import ColumnElement, and_, exists, func, or_, select, true
from sqlalchemy.orm import Session

from app.errors import not_found
from app.models import Meeting, MeetingParticipant, Participant, User


def accessible_meeting_clause(user: User) -> ColumnElement[bool]:
    not_duplicate = Meeting.duplicate_of.is_(None)
    if user.role == "admin" or user.access_scope == "all":
        return and_(not_duplicate, true())
    attended = exists().where(
        MeetingParticipant.meeting_id == Meeting.id,
        MeetingParticipant.participant_id == Participant.id,
        func.lower(Participant.email) == user.email.lower(),
    )
    rules = [attended]
    if user.account_label:
        rules.append(Meeting.accounts.contains([user.account_label]))
    return and_(not_duplicate, or_(*rules))


def accessible_meeting_ids(user: User):
    """Subquery of meeting ids the user may see."""
    return select(Meeting.id).where(accessible_meeting_clause(user))


def ensure_meeting_access(db: Session, user: User, meeting_id: uuid.UUID) -> Meeting:
    m = db.scalar(select(Meeting).where(Meeting.id == meeting_id, accessible_meeting_clause(user)))
    if m is None:
        raise not_found("meeting")
    return m
