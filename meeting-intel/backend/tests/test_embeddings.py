import io
import json
import math

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.ai.embeddings import BedrockEmbedder, FakeEmbedder, get_embedder
from app.ingestion.jobs import claim_next_job, enqueue_job, run_job
from app.ingestion.pipeline import embed_meeting, process_meeting, scan_bucket
from app.models import IngestionJob, Meeting, TranscriptSegment
from tests.test_pipeline import A, B, P, bucket, meta, store  # noqa: F401  (fixtures)

MODEL = "amazon.titan-embed-text-v2:0"


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


# --- FakeEmbedder ------------------------------------------------------------

def test_fake_embedder_deterministic_and_normalized():
    e = FakeEmbedder()
    v1, v2 = e.embed_query("Revenue grew"), e.embed_documents(["Revenue grew"])[0]
    assert v1 == v2 and len(v1) == 512 and e.dim == 512
    assert abs(math.sqrt(sum(x * x for x in v1)) - 1.0) < 1e-9


def test_fake_similar_texts_closer():
    e = FakeEmbedder()
    q = e.embed_query("revenue growth plan")
    assert _cos(q, e.embed_query("plan for revenue growth")) > _cos(q, e.embed_query("hello good evening"))


def test_fake_empty_text_is_not_zero_vector():
    assert any(FakeEmbedder().embed_query(""))


# --- BedrockEmbedder -----------------------------------------------------------

def _resp(vec):
    raw = json.dumps({"embedding": vec, "inputTextTokenCount": 3}).encode()
    return {"body": StreamingBody(io.BytesIO(raw), len(raw)), "contentType": "application/json"}


def _expected(text):
    return {
        "modelId": MODEL,
        "body": json.dumps({"inputText": text, "dimensions": 1024, "normalize": True}),
        "contentType": "application/json",
        "accept": "application/json",
    }


@pytest.fixture
def runtime():
    return boto3.client("bedrock-runtime", region_name="ap-south-1")


def test_bedrock_embedder_request_body(runtime):
    with Stubber(runtime) as stub:
        stub.add_response("invoke_model", _resp([0.5] * 1024), _expected("revenue growth"))
        e = BedrockEmbedder(MODEL, "ap-south-1", 1024, concurrency=1, client=runtime)
        assert e.embed_query("revenue growth") == [0.5] * 1024
        stub.assert_no_pending_responses()


def test_bedrock_embedder_keeps_order(runtime):
    with Stubber(runtime) as stub:
        for i in range(3):
            stub.add_response("invoke_model", _resp([float(i)] * 1024), _expected(f"t{i}"))
        e = BedrockEmbedder(MODEL, "ap-south-1", 1024, concurrency=1, client=runtime)
        assert [v[0] for v in e.embed_documents(["t0", "t1", "t2"])] == [0.0, 1.0, 2.0]


def test_bedrock_embedder_retries_throttle(runtime):
    with Stubber(runtime) as stub:
        stub.add_client_error("invoke_model", service_error_code="ThrottlingException", http_status_code=429)
        stub.add_client_error("invoke_model", service_error_code="ThrottlingException", http_status_code=429)
        stub.add_response("invoke_model", _resp([0.1] * 1024), _expected("x"))
        e = BedrockEmbedder(MODEL, "ap-south-1", 1024, concurrency=1, client=runtime, backoff_base=0)
        assert e.embed_query("x") == [0.1] * 1024


def test_bedrock_embedder_gives_up_on_other_errors(runtime):
    with Stubber(runtime) as stub:
        stub.add_client_error("invoke_model", service_error_code="AccessDeniedException", http_status_code=403)
        e = BedrockEmbedder(MODEL, "ap-south-1", 1024, concurrency=1, client=runtime, backoff_base=0)
        with pytest.raises(Exception, match="AccessDenied"):
            e.embed_query("x")


def test_get_embedder_by_mode(settings_override, monkeypatch):
    from app.config import get_settings

    assert isinstance(get_embedder(get_settings()), BedrockEmbedder)
    monkeypatch.setenv("APP_MODE", "dev-mock")
    get_settings.cache_clear()
    assert isinstance(get_embedder(get_settings()), FakeEmbedder)


# --- embed_meeting -------------------------------------------------------------

