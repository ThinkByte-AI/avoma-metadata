import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import func, select

from app.aws.s3 import S3Store
from app.ingestion.metadata import MeetingMeta, load_metadata
from app.ingestion.pipeline import process_meeting, scan_bucket
from app.models import Meeting, MeetingParticipant, Participant, Recording, Transcript, TranscriptSegment

FIX = Path(__file__).parent / "fixtures"
REGION = "ap-south-1"
A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
C = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
E = uuid.UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
T = uuid.UUID("11111111-1111-4111-8111-111111111111")
P = ["avoma/"]


def _put(client, key, body):
    client.put_object(Bucket="test-bucket", Key=key, Body=body if isinstance(body, bytes) else body.encode())


@pytest.fixture
def bucket():
    with mock_aws():
        c = boto3.client("s3", region_name=REGION)
        c.create_bucket(Bucket="test-bucket", CreateBucketConfiguration={"LocationConstraint": REGION})
        basic = (FIX / "transcript_basic.json").read_text(encoding="utf-8")
        notes = (FIX / "notes_basic.md").read_text(encoding="utf-8")
        _put(c, f"avoma/2025/02/{A}/transcript.json", basic)
        _put(c, f"avoma/2025/02/{A}/notes.md", notes)
        _put(c, f"avoma/2025/02/{A}/recording.mp3", b"ID3" + b"\0" * 100)
        _put(c, f"avoma/2025/02/{A}/recording.mp4", b"\0" * 300)
        _put(c, f"avoma/2025/02/{A}/random.txt", "junk")
        _put(c, f"avoma/2025/03/{A}/transcript.json", basic)  # same meeting id in a second folder
        _put(c, f"avoma/2025/03/{B}/transcript.json", (FIX / "transcript_messy.json").read_text(encoding="utf-8"))
        _put(c, f"avoma/2024/11/{C}/notes.md", "# Marketing Strategy\n_2024-11-20T10:00:00Z_\n\n## Key Takeaways\n- Focus on SEO.\n")
        _put(c, f"avoma/2024/11/{C}/recording.mp3", b"ID3" + b"\0" * 50)
        _put(c, f"avoma/2025/02/{E}/transcript.json", basic)  # same transcription uuid as A
        _put(c, "avoma/readme.txt", "not a meeting")
        yield c


@pytest.fixture
def store(bucket):
    return S3Store("test-bucket", REGION)


@pytest.fixture
def meta():
    m = load_metadata(FIX / "csv")
    m[E] = MeetingMeta("Weekly Revenue Review (copy)", datetime(2025, 2, 12, tzinfo=UTC), 600, "Bob", T, ["Bob"])
    return m


def test_scan_counts_and_ignores_unknown(db, store, meta):
    r = scan_bucket(db, store, P, meta)
    assert (r.objects_scanned, r.audio_files, r.transcript_files, r.notes_files, r.unknown_files) == (11, 2, 4, 2, 2)
    assert r.meetings_identified == 4
    assert r.duplicates == 2
    assert sorted(r.to_process) == sorted([A, B, C])
    assert db.scalar(select(func.count()).select_from(Meeting)) == 4


def test_scan_creates_meetings_with_metadata_and_accounts(db, store, meta):
    scan_bucket(db, store, P, meta)
    a = db.get(Meeting, A)
    assert a.subject == "Weekly Revenue Review" and a.owner_key == "Alice" and a.accounts == ["Alice", "Bob"]
    assert a.start_at == datetime(2025, 2, 11, 14, tzinfo=UTC) and a.duration_sec == 2490
    assert (a.has_recording, a.has_transcript, a.has_notes, a.ingest_status) == (True, True, True, "discovered")
    recs = {r.kind: r for r in db.scalars(select(Recording).where(Recording.meeting_id == A))}
    assert recs["audio"].s3_key == f"avoma/2025/02/{A}/recording.mp3" and recs["audio"].content_type == "audio/mpeg"
    assert recs["audio"].size_bytes == 103 and recs["audio"].storage_class == "STANDARD"
    assert recs["video"].content_type == "video/mp4"


def test_duplicate_folder_counted_once(db, store, meta):
    scan_bucket(db, store, P, meta)
    assert db.get(Meeting, A).s3_folder == f"avoma/2025/02/{A}/"


def test_shared_transcription_uuid_marked_duplicate(db, store, meta):
    r = scan_bucket(db, store, P, meta)
    e = db.get(Meeting, E)
    assert e.duplicate_of == A and e.ingest_status == "skipped" and E not in r.to_process


