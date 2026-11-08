import pytest
from botocore.exceptions import ClientError
from sqlalchemy import func, select

from app.ai.assistant import FORCE_ANSWER, MAX_TOOL_ROUNDS, NO_EVIDENCE_ANSWER
from app.ai.chat import FakeChatModel, final, get_chat_model, tool_call
from app.ai.embeddings import FakeEmbedder, get_query_embedder
from app.models import SearchHistory
from tests.conftest import _client_for, login
from tests.seed import M1, seed_search_data


@pytest.fixture
def seeded(db):
    return seed_search_data(db)


@pytest.fixture
def ai(app, db, make_user, seeded):
    """Returns (client_for_email, set_script). The chat model replays the script."""
    app.dependency_overrides[get_query_embedder] = lambda: FakeEmbedder()
    holder: dict = {}

    def set_script(*items):
        holder["chat"] = FakeChatModel(list(items))
        app.dependency_overrides[get_chat_model] = lambda: holder["chat"]
        return holder["chat"]

    def as_user(email, **kw):
        make_user(email, **kw)
        c = _client_for(app, db)
        login(c, email)
        return c

    return as_user, set_script


def _ask(client, question="What happened with revenue?", **body):
    return client.post("/api/ai/ask", json={"question": question, **body})


def _tool_result_text(call) -> str:
    last = call["messages"][-1]
    return "\n".join(b["toolResult"]["content"][0]["text"] for b in last["content"] if "toolResult" in b)


def test_ask_returns_cited_sources_only(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    chat = set_script(tool_call("revenue grew"), final("Revenue grew five percent [1]."))
    r = _ask(admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["evidence_found"] is True and body["answer_markdown"] == "Revenue grew five percent [1]."
    assert len(body["citations"]) == 1
    c = body["citations"][0]
    assert c["n"] == 1 and c["meeting_id"] == str(M1) and c["subject"] == "Weekly Revenue Review"
    assert c["excerpt"] and c["start_at"].endswith("Z")
    assert body["model"] == chat.model_id
    assert "[1] Meeting: Weekly Revenue Review" in _tool_result_text(chat.calls[1])


def test_unknown_citation_number_stripped(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    set_script(tool_call("revenue grew"), final("Revenue grew [1][99]. Also [2, 77]."))
    body = _ask(admin).json()
    assert body["answer_markdown"] == "Revenue grew [1]. Also [2]."
    assert [c["n"] for c in body["citations"]] == [1, 2]


def test_no_evidence_skips_model_answer_and_says_so(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    set_script(tool_call("quantum chromodynamics"), final("Made-up answer about physics [1]."))
    body = _ask(admin, "What about quantum chromodynamics?").json()
    assert body == {**body, "evidence_found": False, "citations": [], "answer_markdown": NO_EVIDENCE_ANSWER}


def test_answer_without_searching_is_not_trusted(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    set_script(final("Revenue was huge."))
    body = _ask(admin).json()
    assert body["evidence_found"] is False and body["answer_markdown"] == NO_EVIDENCE_ANSWER


def test_tool_results_respect_access(ai):
    as_user, set_script = ai
    dave = as_user("dave@example.com")
    chat = set_script(tool_call("revenue grew"), final("Revenue grew [1]."))
    body = _ask(dave).json()
    assert body["evidence_found"] is False and body["citations"] == []
    assert _tool_result_text(chat.calls[1]) == "No matching passages found."


def test_speaker_name_resolved_to_filter(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    chat = set_script(tool_call("revenue", speaker="Bob"), final("Bob said revenue grew [1]."))
    body = _ask(admin, "What did Bob say about revenue?").json()
    text = _tool_result_text(chat.calls[1])
    assert "Speaker: Bob Client" in text and "Speaker: Alice Tester" not in text
    assert body["citations"][0]["speaker_name"] == "Bob Client"


def test_unknown_speaker_returns_no_passages(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    chat = set_script(tool_call("revenue", speaker="Zorro"), final("Nothing."))
    _ask(admin)
    assert "No participant matching 'Zorro'" in _tool_result_text(chat.calls[1])


def test_tool_round_limit_forces_final_answer(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    chat = set_script(*[tool_call(f"revenue {i}") for i in range(MAX_TOOL_ROUNDS)], final("Done [1]."))
    body = _ask(admin).json()
    assert len(chat.calls) == MAX_TOOL_ROUNDS + 1
    last_user = chat.calls[-1]["messages"][-1]
    assert any(b.get("text") == FORCE_ANSWER for b in last_user["content"])
    assert body["answer_markdown"] == "Done [1]." and body["evidence_found"] is True


def test_model_ignoring_limit_gets_fallback(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    set_script(*[tool_call("revenue") for _ in range(MAX_TOOL_ROUNDS + 1)])
    body = _ask(admin).json()
    assert body["evidence_found"] is False and "rephrase" in body["answer_markdown"]


def test_reasoning_blocks_ignored(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    msg = final("Answer [1].")
    msg["message"]["content"].insert(0, {"reasoningContent": {"reasoningText": {"text": "secret [7] thoughts"}}})
    set_script(tool_call("revenue grew"), msg)
    body = _ask(admin).json()
    assert body["answer_markdown"] == "Answer [1]." and "secret" not in str(body)


def test_history_is_sent_in_alternating_turns(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    chat = set_script(final("ok"))
    _ask(admin, "And pricing?", history=[
        {"role": "assistant", "content": "orphan assistant turn is dropped"},
        {"role": "user", "content": "What about revenue?"},
        {"role": "assistant", "content": "Revenue grew [1]."},
    ])
    roles = [m["role"] for m in chat.calls[0]["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert chat.calls[0]["messages"][-1]["content"][0]["text"] == "And pricing?"


def test_tool_searches_not_recorded_in_history(ai, db):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")
    set_script(tool_call("revenue grew"), final("x [1]"))
    _ask(admin)
    assert db.scalar(select(func.count()).select_from(SearchHistory)) == 0


def test_bedrock_error_returns_502(ai):
    as_user, set_script = ai
    admin = as_user("admin@example.com", role="admin")

    def boom(_messages):
        raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse")

    set_script(boom)
    r = _ask(admin)
    assert r.status_code == 502 and r.json()["error"]["code"] == "ai_unavailable"


def test_validation_and_auth(ai, client):
    as_user, set_script = ai
    assert _ask(client).status_code == 401
    admin = as_user("admin@example.com", role="admin")
    set_script()
    assert _ask(admin, "").status_code == 422
    assert _ask(admin, "x" * 2001).status_code == 422


def test_citation_ranges_are_expanded():
    from app.ai.assistant import clean_citations

    text, cited = clean_citations("Ads were discussed [1-3] and later [5–6, 9].", {1, 2, 3, 5, 6})
    assert text == "Ads were discussed [1][2][3] and later [5][6]."
    assert cited == [1, 2, 3, 5, 6]
