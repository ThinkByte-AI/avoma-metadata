"""Response/request models shared across routers."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["admin", "user"]
Scope = Literal["own", "all"]


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
    last_login_at: datetime | None


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
