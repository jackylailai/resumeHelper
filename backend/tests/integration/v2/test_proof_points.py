from __future__ import annotations

from fastapi.testclient import TestClient


def test_proof_point_crud_filter_and_delete(client: TestClient):
    profile = client.post(
        "/api/profiles",
        json={"skills_text": "Python FastAPI PostgreSQL", "name": "Backend"},
    ).json()["data"]

    create_response = client.post(
        "/api/proof-points",
        json={
            "profile_id": profile["id"],
            "title": "Reduced API latency",
            "context": "Checkout API performance project",
            "metrics": "Reduced p95 latency from 900ms to 220ms",
            "skills": ["Python", "FastAPI", "Python"],
            "tags": ["performance", "backend", "Performance"],
            "situation": "Checkout traffic was growing.",
            "task": "Improve p95 latency before peak campaign traffic.",
            "action": "Profiled slow queries and added Redis caching.",
            "result": "Cut p95 latency by 75%.",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()["data"]
    assert created["profile_id"] == profile["id"]
    assert created["title"] == "Reduced API latency"
    assert created["skills"] == ["Python", "FastAPI"]
    assert created["tags"] == ["performance", "backend"]
    assert created["result"] == "Cut p95 latency by 75%."

    detail_response = client.get(f"/api/proof-points/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["metrics"] == (
        "Reduced p95 latency from 900ms to 220ms"
    )

    list_response = client.get(
        f"/api/proof-points?profile_id={profile['id']}&q=latency&tag=performance"
    )
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["meta"]["total"] == 1
    assert list_body["data"][0]["id"] == created["id"]

    update_response = client.patch(
        f"/api/proof-points/{created['id']}",
        json={
            "profile_id": None,
            "title": "Reduced checkout latency",
            "skills": ["Redis", "PostgreSQL"],
            "tags": None,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["profile_id"] is None
    assert updated["title"] == "Reduced checkout latency"
    assert updated["skills"] == ["Redis", "PostgreSQL"]
    assert updated["tags"] == []

    filtered_response = client.get("/api/proof-points?skill=Redis")
    assert filtered_response.status_code == 200
    assert filtered_response.json()["meta"]["total"] == 1

    delete_response = client.delete(f"/api/proof-points/{created['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["deleted"] is True
    assert client.get(f"/api/proof-points/{created['id']}").status_code == 404


def test_proof_point_rejects_missing_profile(client: TestClient):
    response = client.post(
        "/api/proof-points",
        json={
            "profile_id": 9999,
            "title": "Missing profile proof",
            "skills": ["Python"],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_proof_point_validates_title_and_unknown_fields(client: TestClient):
    blank = client.post("/api/proof-points", json={"title": "   "})
    assert blank.status_code == 422

    non_string_skill = client.post(
        "/api/proof-points",
        json={"title": "Valid", "skills": [123]},
    )
    assert non_string_skill.status_code == 422

    extra = client.post(
        "/api/proof-points",
        json={"title": "Valid", "unexpected": "field"},
    )
    assert extra.status_code == 422

    created = client.post("/api/proof-points", json={"title": "Valid"}).json()["data"]
    null_title = client.patch(
        f"/api/proof-points/{created['id']}",
        json={"title": None},
    )
    assert null_title.status_code == 422
