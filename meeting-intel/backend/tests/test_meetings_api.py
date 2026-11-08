import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.aws.s3 import S3Store, get_store
from app.models import AuditLog, Meeting
from tests.conftest import _client_for, login
from tests.seed import M1, M2, M3, M4, seed_search_data


@pytest.fixture
def seeded(db):
    return seed_search_data(db)


@pytest.fixture
def as_user(app, db, make_user, seeded):
    app.dependency_overrides[get_store] = lambda: S3Store("test-bucket", "ap-south-1")

    def _as(email, **kw):
        make_user(email, **kw)
        c = _client_for(app, db)
        login(c, email)
        return c

    return _as


@pytest.fixture
def admin(as_user):
    return as_user("admin@example.com", role="admin", can_download=True)


def _ids(page):
    return [m["id"] for m in page["items"]]


def test_meeting_detail_404_for_inaccessible(as_user):
    dave = as_user("dave@example.com")
    for path in ("", "/transcript", "/recording"):
        r = dave.get(f"/api/meetings/{M1}{path}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found", path


def test_unknown_meeting_404(admin):
    assert admin.get(f"/api/meetings/{uuid.uuid4()}").status_code == 404


def test_meeting_detail_fields(admin):
    d = admin.get(f"/api/meetings/{M1}").json()
    assert d["subject"] == "Weekly Revenue Review" and d["owner_key"] == "Alice" and d["accounts"] == ["Alice"]
    assert {p["name"]: p["speaking_sec"] for p in d["participants"]} == {"Alice Tester": 6.0, "Bob Client": 6.0}
    assert d["notes_md"].startswith("## Key Takeaways")
    assert sorted((r["kind"], r["size_bytes"]) for r in d["recordings"]) == [("audio", 1000), ("video", 3000)]
    assert d["transcript"] == {"segment_count": 3, "word_count": 24}
    assert d["ingest_status"] == "indexed"


def test_transcript_ordered_with_speakers(admin):
    t = admin.get(f"/api/meetings/{M1}/transcript").json()
    assert [(s["seq"], s["speaker_name"], s["start_sec"]) for s in t["segments"]] == [
        (0, "Alice Tester", 10.0), (1, "Bob Client", 14.0), (2, "Alice Tester", 21.0)]
    assert t["segments"][1]["text"].startswith("Revenue grew") and t["segments"][1]["end_sec"] == 20.0
    assert {s["name"] for s in t["speakers"]} == {"Alice Tester", "Bob Client"}


def test_transcript_missing_404(admin, db):
    mid = uuid.uuid4()
    db.add(Meeting(id=mid, subject="Audio only", s3_folder="x/", has_recording=True, has_transcript=False))
    db.commit()
    r = admin.get(f"/api/meetings/{mid}/transcript")
    assert r.status_code == 404 and r.json()["error"]["code"] == "transcript_not_found"


def test_recording_presign_audio_content_type(admin):
    before = datetime.now(UTC)
    r = admin.get(f"/api/meetings/{M1}/recording").json()
    assert r["kind"] == "audio" and r["content_type"] == "audio/mpeg"
    q = parse_qs(urlparse(r["url"]).query)
    assert q["response-content-type"] == ["audio/mpeg"] and "response-content-disposition" not in q
    exp = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
    assert before + timedelta(seconds=890) < exp < before + timedelta(seconds=910)
    assert f"{M1}/recording.mp3" in urlparse(r["url"]).path


def test_recording_video_kind(admin):
    r = admin.get(f"/api/meetings/{M1}/recording", params={"kind": "video"}).json()
    assert r["content_type"] == "video/mp4" and r["kind"] == "video"


def test_recording_missing_404(admin):
    r = admin.get(f"/api/meetings/{M2}/recording")
    assert r.status_code == 404 and r.json()["error"]["code"] == "recording_not_found"


def test_download_requires_permission_403(as_user, admin):
    alice = as_user("alice-user@example.com", account_label="Alice")
    assert alice.get(f"/api/meetings/{M1}/recording").status_code == 200
    r = alice.get(f"/api/meetings/{M1}/recording", params={"download": "true"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "download_not_allowed"
    url = admin.get(f"/api/meetings/{M1}/recording", params={"download": "true"}).json()["url"]
    disp = parse_qs(urlparse(url).query)["response-content-disposition"][0]
    assert disp.startswith('attachment; filename="Weekly Revenue Review-') and disp.endswith('.mp3"')


def test_download_filename_is_sanitised(admin, db):
    m = db.get(Meeting, M1)
    m.subject = 'Q3 "Plan" <> Café/Review'
    db.commit()
    url = admin.get(f"/api/meetings/{M1}/recording", params={"download": "true"}).json()["url"]
    disp = parse_qs(urlparse(url).query)["response-content-disposition"][0]
    name = disp.split('filename="')[1][:-1]
    assert '"' not in name and "/" not in name and "<" not in name and name.startswith("Q3 Plan")


def test_recording_access_audited(admin, db):
    admin.get(f"/api/meetings/{M1}/recording", params={"download": "true"})
    a = db.scalars(select(AuditLog).where(AuditLog.action == "recording.access")).one()
    assert a.target_id == str(M1) and a.details == {"kind": "audio", "download": True}


def test_meetings_list_filters_and_sort(admin, seeded):
    page = admin.get("/api/meetings").json()
    assert page["total"] == 4 and _ids(page) == [str(M1), str(M2), str(M3), str(M4)]
    assert _ids(admin.get("/api/meetings", params={"sort": "title"}).json()) == [str(M3), str(M2), str(M4), str(M1)]
    assert _ids(admin.get("/api/meetings", params={"has_recording": "false"}).json()) == [str(M2)]
    assert _ids(admin.get("/api/meetings", params={"participant_id": seeded.people["erin"]}).json()) == [str(M3)]
    assert _ids(admin.get("/api/meetings", params={"title": "revenue"}).json()) == [str(M1)]
    assert _ids(admin.get("/api/meetings", params={"owner": "Zed"}).json()) == [str(M4)]
    p2 = admin.get("/api/meetings", params={"page": 2, "page_size": 3}).json()
    assert p2["total"] == 4 and _ids(p2) == [str(M4)]


def test_meetings_list_scoped(as_user):
    alice = as_user("alice-user@example.com", account_label="Alice")
    assert _ids(alice.get("/api/meetings").json()) == [str(M1), str(M3)]
