"""Tests for Email Action API."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_enrich_requires_auth(client):
    r = client.post("/emails/enrich", json={"emails": []})
    assert r.status_code in (400, 401)


def test_sync_requires_auth(client):
    r = client.post("/contacts/sync", json={"contacts": []})
    assert r.status_code in (400, 401)


def test_me_requires_auth(client):
    r = client.get("/auth/me")
    assert r.status_code == 401
