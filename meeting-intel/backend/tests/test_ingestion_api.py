from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.ingestion.jobs import claim_next_job, run_job
from app.models import AuditLog
from tests.conftest import login
from tests.test_pipeline import bucket, meta, store  # noqa: F401  (fixtures)


def test_standard_user_cannot_start_403(client, make_user):
    make_user("alice@example.com")
    login(client, "alice@example.com")
    for path in ("start", "sync", "retry", "pause", "resume"):
        assert client.post(f"/api/ingestion/{path}").status_code == 403
    assert client.get("/api/ingestion/status").status_code == 403


def test_second_start_returns_409(admin_client):
    r = admin_client.post("/api/ingestion/start")
    assert r.status_code == 200 and r.json()["kind"] == "initial" and r.json()["status"] == "queued"
    r2 = admin_client.post("/api/ingestion/sync")
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "job_active"


def test_pause_resume_flow_and_audit(admin_client, db):
    admin_client.post("/api/ingestion/start")
    assert admin_client.post("/api/ingestion/pause").json()["status"] == "paused"
    assert admin_client.post("/api/ingestion/resume").json()["status"] == "queued"  # never started → back to queue
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions[-3:] == ["ingestion.start", "ingestion.pause", "ingestion.resume"]


def test_pause_without_active_job_404(admin_client):
    r = admin_client.post("/api/ingestion/pause")
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_active_job"


def test_status_totals_match_db(admin_client, engine, store, meta):  # noqa: F811
    job_id = admin_client.post("/api/ingestion/start").json()["id"]
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        claim_next_job(s)
    run_job(factory, job_id, store, None, lambda: meta, poll_sec=0.05)

    body = admin_client.get("/api/ingestion/status").json()
    assert body["current_job"] is None
    assert body["last_completed_job"]["id"] == job_id and body["last_completed_job"]["stats"]["processed"] == 3
    t = body["totals"]
    assert (t["meetings"], t["parsed"], t["skipped"], t["failed"], t["indexed"], t["discovered"]) == (4, 3, 1, 0, 0, 0)
    assert t["segments"] == 8 + 6 + 1 and t["embedded_segments"] == 0
    assert body["failed_meetings"] == [] and body["last_sync_at"] is not None
    assert body["bucket"] == "test-bucket" and body["prefixes"] == ["avoma/"]