def test_embed_meeting_sets_indexed(db, store, meta):
    scan_bucket(db, store, P, meta)
    process_meeting(db, store, A, meta[A])
    assert embed_meeting(db, FakeEmbedder(), A) is True
    a = db.get(Meeting, A)
    assert a.ingest_status == "indexed" and a.indexed_at is not None
    rows = db.execute(select(TranscriptSegment.kind, TranscriptSegment.embedding.is_not(None))
                      .where(TranscriptSegment.meeting_id == A)).all()
    assert not any(e for k, e in rows if k == "utterance")  # single lines are keyword-only
    assert all(e for k, e in rows if k in ("chunk", "note")) and any(k == "chunk" for k, _ in rows)


def test_embed_text_includes_subject_and_speaker(db, store, meta):
    seen: list[str] = []

    class Spy(FakeEmbedder):
        def embed_documents(self, texts):
            seen.extend(texts)
            return super().embed_documents(texts)

    scan_bucket(db, store, P, meta)
    process_meeting(db, store, A, meta[A])
    embed_meeting(db, Spy(), A)
    assert any(t.startswith("Weekly Revenue Review | Alice Tester: Hi Bob, good evening.") and "Bob Client: Revenue grew" in t
               for t in seen)
    assert any(t.startswith("Weekly Revenue Review | Key Takeaways: ") for t in seen)


def test_only_chunks_and_notes_are_embedded(db, store, meta):
    scan_bucket(db, store, P, meta)
    process_meeting(db, store, B, meta[B])
    assert embed_meeting(db, FakeEmbedder(), B) is True
    assert db.get(Meeting, B).ingest_status == "indexed"
    kinds = db.scalars(select(TranscriptSegment.kind).where(TranscriptSegment.meeting_id == B,
                                                            TranscriptSegment.embedding.is_not(None))).all()
    assert kinds == ["chunk"]


def test_embed_meetings_batches_several(db, store, meta):
    from app.ingestion.pipeline import embed_meetings

    calls: list[int] = []

    class Counting(FakeEmbedder):
        def embed_documents(self, texts):
            calls.append(len(texts))
            return super().embed_documents(texts)

    scan_bucket(db, store, P, meta)
    for mid in (A, B):
        process_meeting(db, store, mid, meta[mid])
    assert embed_meetings(db, Counting(), [A, B]) == {A: True, B: True}
    assert calls == [6]  # A: 1 chunk + 4 notes, B: 1 chunk, in one batch
    assert {db.get(Meeting, A).ingest_status, db.get(Meeting, B).ingest_status} == {"indexed"}


def test_embed_meetings_isolates_a_bad_meeting(db, store, meta):
    from app.ingestion.pipeline import embed_meetings

    class FailsOnB(FakeEmbedder):
        def embed_documents(self, texts):
            if any("Who am I?" in t for t in texts):
                raise RuntimeError("bad input")
            return super().embed_documents(texts)

    scan_bucket(db, store, P, meta)
    for mid in (A, B):
        process_meeting(db, store, mid, meta[mid])
    assert embed_meetings(db, FailsOnB(), [A, B]) == {A: True, B: False}
    assert db.get(Meeting, B).ingest_status == "failed" and db.get(Meeting, A).ingest_status == "indexed"


def test_bedrock_embedder_retries_network_errors(runtime):
    from botocore.exceptions import ReadTimeoutError

    e = BedrockEmbedder(MODEL, "ap-south-1", 1024, concurrency=1, client=runtime, backoff_base=0)
    calls = {"n": 0}

    with Stubber(runtime) as stub:
        stub.add_response("invoke_model", _resp([0.2] * 1024), _expected("x"))
        real = e.client.invoke_model

        def flaky(**kw):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ReadTimeoutError(endpoint_url="https://bedrock")
            return real(**kw)

        e.client.invoke_model = flaky
        assert e.embed_query("x") == [0.2] * 1024 and calls["n"] == 3


def test_embed_failure_marks_failed(db, store, meta):
    class Broken(FakeEmbedder):
        def embed_documents(self, texts):
            raise RuntimeError("bedrock down")

    scan_bucket(db, store, P, meta)
    process_meeting(db, store, A, meta[A])
    assert embed_meeting(db, Broken(), A) is False
    a = db.get(Meeting, A)
    assert a.ingest_status == "failed" and "bedrock down" in a.ingest_error


def test_run_job_with_embedder_indexes(db, engine, store, meta):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    job = enqueue_job(db, "initial", None)
    with factory() as s:
        claim_next_job(s)
    run_job(factory, job.id, store, FakeEmbedder(), lambda: meta, poll_sec=0.05)
    db.expire_all()
    assert db.get(IngestionJob, job.id).stats["meetings_indexed"] == 3
    assert db.get(Meeting, A).ingest_status == "indexed"
