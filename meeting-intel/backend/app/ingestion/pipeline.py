"""Ingestion: scan S3 → meetings/recordings rows; process one meeting → transcript, segments, participants.

Reads only transcript.json and notes.md. Recordings are never downloaded.
"""
import json
import logging
import math
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.aws.s3 import S3Object, S3Store
from app.ingestion.classify import FileKind, classify_key
from app.ingestion.metadata import MeetingMeta
from app.ingestion.notes import parse_notes
from app.ingestion.transcript import parse_transcript
from app.models import Meeting, MeetingParticipant, Participant, Recording, Transcript, TranscriptSegment

log = logging.getLogger("app.ingestion")

PLACEHOLDER_SUBJECT = "Untitled meeting"
TRANSCRIPT_FILE = "transcript.json"
NOTES_FILE = "notes.md"
SKIP_NOTE_SECTIONS = {"participants"}
_GENERIC_SPEAKER = re.compile(r"^(speaker \d+|unknown speaker)$", re.I)
_CONTENT_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav", ".mp4": "video/mp4", ".webm": "video/webm"}


@dataclass
class ScanResult:
    objects_scanned: int = 0
    audio_files: int = 0
    transcript_files: int = 0
    notes_files: int = 0
    unknown_files: int = 0
    meetings_identified: int = 0
    duplicates: int = 0
    to_process: list[uuid.UUID] = field(default_factory=list)


def _content_type(key: str) -> str:
    for ext, ct in _CONTENT_TYPES.items():
        if key.lower().endswith(ext):
            return ct
    return "application/octet-stream"


def scan_bucket(
    db: Session,
    store: S3Store,
    prefixes: list[str],
    meta: dict[uuid.UUID, MeetingMeta],
    only_failed: bool = False,
) -> ScanResult:
    r = ScanResult()
    found: dict[uuid.UUID, dict[str, dict[FileKind, S3Object]]] = defaultdict(lambda: defaultdict(dict))

    for obj in store.iter_objects(prefixes):
        r.objects_scanned += 1
        c = classify_key(obj.key, prefixes)
        if c.kind == FileKind.UNKNOWN:
            r.unknown_files += 1
            continue
        r.audio_files += c.kind == FileKind.AUDIO
        r.transcript_files += c.kind == FileKind.TRANSCRIPT
        r.notes_files += c.kind == FileKind.NOTES_MD
        found[c.meeting_id][c.folder][c.kind] = obj

    r.meetings_identified = len(found)
    existing = {m.id: m for m in db.scalars(select(Meeting))}
    chosen: dict[uuid.UUID, dict[FileKind, S3Object]] = {}

    for mid, folders in found.items():
        folder = sorted(folders)[0]
        r.duplicates += len(folders) - 1
        files = folders[folder]
        chosen[mid] = files
        mm = meta.get(mid)
        m = existing.get(mid)
        if m is None:
            m = Meeting(id=mid, subject=(mm.subject if mm and mm.subject else PLACEHOLDER_SUBJECT), s3_folder=folder)
            db.add(m)
            existing[mid] = m
        m.s3_folder = folder
        m.has_transcript = FileKind.TRANSCRIPT in files
        m.has_notes = FileKind.NOTES_MD in files
        m.has_recording = FileKind.AUDIO in files or FileKind.VIDEO in files
        if mm:
            if mm.subject:
                m.subject = mm.subject
            m.start_at = mm.start_at or m.start_at
            m.duration_sec = mm.duration_sec or m.duration_sec
            m.owner_key = mm.owner_key
            m.accounts = mm.accounts
            m.transcription_uuid = mm.transcription_uuid or m.transcription_uuid
    db.flush()

    _sync_recordings(db, chosen)
    r.duplicates += _mark_transcript_duplicates(db, [existing[mid] for mid in chosen])

    for mid, files in chosen.items():
        m = existing[mid]
        if m.ingest_status == "skipped":
            continue
        if only_failed:
            if m.ingest_status == "failed":
                r.to_process.append(mid)
            continue
        t, n = files.get(FileKind.TRANSCRIPT), files.get(FileKind.NOTES_MD)
        changed = (t.etag if t else None) != m.transcript_etag or (n.etag if n else None) != m.notes_etag
        if m.ingest_status != "indexed" or changed:
            r.to_process.append(mid)

    r.to_process.sort(key=lambda i: (existing[i].start_at or datetime.max.replace(tzinfo=UTC), str(i)))
    db.commit()
    log.info("scan complete", extra={k: v for k, v in r.__dict__.items() if k != "to_process"} | {"to_process": len(r.to_process)})
    return r


