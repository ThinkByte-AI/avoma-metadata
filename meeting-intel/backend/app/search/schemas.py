from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas import MeetingSummary

DatePreset = Literal["today", "7d", "30d", "6m", "1y", "all"]


class SearchFilters(BaseModel):
    participant_ids: list[int] = Field(default_factory=list, max_length=20)
    speaker_ids: list[int] = Field(default_factory=list, max_length=20)
    owner: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=300)
    date_preset: DatePreset | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_duration_min: int | None = Field(default=None, ge=0)
    max_duration_min: int | None = Field(default=None, ge=0)
    has_recording: bool | None = None
    has_transcript: bool | None = None

    def is_empty(self) -> bool:
        return self == SearchFilters() or self.model_dump(exclude_defaults=True) == {"date_preset": "all"}


class SearchRequest(BaseModel):
    q: str = Field(default="", max_length=2000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    mode: Literal["auto", "keyword", "semantic"] = "auto"
    sort: Literal["relevance", "date_desc", "date_asc", "duration_desc"] = "relevance"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class SegmentMatch(BaseModel):
    segment_id: int
    kind: Literal["utterance", "note"]
    speaker_name: str | None
    section: str | None
    start_sec: float | None
    text: str
    highlights: list[tuple[int, int]]
    match_type: Literal["keyword", "semantic", "both"]


class MeetingHit(BaseModel):
    meeting: MeetingSummary
    score: float
    match_types: list[str]
    matches: list[SegmentMatch]


class SearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    results: list[MeetingHit]
    took_ms: int
    semantic_used: bool
