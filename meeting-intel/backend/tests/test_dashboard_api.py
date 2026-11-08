from datetime import UTC, datetime

import pytest

from app.ai.embeddings import FakeEmbedder, get_query_embedder
from tests.conftest import _client_for, login
from tests.seed import M1, seed_search_data


@pytest.fixture
def seeded(db):
    return seed_search_data(db)


@pytest.fixture
def as_user(app, db, make_user, seeded):
    app.dependency_overrides[get_query_embedder] = lambda: FakeEmbedder()

    def _as(email, **kw):
        make_user(email, **kw)
        c = _client_for(app, db)
        login(c, email)
        return c

    return _as


@pytest.fixture
def admin(as_user):
    return as_user("admin@example.com", role="admin")


def test_dashboard_stats_values(admin):
    admin.post("/api/search", json={"q": "revenue"})
    s = admin.get("/api/dashboard/stats").json()
    assert (s["total_meetings"], s["total_recordings"], s["total_participants"], s["total_transcripts"]) == (4, 3, 5, 4)
    assert (s["audio_storage_bytes"], s["video_storage_bytes"], s["total_duration_sec"]) == (3000, 9000, 10590)
    assert sum(m["count"] for m in s["meetings_by_month"]) == 4
    assert s["meetings_by_month"] == sorted(s["meetings_by_month"], key=lambda m: m["month"])
    assert [(p["name"], p["count"]) for p in s["top_participants"][:2]] == [("Alice Tester", 2), ("Bob Client", 2)]
    assert s["top_topics"] == [{"topic": "Revenue", "count": 1}]
    assert [m["id"] for m in s["recent_meetings"]][0] == str(M1) and len(s["recent_meetings"]) == 4
    assert len(s["search_activity"]) == 30
    today = datetime.now(UTC).date().isoformat()
    assert s["search_activity"][-1] == {"date": today, "count": 1}


def test_dashboard_scoped_for_standard_user(as_user):
    alice = as_user("alice-user@example.com", account_label="Alice")
    s = alice.get("/api/dashboard/stats").json()
    assert (s["total_meetings"], s["total_participants"], s["total_duration_sec"]) == (2, 3, 6090)


def test_dashboard_requires_login(client):
    assert client.get("/api/dashboard/stats").status_code == 401


def test_analytics_shapes(admin):
    a = admin.get("/api/analytics").json()
    assert round(sum(m["hours"] for m in a["hours_by_month"]), 4) == round(10590 / 3600, 4)
    assert {o["owner"]: o["count"] for o in a["meetings_by_owner"]} == {"Alice": 2, "Bob": 1, "Zed": 1}
    assert a["speaking_leaders"][0]["name"] == "Bob Client"
    assert round(a["speaking_leaders"][0]["hours"] * 3600) == 16
    assert {t["topic"] for t in a["topics_by_month"]} == {"Revenue"}
    iv = a["internal_vs_external_speaking"]
    assert round(iv["internal_hours"] * 3600) == 6 + 4 + 8 + 5 and round(iv["external_hours"] * 3600) == 6 + 5 + 10


def test_analytics_date_filter(admin, seeded):
    a = admin.get("/api/analytics", params={"date_from": seeded.now.date().replace(day=1).isoformat()}).json()
    assert sum(o["count"] for o in a["meetings_by_owner"]) <= 1
