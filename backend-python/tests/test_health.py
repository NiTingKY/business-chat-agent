from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_exposes_active_agent_id() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["agent_id"] == "travel-agent"
