"""Parse Avoma transcript.json into speaker-turn segments with timestamps."""
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.ingestion.metadata import parse_dt

MAX_SEGMENT_WORDS = 220


@dataclass
class Speaker:
    id: int
    name: str
    email: str | None
    is_internal: bool


@dataclass
class Segment:
    seq: int
    speaker_id: int | None
    speaker_name: str
    start_sec: float
    end_sec: float
    text: str
    word_count: int


@dataclass
class ParsedTranscript:
    transcription_uuid: uuid.UUID | None
    meeting_uuid: uuid.UUID | None
    modified: datetime | None
    speakers: list[Speaker]
    segments: list[Segment]
    last_word_sec: float


def _uuid(v: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(v)) if v else None
    except ValueError:
        return None


def _int(v: Any) -> int | None:
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _times(v: Any) -> list[float]:
    out = []
    for t in v or []:
        try:
            out.append(float(t))
        except (TypeError, ValueError):
            continue
    return out


def parse_transcript(raw: Any) -> ParsedTranscript:
    doc: dict = {}
    if isinstance(raw, list):
        doc = raw[0] if raw and isinstance(raw[0], dict) else {}
    elif isinstance(raw, dict):
        doc = raw

    speakers: list[Speaker] = []
    by_id: dict[int, Speaker] = {}
    for s in doc.get("speakers") or []:
        sid = _int(s.get("id"))
        if sid is None:
            continue
        name = (s.get("name") or "").strip() or f"Speaker {sid}"
        email = (s.get("email") or "").strip().lower() or None
        sp = Speaker(sid, name, email, bool(s.get("is_rep")))
        speakers.append(sp)
        by_id[sid] = sp

    segments: list[Segment] = []
    cur: dict | None = None
    last_end = 0.0

    def flush() -> None:
        if cur is not None:
            segments.append(
                Segment(len(segments), cur["sid"], cur["name"], cur["start"], cur["end"], " ".join(cur["texts"]), cur["words"])
            )

    for u in doc.get("transcript") or []:
        text = " ".join(str(u.get("transcript") or "").split())
        if not text:
            continue
        sid = _int(u.get("speaker_id"))
        if sid is None:
            name = "Unknown speaker"
        else:
            name = by_id[sid].name if sid in by_id else f"Speaker {sid}"
        times = _times(u.get("timestamps"))
        start = times[0] if times else last_end
        end = times[-1] if times else last_end
        last_end = max(last_end, end)
        words = len(text.split())

        if cur is not None and cur["sid"] == sid and cur["words"] + words <= MAX_SEGMENT_WORDS:
            cur["texts"].append(text)
            cur["words"] += words
            cur["end"] = max(cur["end"], end)
            continue
        flush()
        cur = {"sid": sid, "name": name, "start": start, "end": end, "texts": [text], "words": words}
    flush()

    return ParsedTranscript(
        transcription_uuid=_uuid(doc.get("uuid")),
        meeting_uuid=_uuid(doc.get("meeting_uuid")),
        modified=parse_dt(doc.get("modified")) if isinstance(doc.get("modified"), str) else None,
        speakers=speakers,
        segments=segments,
        last_word_sec=last_end,
    )