def test_meeting_without_recording_has_flag_false(db, store, meta):
    scan_bucket(db, store, P, meta)
    b = db.get(Meeting, B)
    assert (b.has_recording, b.has_transcript, b.has_notes) == (False, True, False)
    assert db.scalar(select(func.count()).select_from(Recording).where(Recording.meeting_id == B)) == 0


def test_missing_metadata_gets_placeholder_subject(db, store):
    scan_bucket(db, store, P, {})
    assert db.get(Meeting, B).subject == "Untitled meeting"


def test_process_meeting_writes_segments_participants_notes(db, store, meta):
    scan_bucket(db, store, P, meta)
    assert process_meeting(db, store, A, meta[A]) is True
    a = db.get(Meeting, A)
    assert a.ingest_status == "parsed" and a.parsed_at is not None and a.ingest_error is None
    assert a.topics == ["Spending And Revenue"] and a.notes_md.startswith("# Weekly Revenue Review")
    assert a.transcript_etag and a.notes_etag

    utt = db.scalars(
        select(TranscriptSegment).where(TranscriptSegment.meeting_id == A, TranscriptSegment.kind == "utterance")
        .order_by(TranscriptSegment.seq)
    ).all()
    assert [(s.seq, s.speaker_name, float(s.start_sec), float(s.end_sec)) for s in utt] == [
        (0, "Alice Tester", 10.0, 13.0), (1, "Bob Client", 14.0, 15.5), (2, "Alice Tester", 16.0, 17.5),
    ]
    notes = db.scalars(
        select(TranscriptSegment).where(TranscriptSegment.meeting_id == A, TranscriptSegment.kind == "note")
        .order_by(TranscriptSegment.seq)
    ).all()
    assert [n.section for n in notes] == ["Key Takeaways", "Action Items", "spending and revenue", "Next Steps"]
    assert all(n.start_sec is None and n.participant_id is None for n in notes)

    people = {p.email: p for p in db.scalars(select(Participant))}
    assert set(people) == {"alice@example.com", "bob@client.example"}
    assert people["alice@example.com"].is_internal is True and people["bob@client.example"].is_internal is False
    assert utt[0].participant_id == people["alice@example.com"].id
    mp = {r.participant_id: r for r in db.scalars(select(MeetingParticipant).where(MeetingParticipant.meeting_id == A))}
    assert float(mp[people["alice@example.com"].id].speaking_sec) == 4.5
    assert float(mp[people["bob@client.example"].id].speaking_sec) == 1.5

    t = db.scalar(select(Transcript).where(Transcript.meeting_id == A))
    assert (t.segment_count, t.word_count, t.speaker_count, float(t.last_word_sec)) == (3, 20, 2, 17.5)
    assert t.transcription_uuid == T

    chunk = db.scalars(select(TranscriptSegment).where(TranscriptSegment.meeting_id == A,
                                                       TranscriptSegment.kind == "chunk")).one()
    assert chunk.text == ("Alice Tester: Hi Bob, good evening. Let us review revenue.\n"
                          "Bob Client: Revenue grew five percent last quarter.\n"
                          "Alice Tester: Great, what about the marketing budget?")
    assert (float(chunk.start_sec), float(chunk.end_sec), chunk.seq) == (10.0, 17.5, 0)
    assert chunk.speaker_name == "Alice Tester, Bob Client" and chunk.participant_id is None
    assert sorted(chunk.participant_ids) == sorted(p.id for p in people.values())


def test_generic_speakers_are_not_participants(db, store, meta):
    scan_bucket(db, store, P, meta)
    assert process_meeting(db, store, B, meta[B]) is True
    names = sorted(p.name for p in db.scalars(select(Participant)))
    assert names == ["Carol"]
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.meeting_id == B, TranscriptSegment.kind == "utterance")
                      .order_by(TranscriptSegment.seq)).all()
    assert [s.speaker_name for s in segs] == ["Carol", "Speaker 9", "Carol", "Speaker 1", "Unknown speaker"]
    assert segs[1].participant_id is None


def test_process_without_transcript_falls_back_to_notes(db, store):
    scan_bucket(db, store, P, {})
    assert process_meeting(db, store, C, None) is True
    c = db.get(Meeting, C)
    assert c.subject == "Marketing Strategy" and c.start_at == datetime(2024, 11, 20, 10, tzinfo=UTC)
    assert c.ingest_status == "parsed"
    assert db.scalar(select(func.count()).select_from(TranscriptSegment).where(TranscriptSegment.meeting_id == C)) == 1


def test_duration_falls_back_to_last_word(db, store):
    scan_bucket(db, store, P, {})
    process_meeting(db, store, A, None)
    assert db.get(Meeting, A).duration_sec == 18  # ceil(17.5)


