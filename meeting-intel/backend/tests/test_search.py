from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.ai.embeddings import FakeEmbedder, get_query_embedder
from app.models import SearchHistory
from tests.conftest import _client_for, login
from tests.seed import M1, M2, M3, M4, M5, seed_search_data


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


def _search(client, **body):
    r = client.post("/api/search", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _ids(resp):
    return [r["meeting"]["id"] for r in resp["results"]]


def test_admin_sees_all(admin):
    resp = _search(admin)
    assert resp["total"] == 4 and set(_ids(resp)) == {str(M1), str(M2), str(M3), str(M4)}


def test_account_label_access(as_user):
    assert set(_ids(_search(as_user("alice-user@example.com", account_label="Alice")))) == {str(M1), str(M3)}


def test_participant_email_access(as_user):
    assert _ids(_search(as_user("carol@example.com"))) == [str(M2)]


def test_no_access_user_gets_zero_results(as_user):
    resp = _search(as_user("dave@example.com"), q="revenue")
    assert resp["total"] == 0 and resp["results"] == []


def test_keyword_search_finds_and_highlights(admin):
    resp = _search(admin, q="revenue", mode="keyword")
    ids = _ids(resp)
    assert ids[0] == str(M1) and str(M4) in ids and str(M5) not in ids
    hit = resp["results"][0]
    assert "keyword" in hit["match_types"]
    m = next(x for x in hit["matches"] if x["text"].startswith("Revenue grew"))
    assert m["match_type"] == "keyword" and m["speaker_name"] == "Bob Client" and m["start_sec"] == 14
    s, e = m["highlights"][0]
    assert m["text"][s:e] == "Revenue"
    assert resp["semantic_used"] is False


def test_highlight_covers_every_occurrence(admin):
    resp = _search(admin, q="marketing strategy", mode="keyword")
    hit = next(r for r in resp["results"] if r["meeting"]["id"] == str(M4))
    m = next(x for x in hit["matches"] if x["text"].startswith("Our marketing"))
    assert [m["text"][s:e].lower() for s, e in m["highlights"]] == ["marketing", "strategy"]


def test_semantic_search_ranks_by_vector(admin):
    resp = _search(admin, q="increasing budget cloud", mode="semantic")
    assert resp["semantic_used"] is True
    top = resp["results"][0]
    assert top["meeting"]["id"] == str(M3) and top["matches"][0]["match_type"] == "semantic"
    m = top["matches"][0]
    assert m["highlights"] == [[0, len(m["text"])]]


def test_auto_mode_uses_semantic_for_phrases_only(admin):
    assert _search(admin, q="revenue")["semantic_used"] is False
    assert _search(admin, q="revenue growth pricing")["semantic_used"] is True


def test_semantic_falls_back_when_embedder_fails(admin, app):
    class Broken(FakeEmbedder):
        def embed_query(self, text):
            raise RuntimeError("bedrock down")

    app.dependency_overrides[get_query_embedder] = lambda: Broken()
    resp = _search(admin, q="revenue growth pricing")
    assert resp["semantic_used"] is False and str(M1) in _ids(resp)


def test_meeting_uuid_query_returns_that_meeting(admin):
    resp = _search(admin, q=str(M2))
    assert _ids(resp)[0] == str(M2) and "metadata" in resp["results"][0]["match_types"]


def test_title_search(admin):
    assert _ids(_search(admin, q="onboarding discussion"))[0] == str(M2)


def test_person_partial_name_and_email(admin):
    assert _ids(_search(admin, q="erin"))[0] == str(M3)
    assert _ids(_search(admin, q="prospect.example"))[0] == str(M2)


def test_filters_combined_participant_and_date_and_keyword(admin, seeded):
    since = (seeded.now - timedelta(days=10)).date().isoformat()
    resp = _search(admin, q="revenue", filters={"participant_ids": [seeded.people["bob"]], "date_from": since})
    assert _ids(resp) == [str(M1)]


def test_participant_filter_requires_all_selected(admin, seeded):
    p = seeded.people
    assert _ids(_search(admin, filters={"participant_ids": [p["alice"], p["erin"]]})) == [str(M3)]


def test_speaker_filter_limits_matches(admin, seeded):
    resp = _search(admin, q="revenue", mode="keyword", filters={"speaker_ids": [seeded.people["bob"]]})
    assert set(_ids(resp)) == {str(M1), str(M4)}
    assert all(m["speaker_name"] == "Bob Client" for r in resp["results"] for m in r["matches"])


@pytest.mark.parametrize("preset,expected", [
    ("7d", {M1}), ("30d", {M1}), ("6m", {M1, M2}), ("1y", {M1, M2, M3}), ("all", {M1, M2, M3, M4}),
])
def test_date_presets(admin, preset, expected):
    assert set(_ids(_search(admin, filters={"date_preset": preset}))) == {str(x) for x in expected}


def test_explicit_dates_override_preset_and_date_to_inclusive(admin, seeded):
    day = (seeded.now - timedelta(days=40)).date().isoformat()
    resp = _search(admin, filters={"date_preset": "7d", "date_from": day, "date_to": day})
    assert _ids(resp) == [str(M2)]


def test_other_filters(admin):
    assert _ids(_search(admin, filters={"has_recording": False})) == [str(M2)]
    assert _ids(_search(admin, filters={"min_duration_min": 50})) == [str(M3)]
    assert set(_ids(_search(admin, filters={"max_duration_min": 42}))) == {str(M1), str(M2)}
    assert set(_ids(_search(admin, filters={"owner": "alice"}))) == {str(M1), str(M3)}
    assert _ids(_search(admin, filters={"title": "strategy"})) == [str(M4)]


def test_empty_q_lists_by_date(admin):
    resp = _search(admin)
    assert _ids(resp) == [str(M1), str(M2), str(M3), str(M4)]
    assert all(r["matches"] == [] for r in resp["results"])
    assert _ids(_search(admin, sort="date_asc")) == [str(M4), str(M3), str(M2), str(M1)]
    assert _ids(_search(admin, sort="duration_desc"))[0] == str(M3)


def test_result_card_fields(admin, seeded):
    r = next(x for x in _search(admin, q="revenue")["results"] if x["meeting"]["id"] == str(M1))
    m = r["meeting"]
    assert (m["subject"], m["duration_sec"], m["owner_key"], m["has_recording"], m["has_transcript"]) == (
        "Weekly Revenue Review", 2490, "Alice", True, True)
    assert m["participant_count"] == 2
    assert [p["name"] for p in m["participants"]] == ["Bob Client", "Alice Tester"]  # external first
    assert m["start_at"].endswith("Z")


@pytest.mark.parametrize("q", ['"unclosed', "a & | ! ( ) :*", "🙂", "x" * 2000, "100%_off", "  "])
def test_special_characters_no_500(admin, q):
    r = admin.post("/api/search", json={"q": q})
    assert r.status_code == 200


def test_too_long_query_422(admin):
    assert admin.post("/api/search", json={"q": "x" * 2001}).status_code == 422


def test_pagination_totals(admin):
    resp = _search(admin, page=2, page_size=2)
    assert resp["total"] == 4 and resp["page"] == 2 and _ids(resp) == [str(M3), str(M4)]
    assert admin.post("/api/search", json={"page_size": 51}).status_code == 422


def test_history_written_once_and_own_only(as_user, db, admin):
    _search(admin, q="revenue")
    _search(admin, q="revenue", page=2)
    _search(admin)  # empty query, no filters → not recorded
    other = as_user("alice-user@example.com", account_label="Alice")
    _search(other, q="aws")
    assert db.scalar(select(func.count()).select_from(SearchHistory)) == 2
    hist = admin.get("/api/search/history").json()
    assert [h["query"] for h in hist] == ["revenue"] and hist[0]["result_count"] >= 2


def test_suggest_respects_access(as_user, admin):
    alice = as_user("alice-user@example.com", account_label="Alice")
    s = alice.get("/api/search/suggest", params={"q": "ali"}).json()
    assert [p["name"] for p in s["participants"]] == ["Alice Tester"]
    assert alice.get("/api/search/suggest", params={"q": "carol"}).json()["participants"] == []
    assert [m["subject"] for m in alice.get("/api/search/suggest", params={"q": "onboarding"}).json()["meetings"]] == []
    assert [m["subject"] for m in admin.get("/api/search/suggest", params={"q": "onboarding"}).json()["meetings"]] == [
        "Client Onboarding Discussion"]
    _search(alice, q="aws infrastructure")
    assert alice.get("/api/search/suggest", params={"q": "aws"}).json()["recent"] == ["aws infrastructure"]


def test_search_requires_login(client):
    assert client.post("/api/search", json={}).status_code == 401


def test_long_auto_query_matches_any_term_but_keyword_mode_is_strict(admin, app):
    app.dependency_overrides[get_query_embedder] = lambda: None  # keyword path only
    assert _search(admin, q="revenue growth pricing", mode="keyword")["total"] == 0
    resp = _search(admin, q="revenue growth pricing", mode="auto")
    assert _ids(resp)[0] == str(M1)
    m = next(x for x in resp["results"][0]["matches"] if x["text"].startswith("Revenue grew"))
    assert sorted(m["text"][s:e].lower() for s, e in m["highlights"]) == ["pricing", "revenue"]
