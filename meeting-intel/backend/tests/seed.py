"""Synthetic, clearly fake meetings for search/API tests (written straight to the DB)."""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.ai.embeddings import FakeEmbedder
from app.models import Meeting, MeetingParticipant, Participant, Recording, TranscriptSegment

M1 = uuid.UUID("10000000-0000-4000-8000-000000000001")
M2 = uuid.UUID("20000000-0000-4000-8000-000000000002")
M3 = uuid.UUID("30000000-0000-4000-8000-000000000003")
M4 = uuid.UUID("40000000-0000-4000-8000-000000000004")
M5 = uuid.UUID("50000000-0000-4000-8000-000000000005")  # duplicate of M1


@dataclass
class Seeded:
    now: datetime
    people: dict[str, int]


def _days_ago(now: datetime, d: int) -> datetime:
    return (now - timedelta(days=d)).replace(microsecond=0)


def seed_search_data(db, embedder=None) -> Seeded:
    embedder = embedder or FakeEmbedder()
    now = datetime.now(UTC)
    people_spec = {
        "alice": ("Alice Tester", "alice@example.com", True),
        "bob": ("Bob Client", "bob@client.example", False),
        "carol": ("Carol Ops", "carol@example.com", True),
        "dan": ("Dan Prospect", "dan@prospect.example", False),
        "erin": ("Erin Engineer", "erin@example.com", True),
    }
    people = {}
    for key, (name, email, internal) in people_spec.items():
        p = Participant(name=name, email=email, is_internal=internal, normalized_key=f"email:{email}")
        db.add(p)
        db.flush()
        people[key] = p.id

    meetings = [
        (M1, "Weekly Revenue Review", 3, 2490, "Alice", ["Alice"], True, None, [
            ("alice", "Let us review revenue for the quarter.", 10, 13),
            ("bob", "Revenue grew five percent last quarter thanks to the new pricing.", 14, 20),
            ("alice", "Great, what about the marketing budget?", 21, 24),
        ], [("Key Takeaways", "- Revenue grew five percent.")]),
        (M2, "Client Onboarding Discussion", 40, 1800, "Bob", ["Bob"], False, None, [
            ("carol", "Welcome aboard, we will set up your account this week.", 5, 9),
            ("dan", "We need the onboarding finished before the project deadline.", 10, 15),
            ("carol", "The deadline is achievable if documents arrive Monday.", 16, 20),
        ], []),
        (M3, "AWS Infrastructure Planning", 200, 3600, "Alice", ["Alice", "Bob"], True, None, [
            ("erin", "We should migrate the database to AWS RDS next month.", 30, 35),
            ("alice", "Increasing the budget for cloud infrastructure makes sense.", 36, 40),
        ], []),
        (M4, "Marketing Strategy Session", 500, 2700, "Zed", ["Zed"], True, None, [
            ("bob", "Our marketing strategy focuses on search engine optimisation and paid ads.", 3, 9),
            ("bob", "Revenue targets depend on the marketing strategy.", 10, 14),
        ], []),
        (M5, "Weekly Revenue Review (copy)", 3, 2490, "Alice", ["Alice"], True, M1, [
            ("bob", "Revenue grew five percent last quarter thanks to the new pricing.", 14, 20),
        ], []),
    ]
    for mid, subject, days, dur, owner, accounts, has_rec, dup, utts, notes in meetings:
        db.add(Meeting(
            id=mid, subject=subject, start_at=_days_ago(now, days), duration_sec=dur, owner_key=owner,
            accounts=accounts, s3_folder=f"avoma/x/{mid}/", has_recording=has_rec, has_transcript=True,
            has_notes=bool(notes), notes_md="\n".join(f"## {h}\n{t}" for h, t in notes) or None,
            topics=["Revenue"] if "Revenue" in subject else [], duplicate_of=dup,
            ingest_status="skipped" if dup else "indexed",
        ))
        db.flush()
        if has_rec:
            db.add(Recording(meeting_id=mid, kind="audio", s3_key=f"avoma/x/{mid}/recording.mp3", size_bytes=1000,
                             storage_class="GLACIER_IR", content_type="audio/mpeg"))
            db.add(Recording(meeting_id=mid, kind="video", s3_key=f"avoma/x/{mid}/recording.mp4", size_bytes=3000,
                             storage_class="GLACIER_IR", content_type="video/mp4"))
        speaking: dict[str, float] = {}
        for seq, (who, text, start, end) in enumerate(utts):
            speaking[who] = speaking.get(who, 0) + (end - start)
            name = people_spec[who][0]
            db.add(TranscriptSegment(
                meeting_id=mid, kind="utterance", seq=seq, participant_id=people[who], speaker_name=name,
                start_sec=start, end_sec=end, text=text,
                embedding=embedder.embed_documents([f"{subject} | {name}: {text}"])[0],
            ))
        for seq, (heading, text) in enumerate(notes):
            db.add(TranscriptSegment(
                meeting_id=mid, kind="note", seq=seq, section=heading, text=text,
                embedding=embedder.embed_documents([f"{subject} | {heading}: {text}"])[0],
            ))
        for who, sec in speaking.items():
            db.add(MeetingParticipant(meeting_id=mid, participant_id=people[who], speaker_id=None,
                                      speaking_sec=sec, is_internal=people_spec[who][2]))
    db.commit()
    return Seeded(now=now, people=people)
