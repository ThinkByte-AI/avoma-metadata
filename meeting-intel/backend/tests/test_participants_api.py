import pytest

from tests.conftest import _client_for, login
from tests.seed import M2, seed_search_data


@pytest.fixture
def seeded(db):
    return seed_search_data(db)


@pytest.fixture
def as_user(app, db, make_user, seeded):
    def _as(email, **kw):
        make_user(email, **kw)
        c = _client_for(app, db)
        login(c, email)
        return c

    return _as


@pytest.fixture
def admin(as_user):
    return as_user("admin@example.com", role="admin")


def _rows(page):
    return {p["name"]: p for p in page["items"]}


def test_participants_counts_scoped_to_access(admin, as_user):
    rows = _rows(admin.get("/api/participants").json())
    assert {n: r["meeting_count"] for n, r in rows.items()} == {
        "Alice Tester": 2, "Bob Client": 2, "Carol Ops": 1, "Dan Prospect": 1, "Erin Engineer": 1}
    assert rows["Bob Client"]["speaking_sec"] == 16.0 and rows["Alice Tester"]["speaking_sec"] == 10.0
    assert rows["Bob Client"]["first_meeting_at"] < rows["Bob Client"]["last_meeting_at"]

    alice = as_user("alice-user@example.com", account_label="Alice")
    rows = _rows(alice.get("/api/participants").json())
    assert {n: r["meeting_count"] for n, r in rows.items()} == {"Alice Tester": 2, "Bob Client": 1, "Erin Engineer": 1}


def test_participants_sort_and_filters(admin):
    page = admin.get("/api/participants", params={"sort": "name"}).json()
    assert [p["name"] for p in page["items"]] == ["Alice Tester", "Bob Client", "Carol Ops", "Dan Prospect", "Erin Engineer"]
    assert [p["name"] for p in admin.get("/api/participants", params={"q": "pros"}).json()["items"]] == ["Dan Prospect"]
    ext = admin.get("/api/participants", params={"internal": "false", "sort": "name"}).json()
    assert [p["name"] for p in ext["items"]] == ["Bob Client", "Dan Prospect"]
    assert admin.get("/api/participants", params={"page_size": 2}).json()["total"] == 5


def test_participant_detail_mentions(admin, seeded):
    d = admin.get(f"/api/participants/{seeded.people['dan']}").json()
    assert d["name"] == "Dan Prospect" and d["meeting_count"] == 1
    assert [m["id"] for m in d["meetings"]["items"]] == [str(M2)]
    assert [(x["meeting_id"], x["speaker_name"]) for x in d["mentions"]] == [(str(M2), "Carol Ops")]
    assert d["mentions"][0]["text"].startswith("Welcome aboard Dan")


def test_participant_with_no_accessible_meetings_404(as_user, seeded):
    alice = as_user("alice-user@example.com", account_label="Alice")
    r = alice.get(f"/api/participants/{seeded.people['carol']}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert alice.get("/api/participants/99999").status_code == 404
