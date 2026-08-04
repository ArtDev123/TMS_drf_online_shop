import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_health_ok(api: APIClient):
    r = api.get("/api/health/")
    assert r.status_code == 200
    assert r.data["status"] == "ok"


@pytest.mark.django_db
def test_echo_ok(api):
    r = api.post("/api/echo/", {"message": "hello"}, format="json")
    assert r.status_code == 200
    assert r.data["echo"] == "hello"


@pytest.mark.django_db
def test_echo_requires_message(api):
    r = api.post("/api/echo/", {}, format="json")
    assert r.status_code == 400
    assert "message" in r.data
