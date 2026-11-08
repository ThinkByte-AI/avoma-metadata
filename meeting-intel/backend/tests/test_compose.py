"""Guards for docker-compose.yml: services restart, and the worker waits for migrations (via a healthy backend)."""
import re
from pathlib import Path

COMPOSE = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")


def _service(name: str) -> str:
    m = re.search(rf"^  {name}:\n(.*?)(?=^  \w[\w-]*:\n|^\S|\Z)", COMPOSE, re.M | re.S)
    assert m, f"service {name} missing"
    block = m.group(1)
    if "<<: *backend-common" in block:  # include the shared anchor's settings
        anchor = re.search(r"^x-backend-common: &backend-common\n(.*?)(?=^\S)", COMPOSE, re.M | re.S)
        block += anchor.group(1)
    return block


def test_long_running_services_restart():
    for svc in ("db", "backend", "worker", "frontend"):
        assert "restart: unless-stopped" in _service(svc), svc


def test_backend_has_healthcheck_on_api_health():
    block = _service("backend")
    assert "healthcheck:" in block and "/api/health" in block


def test_worker_and_frontend_wait_for_healthy_backend():
    for svc in ("worker", "frontend"):
        block = _service(svc)
        assert re.search(r"backend:\s*\n\s*condition: service_healthy", block), svc

