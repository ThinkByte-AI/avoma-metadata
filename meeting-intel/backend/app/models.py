"""ORM models. Table and column names are part of the contract between tasks — see the plan, Task 2."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBED_DIM = 1024


class Base(DeclarativeBase):
    pass


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin','user')", name="ck_users_role"),
        CheckConstraint("access_scope IN ('own','all')", name="ck_users_access_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")
    access_scope: Mapped[str] = mapped_column(Text, nullable=False, server_default="own")
    account_label: Mapped[str | None] = mapped_column(Text)
    can_download: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint(
            "ingest_status IN ('discovered','parsed','indexed','failed','skipped')", name="ck_meetings_ingest_status"
        ),
        Index("ix_meetings_start_at", "start_at"),
        Index("ix_meetings_ingest_status", "ingest_status"),
        Index("ix_meetings_accounts", "accounts", postgresql_using="gin"),
        Index("ix_meetings_subject_trgm", "subject", postgresql_using="gin", postgresql_ops={"subject": "gin_trgm_ops"}),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    owner_key: Mapped[str | None] = mapped_column(Text)
    accounts: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    s3_folder: Mapped[str] = mapped_column(Text, nullable=False)
    has_recording: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    has_transcript: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    has_notes: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    notes_md: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    transcription_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("meetings.id"))
    ingest_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="discovered")
    ingest_error: Mapped[str | None] = mapped_column(Text)
    ingest_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    transcript_etag: Mapped[str | None] = mapped_column(Text)
    notes_etag: Mapped[str | None] = mapped_column(Text)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        Index("ix_participants_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        Index("ix_participants_email_trgm", "email", postgresql_using="gin", postgresql_ops={"email": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    normalized_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"
    __table_args__ = (
        PrimaryKeyConstraint("meeting_id", "participant_id"),
        Index("ix_meeting_participants_participant_id", "participant_id"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"))
    participant_id: Mapped[int] = mapped_column(Integer, ForeignKey("participants.id", ondelete="CASCADE"))
    speaker_id: Mapped[int | None] = mapped_column(Integer)
    speaking_sec: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = (
        CheckConstraint("kind IN ('audio','video')", name="ck_recordings_kind"),
        UniqueConstraint("meeting_id", "kind", name="uq_recordings_meeting_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    storage_class: Mapped[str | None] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    transcription_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    etag: Mapped[str | None] = mapped_column(Text)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    speaker_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_word_sec: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, server_default=text("0"))
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        CheckConstraint("kind IN ('utterance','note')", name="ck_segments_kind"),
        UniqueConstraint("meeting_id", "kind", "seq", name="uq_segments_meeting_kind_seq"),
        Index("ix_segments_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_segments_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_segments_meeting_start", "meeting_id", "start_sec"),
        Index("ix_segments_participant_id", "participant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    transcript_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("transcripts.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    participant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("participants.id", ondelete="SET NULL"))
    speaker_name: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text)
    start_sec: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    end_sec: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('initial','sync','retry')", name="ck_jobs_kind"),
        CheckConstraint(
            "status IN ('queued','running','paused','completed','failed','cancelled')", name="ck_jobs_status"
        ),
        # Only one queued/running/paused job at a time.
        Index(
            "uq_jobs_one_active",
            text("(true)"),
            unique=True,
            postgresql_where=text("status IN ('queued','running','paused')"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    requested_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchHistory(Base):
    __tablename__ = "search_history"
    __table_args__ = (Index("ix_search_history_user_created", "user_id", text("created_at DESC")),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="auto")
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = _created()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