def _sync_recordings(db: Session, chosen: dict[uuid.UUID, dict[FileKind, S3Object]]) -> None:
    current = {(rec.meeting_id, rec.kind): rec for rec in db.scalars(select(Recording))}
    wanted: set[tuple[uuid.UUID, str]] = set()
    for mid, files in chosen.items():
        for fk, kind in ((FileKind.AUDIO, "audio"), (FileKind.VIDEO, "video")):
            obj = files.get(fk)
            if obj is None:
                continue
            wanted.add((mid, kind))
            rec = current.get((mid, kind))
            if rec is None:
                rec = Recording(meeting_id=mid, kind=kind, s3_key=obj.key, content_type=_content_type(obj.key))
                db.add(rec)
            rec.s3_key, rec.size_bytes, rec.etag = obj.key, obj.size, obj.etag
            rec.storage_class, rec.content_type = obj.storage_class, _content_type(obj.key)
    for key, rec in current.items():
        if key[0] in chosen and key not in wanted:
            db.delete(rec)  # file no longer in S3 → drop our pointer (S3 itself is never touched)
    db.flush()


def _mark_transcript_duplicates(db: Session, meetings: list[Meeting]) -> int:
    """Different meeting ids that share one transcription are the same meeting; keep the earliest."""
    by_tx: dict[uuid.UUID, list[Meeting]] = defaultdict(list)
    for m in meetings:
        if m.transcription_uuid:
            by_tx[m.transcription_uuid].append(m)
    dupes = 0
    keep_ids: set[uuid.UUID] = set()
    for group in by_tx.values():
        group.sort(key=lambda m: (m.start_at or datetime.max.replace(tzinfo=UTC), str(m.id)))
        keep_ids.add(group[0].id)
        for m in group[1:]:
            m.duplicate_of = group[0].id
            m.ingest_status = "skipped"
            dupes += 1
    for m in meetings:
        if m.duplicate_of and (not m.transcription_uuid or m.id in keep_ids or len(by_tx[m.transcription_uuid]) < 2):
            m.duplicate_of = None
            if m.ingest_status == "skipped":
                m.ingest_status = "discovered"
    db.flush()
    return dupes


def _participant_key(email: str | None, name: str) -> str:
    return f"email:{email}" if email else "name:" + " ".join(name.lower().split())


def _upsert_participant(db: Session, name: str, email: str | None, is_internal: bool) -> int:
    stmt = pg_insert(Participant).values(
        name=name, email=email, is_internal=is_internal, normalized_key=_participant_key(email, name)
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Participant.normalized_key],
        set_={
            "is_internal": Participant.is_internal | stmt.excluded.is_internal,
            "email": func.coalesce(Participant.email, stmt.excluded.email),
            "updated_at": datetime.now(UTC),
        },
    ).returning(Participant.id)
    return db.execute(stmt).scalar_one()


def process_meeting(db: Session, store: S3Store, meeting_id: uuid.UUID, meta: MeetingMeta | None) -> bool:
    """Parse one meeting's transcript + notes into the DB. Returns False (and records the error) on failure."""
    m = db.get(Meeting, meeting_id)
    if m is None:
        return False
    try:
        _process(db, store, m, meta)
        db.commit()
        return True
    except Exception as e:  # one bad meeting must not stop the run
        db.rollback()
        m = db.get(Meeting, meeting_id)
        m.ingest_status = "failed"
        m.ingest_error = f"{type(e).__name__}: {e}"[:2000]
        m.ingest_attempts = (m.ingest_attempts or 0) + 1
        db.commit()
        log.warning("meeting failed", extra={"meeting_id": str(meeting_id), "error": m.ingest_error})
        return False


MIN_EMBED_WORDS = 4
EMBED_BATCH = 64
EMBED_MAX_CHARS = 8000


def embed_meeting(db: Session, embedder, meeting_id: uuid.UUID) -> bool:
    """Embed this meeting's not-yet-embedded segments, then mark it indexed. False (and recorded) on failure."""
    m = db.get(Meeting, meeting_id)
    if m is None:
        return False
    try:
        rows = db.execute(
            select(TranscriptSegment.id, TranscriptSegment.speaker_name, TranscriptSegment.section, TranscriptSegment.text)
            .where(TranscriptSegment.meeting_id == meeting_id, TranscriptSegment.embedding.is_(None))
            .order_by(TranscriptSegment.kind, TranscriptSegment.seq)
        ).all()
        todo = [r for r in rows if len(r.text.split()) >= MIN_EMBED_WORDS]
        for i in range(0, len(todo), EMBED_BATCH):
            chunk = todo[i : i + EMBED_BATCH]
            texts = [f"{m.subject} | {r.speaker_name or r.section}: {r.text}"[:EMBED_MAX_CHARS] for r in chunk]
            vectors = embedder.embed_documents(texts)
            db.execute(update(TranscriptSegment), [{"id": r.id, "embedding": v} for r, v in zip(chunk, vectors)])
        m.ingest_status = "indexed"
        m.indexed_at = datetime.now(UTC)
        m.ingest_error = None
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        m = db.get(Meeting, meeting_id)
        m.ingest_status = "failed"
        m.ingest_error = f"embedding: {type(e).__name__}: {e}"[:2000]
        m.ingest_attempts = (m.ingest_attempts or 0) + 1
        db.commit()
        log.warning("embedding failed", extra={"meeting_id": str(meeting_id), "error": m.ingest_error})
        return False


