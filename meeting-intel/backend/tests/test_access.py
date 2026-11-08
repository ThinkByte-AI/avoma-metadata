import pytest
from sqlalchemy import select

from app.auth.access import accessible_meeting_clause, ensure_meeting_access
from app.errors import ApiError
from app.models import Meeting
from tests.seed import M1, M2, M3, M4, M5, seed_search_data


@pytest.fixture
def seeded(db):
    return seed_search_data(db)


def _visible(db, user):
    return set(db.scalars(select(Meeting.id).where(accessible_meeting_clause(user))))


def test_admin_sees_all_but_duplicates(db, seeded, make_user):
    admin = make_user("admin@example.com", role="admin")
    assert _visible(db, admin) == {M1, M2, M3, M4}


def test_scope_all_user_sees_all(db, seeded, make_user):
    assert _visible(db, make_user("u@example.com", access_scope="all")) == {M1, M2, M3, M4}


def test_account_label_access(db, seeded, make_user):
    assert _visible(db, make_user("alice-user@example.com", account_label="Alice")) == {M1, M3}


def test_participant_email_access(db, seeded, make_user):
    assert _visible(db, make_user("Carol@Example.com")) == {M2}


def test_label_and_email_combine(db, seeded, make_user):
    assert _visible(db, make_user("carol@example.com", account_label="Zed")) == {M2, M4}


def test_no_access_user_sees_nothing(db, seeded, make_user):
    assert _visible(db, make_user("dave@example.com")) == set()


def test_ensure_meeting_access_404(db, seeded, make_user):
    dave = make_user("dave@example.com")
    with pytest.raises(ApiError) as e:
        ensure_meeting_access(db, dave, M1)
    assert e.value.status == 404 and e.value.code == "not_found"
    admin = make_user("admin@example.com", role="admin")
    assert ensure_meeting_access(db, admin, M1).id == M1
    with pytest.raises(ApiError):
        ensure_meeting_access(db, admin, M5)  # duplicates are hidden from everyone
