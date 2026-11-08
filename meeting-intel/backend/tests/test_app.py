def test_health_reports_db_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": "ok"}


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_validation_error_uses_envelope(client_with_test_routes):
    r = client_with_test_routes.get("/api/_typed", params={"n": "abc"})  # route takes n: int
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_api_error_handler(client_with_test_routes):
    r = client_with_test_routes.get("/api/_boom")  # route raises ApiError(418, "teapot", "boom")
    assert r.status_code == 418 and r.json() == {"error": {"code": "teapot", "message": "boom", "details": None}}


def test_unhandled_exception_hides_details(client_with_test_routes):
    r = client_with_test_routes.get("/api/_crash")  # route raises RuntimeError("secret")
    assert r.status_code == 500 and "secret" not in r.text
    assert r.json()["error"]["code"] == "internal_error"


def test_settings_prefix_list(settings_override, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("S3_PREFIXES", "avoma/, other/ ,")
    get_settings.cache_clear()
    assert get_settings().s3_prefix_list == ["avoma/", "other/"]
