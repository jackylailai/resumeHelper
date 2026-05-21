from __future__ import annotations

from fastapi.testclient import TestClient


def test_tailoring_uses_relevant_proof_points(client: TestClient):
    profile = client.post(
        "/api/profiles",
        json={
            "name": "Backend",
            "skills_text": "Python FastAPI Redis PostgreSQL",
        },
    ).json()["data"]

    relevant = client.post(
        "/api/proof-points",
        json={
            "profile_id": profile["id"],
            "title": "Reduced checkout latency",
            "context": "Checkout API performance project",
            "metrics": "Reduced p95 latency from 900ms to 220ms",
            "skills": ["FastAPI", "Redis"],
            "tags": ["performance"],
            "action": "Added Redis caching and optimized FastAPI handlers.",
            "result": "Cut p95 latency by 75%.",
        },
    ).json()["data"]
    irrelevant = client.post(
        "/api/proof-points",
        json={
            "profile_id": profile["id"],
            "title": "Updated landing page visuals",
            "context": "Marketing page refresh",
            "skills": ["Figma"],
            "tags": ["design"],
        },
    ).json()["data"]

    evaluate_response = client.post(
        "/api/evaluate",
        json={
            "profile_id": profile["id"],
            "jd_text": (
                "Backend role needing FastAPI and Redis performance work. "
                "[[score=72]]"
            ),
        },
    )

    assert evaluate_response.status_code == 200
    job_id = evaluate_response.json()["data"]["job_analysis_id"]
    detail_response = client.get(f"/api/history/{job_id}")

    assert detail_response.status_code == 200
    resumes = detail_response.json()["data"]["generated_resumes"]
    assert len(resumes) == 1
    generated_resume = resumes[0]
    assert generated_resume["proof_point_ids"] == [relevant["id"]]
    assert relevant["id"] in generated_resume["resume_text"]
    assert "Reduced p95 latency from 900ms to 220ms" in generated_resume["resume_text"]
    assert irrelevant["id"] not in generated_resume["resume_text"]