def test_reprocess_is_idempotent(db, store, meta):
    scan_bucket(db, store, P, meta)
    process_meeting(db, store, A, meta[A])
    counts = lambda: tuple(  # noqa: E731
        db.scalar(select(func.count()).select_from(t)) for t in (TranscriptSegment, Participant, MeetingParticipant, Transcript)
    )
    first = counts()
    scan_bucket(db, store, P, meta)
    process_meeting(db, store, A, meta[A])
    assert counts() == first == (8, 2, 2, 1)


def test_same_email_reused_across_meetings(db, store, meta):
    scan_bucket(db, store, P, meta)
    process_meeting(db, store, A, meta[A])
    process_meeting(db, store, E, meta[E])
    assert db.scalar(select(func.count()).select_from(Participant)) == 2
    assert db.scalar(select(func.count()).select_from(MeetingParticipant)) == 4


def test_unchanged_indexed_meeting_not_in_to_process(db, store, meta):
    scan_bucket(db, store, P, meta)
    process_meeting(db, store, A, meta[A])
    db.get(Meeting, A).ingest_status = "indexed"
    db.commit()
    assert A not in scan_bucket(db, store, P, meta).to_process


def test_changed_etag_requeues(db, store, bucket, meta):
    scan_bucket(db, store, P, meta)
    process_meeting(db, store, A, meta[A])
    db.get(Meeting, A).ingest_status = "indexed"
    db.commit()
    changed = json.loads((FIX / "transcript_basic.json").read_text(encoding="utf-8"))
    changed[0]["transcript"].append({"speaker_id": 1, "transcript": "One more thing.", "timestamps": [20.0, 20.3, 20.6]})
    _put(bucket, f"avoma/2025/02/{A}/transcript.json", json.dumps(changed))
    assert A in scan_bucket(db, store, P, meta).to_process


def test_corrupt_json_marks_failed_and_continues(db, store, bucket, meta):
    _put(bucket, f"avoma/2025/03/{B}/transcript.json", "{not json")
    scan_bucket(db, store, P, meta)
    assert process_meeting(db, store, B, meta[B]) is False
    b = db.get(Meeting, B)
    assert b.ingest_status == "failed" and "JSONDecodeError" in b.ingest_error and b.ingest_attempts == 1
    assert db.scalar(select(func.count()).select_from(TranscriptSegment).where(TranscriptSegment.meeting_id == B)) == 0
    assert process_meeting(db, store, A, meta[A]) is True


def test_only_failed_returns_failed_only(db, store, bucket, meta):
    _put(bucket, f"avoma/2025/03/{B}/transcript.json", "{not json")
    scan_bucket(db, store, P, meta)
    process_meeting(db, store, B, meta[B])
    assert scan_bucket(db, store, P, meta, only_failed=True).to_process == [B]


def test_never_reads_recordings(db, store, meta):
    seen: list[str] = []
    real = store.client.get_object

    def spy(**kw):
        seen.append(kw["Key"])
        return real(**kw)

    store.client.get_object = spy
    r = scan_bucket(db, store, P, meta)
    for mid in r.to_process:
        process_meeting(db, store, mid, meta.get(mid))
    assert seen and not [k for k in seen if k.endswith((".mp3", ".mp4"))]


def test_make_chunks_groups_turns_to_target_words():
    from app.ingestion.pipeline import make_chunks
    from app.ingestion.transcript import Segment

    segs = [Segment(i, i % 2, f"P{i % 2}", float(i * 10), float(i * 10 + 5), " ".join(["w"] * 40), 40) for i in range(10)]
    chunks = make_chunks(segs, {0: 100, 1: 200}, target_words=100, max_words=150)
    assert [c["word_count"] for c in chunks] == [120, 120, 120, 40]
    assert chunks[0]["text"].startswith("P0: w w") and chunks[0]["text"].count("\n") == 2
    assert (chunks[1]["start_sec"], chunks[1]["end_sec"]) == (30.0, 55.0)
    assert chunks[0]["participant_ids"] == [100, 200] and chunks[0]["speaker_name"] == "P0, P1"
    assert [c["seq"] for c in chunks] == [0, 1, 2, 3]


def test_make_chunks_never_exceeds_max_except_single_long_turn():
    from app.ingestion.pipeline import make_chunks
    from app.ingestion.transcript import Segment

    segs = [Segment(0, 0, "A", 0.0, 1.0, " ".join(["w"] * 400), 400), Segment(1, 0, "A", 2.0, 3.0, "short line here", 3)]
    assert [c["word_count"] for c in make_chunks(segs, {}, target_words=150, max_words=300)] == [400, 3]
    assert make_chunks([], {}) == []
