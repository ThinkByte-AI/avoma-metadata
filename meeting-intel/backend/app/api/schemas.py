"""Response/request models shared across routers."""
import uuid
from datetime import UTC, datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator

Role = Literal["admin", "user"]
Scope = Literal["own", "all"]
T = TypeVar("T")


def _iso_z(d: datetime) -> str:
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC).isoformat().replace("+00:00", "Z")


# All API datetimes are UTC ISO 8601 with a trailing "Z".
UtcDT = Annotated[datetime, PlainSerializer(_iso_z, return_type=str)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: Role
    access_scope: Scope
    account_label: str | None
    can_download: bool
    is_active: bool
    last_login_at: UtcDT | None


class ParticipantRef(BaseModel):
    id: int
    name: str
    email: str | None
    is_internal: bool


class MeetingSummary(BaseModel):
    id: uuid.UUID
    subject: str
    start_at: UtcDT | None
    duration_sec: int | None
    owner_key: str | None
    has_recording: bool
    has_transcript: bool
    participant_count: int
    participants: list[ParticipantRef]
    topics: list[str]


class Page(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: list[T]


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=256)
    role: Role = "user"
    access_scope: Scope = "own"
    account_label: str | None = Field(default=None, max_length=200)
    can_download: bool = False

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=10, max_length=256)
    role: Role | None = None
    access_scope: Scope | None = None
    account_label: str | None = Field(default=None, max_length=200)
    can_download: bool | None = None
    is_active: bool | None = None
