from app.ai.chat import FakeChatModel, final, get_chat_model
from app.ai.embeddings import FakeEmbedder, get_query_embedder
from app.ratelimit import AI_LIMIT_PER_MIN, ai_limiter
from tests.conftest import _client_for, login


def test_ai_rate_limit_429(app, db, make_user):
    ai_limiter.reset()
    app.dependency_overrides[get_query_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[get_chat_model] = lambda: FakeChatModel([final("ok")] * (AI_LIMIT_PER_MIN + 5))
    make_user("a@example.com")
    make_user("b@example.com")
    a, b = _client_for(app, db), _client_for(app, db)
    login(a, "a@example.com")
    for _ in range(AI_LIMIT_PER_MIN):
        assert a.post("/api/ai/ask", json={"question": "hi"}).status_code == 200
    r = a.post("/api/ai/ask", json={"question": "hi"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    login(b, "b@example.com")  # limits are per user
    assert b.post("/api/ai/ask", json={"question": "hi"}).status_code == 200
    ai_limiter.reset()
