import json
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from moto import mock_aws

from app.aws.s3 import S3Store, get_store
from tests.conftest import login

REGION = "ap-south-1"


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket="test-bucket", CreateBucketConfiguration={"LocationConstraint": REGION})
        yield client


def test_iter_objects_paginates(s3_bucket):
    for i in range(1005):
        s3_bucket.put_object(Bucket="test-bucket", Key=f"avoma/x/{i:04d}.txt", Body=b"x")
    s3_bucket.put_object(Bucket="test-bucket", Key="elsewhere/skip.txt", Body=b"x")
    objs = list(S3Store("test-bucket", REGION).iter_objects(["avoma/"]))
    assert len(objs) == 1005
    assert objs[0].key == "avoma/x/0000.txt" and objs[0].size == 1 and objs[0].etag and '"' not in objs[0].etag
    assert objs[0].storage_class == "STANDARD"


def test_get_json_and_text(s3_bucket):
    s3_bucket.put_object(Bucket="test-bucket", Key="a.json", Body=json.dumps([{"x": 1}]).encode())
    s3_bucket.put_object(Bucket="test-bucket", Key="a.md", Body="# Título".encode())
    store = S3Store("test-bucket", REGION)
    assert store.get_json("a.json") == [{"x": 1}]
    assert store.get_text("a.md") == "# Título"


def test_presign_sets_response_content_type(s3_bucket):
    url = S3Store("test-bucket", REGION).presign_get("avoma/a/recording.mp3", "audio/mpeg", 900)
    q = parse_qs(urlparse(url).query)
    assert q["response-content-type"] == ["audio/mpeg"]
    assert "response-content-disposition" not in q
    assert q["X-Amz-Expires"] == ["900"]


def test_presign_download_sets_disposition(s3_bucket):
    url = S3Store("test-bucket", REGION).presign_get("k.mp3", "audio/mpeg", 60, download_name="Weekly sync-2025-02-11.mp3")
    q = parse_qs(urlparse(url).query)
    assert q["response-content-disposition"] == ['attachment; filename="Weekly sync-2025-02-11.mp3"']


def test_check_ok(s3_bucket):
    assert S3Store("test-bucket", REGION).check() == {"ok": True, "bucket": "test-bucket", "region": REGION, "error": None}


def test_check_reports_missing_bucket(s3_bucket):
    r = S3Store("missing-bucket", REGION).check()
    assert r["ok"] is False and r["bucket"] == "missing-bucket" and r["error"]


def test_system_status_admin_only(client, make_user):
    make_user("alice@example.com")
    login(client, "alice@example.com")
    assert client.get("/api/system/status").status_code == 403


def test_system_status_reports_config(admin_client, app, s3_bucket):
    app.dependency_overrides[get_store] = lambda: S3Store("test-bucket", REGION)
    r = admin_client.get("/api/system/status")
    assert r.status_code == 200
    body = r.json()
    assert body["aws"]["ok"] is True
    assert body["bucket"] == "test-bucket" and body["prefixes"] == ["avoma/"] and body["region"] == REGION
    assert body["embed_model"] == "amazon.titan-embed-text-v2:0" and body["chat_model"] == "zai.glm-5"
    assert body["app_mode"] == "production" and body["db"] == "ok"
