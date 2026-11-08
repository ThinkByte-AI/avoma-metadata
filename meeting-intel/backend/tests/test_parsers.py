import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.ingestion.metadata import load_metadata
from app.ingestion.notes import parse_notes
from app.ingestion.transcript import parse_transcript

FIX = Path(__file__).parent / "fixtures"
A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
C = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# --- metadata ---------------------------------------------------------------

def test_metadata_first_deduped_file_wins():
    meta = load_metadata(FIX / "csv")
    assert set(meta) == {A, B, C}
    a = meta[A]
    assert a.subject == "Weekly Revenue Review"
    assert a.start_at == datetime(2025, 2, 11, 14, 0, tzinfo=UTC)
    assert a.duration_sec == 2490  # 41.5 min
    assert a.owner_key == "Alice"
    assert a.transcription_uuid == uuid.UUID("11111111-1111-4111-8111-111111111111")


def test_metadata_handles_quoted_subject_and_blank_duration():
    c = load_metadata(FIX / "csv")[C]
    assert c.subject == "Marketing Strategy, Q4" and c.duration_sec is None and c.transcription_uuid is None


def test_metadata_accounts_from_owner_column():
    meta = load_metadata(FIX / "csv")
    assert meta[A].accounts == ["Alice", "Bob"]
    assert meta[B].accounts == ["Bob"]  # meetings_2yr.csv has no owner column and is ignored
    assert meta[C].accounts == ["Alice"]


def test_metadata_missing_dir_returns_empty(tmp_path):
    assert load_metadata(tmp_path / "nope") == {}


# --- transcript --------------------------------------------------------------

def test_parse_basic_transcript():
    t = parse_transcript(_load("transcript_basic.json"))
    assert t.transcription_uuid == uuid.UUID("11111111-1111-4111-8111-111111111111")
    assert t.meeting_uuid == A
    assert t.modified == datetime(2025, 2, 11, 14, 48, 17, 51057, tzinfo=UTC)
    assert [(s.id, s.name, s.email, s.is_internal) for s in t.speakers] == [
        (0, "Alice Tester", "alice@example.com", True),
        (1, "Bob Client", "bob@client.example", False),
    ]
    assert len(t.segments) == 3
    s0 = t.segments[0]
    assert (s0.seq, s0.speaker_id, s0.speaker_name, s0.start_sec, s0.end_sec) == (0, 0, "Alice Tester", 10.0, 13.0)
    assert s0.text == "Hi Bob, good evening. Let us review revenue." and s0.word_count == 8
    assert (t.segments[1].speaker_name, t.segments[1].start_sec, t.segments[1].end_sec) == ("Bob Client", 14.0, 15.5)
    assert t.last_word_sec == 17.5


def test_merges_same_speaker_runs():
    raw = {"speakers": [{"id": 0, "name": "A"}], "transcript": [
        {"speaker_id": 0, "transcript": "one two", "timestamps": [1, 2]},
        {"speaker_id": 0, "transcript": "three", "timestamps": [3]},
    ]}
    t = parse_transcript(raw)
    assert [(s.text, s.start_sec, s.end_sec) for s in t.segments] == [("one two three", 1.0, 3.0)]


def test_splits_runs_over_220_words():
    words = " ".join(["w"] * 100)
    raw = {"speakers": [{"id": 0, "name": "A"}], "transcript": [
        {"speaker_id": 0, "transcript": words, "timestamps": [float(i) for i in range(100)]},
        {"speaker_id": 0, "transcript": words, "timestamps": [float(100 + i) for i in range(100)]},
        {"speaker_id": 0, "transcript": words, "timestamps": [float(200 + i) for i in range(100)]},
    ]}
    t = parse_transcript(raw)
    assert [s.word_count for s in t.segments] == [200, 100]
    assert (t.segments[1].start_sec, t.segments[1].seq) == (200.0, 1)


def test_messy_transcript_unknown_speaker_and_empty_text():
    t = parse_transcript(_load("transcript_messy.json"))
    assert t.transcription_uuid is None and t.modified is None
    carol = t.speakers[0]
    assert carol.email is None and carol.is_internal is True
    got = [(s.speaker_id, s.speaker_name, s.text, s.start_sec, s.end_sec) for s in t.segments]
    assert got == [
        (0, "Carol", "Opening remarks here.", 5.0, 6.0),
        (9, "Speaker 9", "Who am I?", 7.0, 7.4),
        (0, "Carol", "No timing here.", 7.4, 7.4),
        (1, "Speaker 1", "Blank name speaker.", 9.0, 10.0),
        (None, "Unknown speaker", "Null speaker.", 11.0, 11.5),
    ]
    assert [s.seq for s in t.segments] == [0, 1, 2, 3, 4]


def test_empty_transcript_list():
    for raw in ([], [{"speakers": [], "transcript": []}], {"transcript": None}):
        t = parse_transcript(raw)
        assert t.segments == [] and t.last_word_sec == 0.0


# --- notes ------------------------------------------------------------------

def test_parse_notes_title_date_topics():
    n = parse_notes((FIX / "notes_basic.md").read_text(encoding="utf-8"))
    assert n.title == "Weekly Revenue Review <> Example Co"
    assert n.start_at == datetime(2025, 2, 11, 14, 0, tzinfo=UTC)
    assert [s.heading for s in n.sections] == [
        "Participants", "Key Takeaways", "Action Items", "spending and revenue", "Next Steps",
    ]
    assert n.sections[1].text == "- Revenue grew five percent last quarter.\n- The marketing budget will be reviewed next week."
    assert n.topics == ["Spending And Revenue"]
    assert n.markdown.startswith("# Weekly Revenue Review")


def test_notes_without_title():
    n = parse_notes("## Key Takeaways\n- Something happened.\n")
    assert n.title is None and n.start_at is None and n.topics == []
    assert [(s.heading, s.text) for s in n.sections] == [("Key Takeaways", "- Something happened.")]


def test_notes_empty():
    n = parse_notes("")
    assert n.title is None and n.sections == [] and n.topics == []