def _process(db: Session, store: S3Store, m: Meeting, meta: MeetingMeta | None) -> None:
    parsed = notes = None
    t_etag = n_etag = None
    if m.has_transcript:
        raw, t_etag = store.fetch(m.s3_folder + TRANSCRIPT_FILE)
        parsed = parse_transcript(json.loads(raw))
    if m.has_notes:
        raw, n_etag = store.fetch(m.s3_folder + NOTES_FILE)
        notes = parse_notes(raw.decode("utf-8", errors="replace"))

    db.execute(delete(TranscriptSegment).where(TranscriptSegment.meeting_id == m.id))
    db.execute(delete(MeetingParticipant).where(MeetingParticipant.meeting_id == m.id))
    db.execute(delete(Transcript).where(Transcript.meeting_id == m.id))

    speaker_pid: dict[int, int] = {}
    transcript_id = None
    if parsed:
        speaking: dict[int | None, float] = defaultdict(float)
        for s in parsed.segments:
            speaking[s.speaker_id] += max(0.0, s.end_sec - s.start_sec)
        rows: dict[int, dict] = {}
        for sp in parsed.speakers:
            if not sp.email and _GENERIC_SPEAKER.match(sp.name):
                continue
            pid = _upsert_participant(db, sp.name, sp.email, sp.is_internal)
            speaker_pid[sp.id] = pid
            row = rows.setdefault(pid, {"meeting_id": m.id, "participant_id": pid, "speaker_id": sp.id,
                                        "speaking_sec": 0.0, "is_internal": sp.is_internal})
            row["speaking_sec"] += speaking.get(sp.id, 0.0)
            row["is_internal"] = row["is_internal"] or sp.is_internal
        if rows:
            for row in rows.values():
                row["speaking_sec"] = round(row["speaking_sec"], 2)
            db.execute(insert(MeetingParticipant), list(rows.values()))

        transcript_id = db.execute(
            insert(Transcript).values(
                meeting_id=m.id,
                s3_key=m.s3_folder + TRANSCRIPT_FILE,
                transcription_uuid=parsed.transcription_uuid,
                etag=t_etag,
                segment_count=len(parsed.segments),
                word_count=sum(s.word_count for s in parsed.segments),
                speaker_count=len(parsed.speakers),
                last_word_sec=parsed.last_word_sec,
                source_modified_at=parsed.modified,
            ).returning(Transcript.id)
        ).scalar_one()

    seg_rows = []
    if parsed:
        seg_rows += [
            {"meeting_id": m.id, "transcript_id": transcript_id, "kind": "utterance", "seq": s.seq,
             "participant_id": speaker_pid.get(s.speaker_id) if s.speaker_id is not None else None,
             "speaker_name": s.speaker_name, "section": None, "start_sec": s.start_sec, "end_sec": s.end_sec,
             "text": s.text}
            for s in parsed.segments
        ]
    if notes:
        note_sections = [s for s in notes.sections if s.text.strip() and s.heading.lower() not in SKIP_NOTE_SECTIONS]
        seg_rows += [
            {"meeting_id": m.id, "transcript_id": None, "kind": "note", "seq": i, "participant_id": None,
             "speaker_name": None, "section": s.heading, "start_sec": None, "end_sec": None, "text": s.text}
            for i, s in enumerate(note_sections)
        ]
    if seg_rows:
        db.execute(insert(TranscriptSegment), seg_rows)

    if not (meta and meta.subject) and notes and notes.title and m.subject == PLACEHOLDER_SUBJECT:
        m.subject = notes.title
    if m.start_at is None and notes and notes.start_at:
        m.start_at = notes.start_at
    if not m.duration_sec and parsed and parsed.last_word_sec > 0:
        m.duration_sec = math.ceil(parsed.last_word_sec)
    if parsed and parsed.transcription_uuid and not m.transcription_uuid:
        m.transcription_uuid = parsed.transcription_uuid
    m.topics = notes.topics if notes else []
    m.notes_md = notes.markdown if notes else None
    m.transcript_etag, m.notes_etag = t_etag, n_etag
    m.ingest_status = "parsed"
    m.ingest_error = None
    m.parsed_at = datetime.now(UTC)
    m.indexed_at = None
