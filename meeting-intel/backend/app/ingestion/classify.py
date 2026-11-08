"""Decide what an S3 key is. Never assume an object is a meeting file."""
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum


class FileKind(StrEnum):
    TRANSCRIPT = "transcript"
    NOTES_MD = "notes_md"
    NOTES_JSON = "notes_json"
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassifiedKey:
    kind: FileKind
    meeting_id: uuid.UUID | None
    folder: str | None


_NAMES = {
    "transcript.json": FileKind.TRANSCRIPT,
    "notes.md": FileKind.NOTES_MD,
    "notes.json": FileKind.NOTES_JSON,
    "recording.mp3": FileKind.AUDIO,
    "recording.m4a": FileKind.AUDIO,
    "recording.wav": FileKind.AUDIO,
    "recording.mp4": FileKind.VIDEO,
    "recording.webm": FileKind.VIDEO,
}

# <YYYY>/<MM>/<meeting-uuid>/<file name>
_REST = re.compile(r"^(?P<year>\d{4})/(?P<month>\d{2})/(?P<mid>[0-9A-Fa-f-]{36})/(?P<name>[^/]+)$")

_UNKNOWN = ClassifiedKey(FileKind.UNKNOWN, None, None)


def _normalise_prefix(p: str) -> str:
    return p if p.endswith("/") else p + "/"


def classify_key(key: str, prefixes: list[str]) -> ClassifiedKey:
    for prefix in map(_normalise_prefix, prefixes):
        if not key.startswith(prefix):
            continue
        m = _REST.match(key[len(prefix):])
        if not m or not 1 <= int(m["month"]) <= 12:
            return _UNKNOWN
        kind = _NAMES.get(m["name"].lower())
        if kind is None:
            return _UNKNOWN
        try:
            mid = uuid.UUID(m["mid"])
        except ValueError:
            return _UNKNOWN
        return ClassifiedKey(kind, mid, f"{prefix}{m['year']}/{m['month']}/{m['mid'].lower()}/")
    return _UNKNOWN
