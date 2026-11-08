"""Meeting metadata from the archive's CSV exports (titles, start, duration, owner, accounts)."""
import csv
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("app.ingestion.metadata")


@dataclass
class MeetingMeta:
    subject: str
    start_at: datetime | None
    duration_sec: int | None
    owner_key: str | None
    transcription_uuid: uuid.UUID | None
    accounts: list[str] = field(default_factory=list)


def parse_dt(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _uuid(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(value.strip()) if value and value.strip() else None
    except ValueError:
        return None


def _duration_sec(value: str | None) -> int | None:
    try:
        minutes = float(value) if value and value.strip() else None
    except ValueError:
        return None
    if minutes is None or math.isnan(minutes) or minutes < 0:
        return None
    return round(minutes * 60)


def _rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        yield reader.fieldnames or [], reader


def load_metadata(directory: Path) -> dict[uuid.UUID, MeetingMeta]:
    directory = Path(directory)
    if not directory.is_dir():
        log.warning("metadata directory not found; titles/dates will fall back to notes", extra={"dir": str(directory)})
        return {}

    files = sorted(directory.glob("meetings_*.csv"))
    meta: dict[uuid.UUID, MeetingMeta] = {}
    for path in (p for p in files if p.name.startswith("meetings_deduped")):
        for _, reader in _rows(path):
            for row in reader:
                mid = _uuid(row.get("uuid"))
                if mid is None or mid in meta:
                    continue
                meta[mid] = MeetingMeta(
                    subject=(row.get("subject") or "").strip(),
                    start_at=parse_dt(row.get("start")),
                    duration_sec=_duration_sec(row.get("duration_min")),
                    owner_key=(row.get("owner_key") or "").strip() or None,
                    transcription_uuid=_uuid(row.get("transcription_uuid")),
                )

    accounts: dict[uuid.UUID, set[str]] = {}
    for path in (p for p in files if not p.name.startswith("meetings_deduped")):
        for fields, reader in _rows(path):
            if "owner" not in fields or "uuid" not in fields:
                continue
            for row in reader:
                mid, owner = _uuid(row.get("uuid")), (row.get("owner") or "").strip()
                if mid and owner:
                    accounts.setdefault(mid, set()).add(owner)

    for mid, owners in accounts.items():
        if mid in meta:
            meta[mid].accounts = sorted(owners)
    log.info("metadata loaded", extra={"meetings": len(meta), "with_accounts": sum(1 for m in meta.values() if m.accounts)})
    return meta
