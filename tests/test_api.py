"""Tests for FastAPI endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from swarm.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data


@pytest.mark.asyncio
async def test_create_and_get_task():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create task
        resp = await ac.post("/tasks", json={"goal": "Evaluate 12 * 12 and save answer"}, params={"wait": True})
        assert resp.status_code == 201
        task_data = resp.json()
        assert "task_id" in task_data
        assert task_data["status"] == "completed"

        task_id = task_data["task_id"]

        # Retrieve task
        get_resp = await ac.get(f"/tasks/{task_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["task_id"] == task_id


@pytest.mark.asyncio
async def test_metrics_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "raw_prompt_tokens" in data
        assert "token_savings_pct" in data
