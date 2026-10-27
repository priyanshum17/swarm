"""FastAPI route endpoints for task orchestration, durable resumption, metrics, and evals."""

from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from swarm.api.schemas import (
    CreateTaskRequest,
    MetricsResponse,
    ResumeTaskRequest,
    RunEvalRequest,
    TaskResponse,
)
from swarm.cache.prompt_cache import get_prompt_cache
from swarm.checkpoint.models import TaskCheckpoint, TaskStatus
from swarm.checkpoint.redis_store import get_checkpoint_store
from swarm.config import settings
from swarm.evals.runner import EvalBenchmarkReport, EvalHarness
from swarm.runtime.agent import SwarmAgent

logger = logging.getLogger("swarm.api")
router = APIRouter()

# Active in-memory agent instance
_agent: Optional[SwarmAgent] = None


async def get_agent() -> SwarmAgent:
    global _agent
    if _agent is None:
        store = await get_checkpoint_store(settings.redis_url)
        _agent = SwarmAgent(checkpoint_store=store)
    return _agent


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(req: CreateTaskRequest, wait: bool = Query(True, description="Wait for completion")) -> TaskResponse:
    """Create and execute a multi-step agent task."""
    agent = await get_agent()

    if wait:
        state = await agent.run(goal=req.goal, metadata=req.metadata)
        cm = await agent._get_checkpoint_manager()
        checkpoint = await cm.store.load(state.task_id)
        if not checkpoint:
            raise HTTPException(status_code=500, detail="Failed to load persisted checkpoint")
        return TaskResponse(**checkpoint.model_dump())

    # Asynchronous background execution
    import uuid
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    cm = await agent._get_checkpoint_manager()
    checkpoint = await cm.initialize_task(task_id=task_id, goal=req.goal, steps=[], metadata=req.metadata)
    asyncio.create_task(agent.run(goal=req.goal, task_id=task_id, metadata=req.metadata))
    return TaskResponse(**checkpoint.model_dump())


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    """Retrieve full task checkpoint from Redis store."""
    agent = await get_agent()
    cm = await agent._get_checkpoint_manager()
    checkpoint = await cm.store.load(task_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found in checkpoint store")
    return TaskResponse(**checkpoint.model_dump())


@router.post("/tasks/{task_id}/resume", response_model=TaskResponse)
async def resume_task(task_id: str) -> TaskResponse:
    """Durable execution: Resume interrupted task from its latest checkpoint in Redis."""
    agent = await get_agent()
    cm = await agent._get_checkpoint_manager()
    checkpoint = await cm.store.load(task_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    resumed_state = await agent.resume_task(task_id)
    if not resumed_state:
        raise HTTPException(status_code=500, detail="Failed to resume task")

    final_checkpoint = await cm.store.load(task_id)
    return TaskResponse(**final_checkpoint.model_dump())


@router.post("/tasks/{task_id}/cancel", response_model=Dict[str, Any])
async def cancel_task(task_id: str) -> Dict[str, Any]:
    """Gracefully cancel a task run."""
    agent = await get_agent()
    cm = await agent._get_checkpoint_manager()
    checkpoint = await cm.store.load(task_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    checkpoint.status = TaskStatus.CANCELLED
    await cm.store.save(checkpoint)
    return {"task_id": task_id, "status": "cancelled"}


@router.get("/tasks/{task_id}/events")
async def task_events_sse(task_id: str) -> StreamingResponse:
    """Server-Sent Events (SSE) streaming real-time step status updates for an agent task."""
    agent = await get_agent()
    cm = await agent._get_checkpoint_manager()

    async def event_generator() -> AsyncGenerator[str, None]:
        last_version = -1
        while True:
            checkpoint = await cm.store.load(task_id)
            if not checkpoint:
                yield f"event: error\ndata: {json.dumps({'error': 'Task not found'})}\n\n"
                break

            if checkpoint.version > last_version:
                last_version = checkpoint.version
                data = {
                    "task_id": checkpoint.task_id,
                    "status": checkpoint.status.value,
                    "version": checkpoint.version,
                    "steps": [s.model_dump() for s in checkpoint.steps],
                }
                yield f"event: update\ndata: {json.dumps(data)}\n\n"

            if checkpoint.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                yield f"event: finish\ndata: {json.dumps({'status': checkpoint.status.value})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics() -> MetricsResponse:
    """Token telemetry and prompt caching analytics endpoint."""
    cache = get_prompt_cache()
    store = await get_checkpoint_store(settings.redis_url)
    redis_healthy = await store.ping()
    snap = cache.metrics.snapshot()

    return MetricsResponse(
        app_name=settings.app_name,
        version=settings.version,
        redis_connected=redis_healthy,
        total_requests=cache.metrics.total_requests,
        raw_prompt_tokens=snap.prompt_tokens,
        cached_prompt_tokens=snap.cached_prompt_tokens,
        completion_tokens=snap.completion_tokens,
        total_tokens=snap.total_tokens,
        token_savings_pct=snap.cache_savings_pct,
        cache_hit_rate_pct=cache.metrics.cache_hit_rate,
        estimated_cost_usd=snap.estimated_cost_usd,
    )


@router.post("/evals/run", response_model=EvalBenchmarkReport)
async def run_evals(req: Optional[RunEvalRequest] = None) -> EvalBenchmarkReport:
    """Trigger the 40-task benchmark evaluation harness and return performance report."""
    harness = EvalHarness()
    subset = req.task_subset if req else None
    concurrency = req.concurrency if req else 4
    report = await harness.run_benchmark(task_subset=subset, concurrency=concurrency)
    return report


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint validating Redis connectivity and runtime configuration."""
    store = await get_checkpoint_store(settings.redis_url)
    redis_alive = await store.ping()
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.version,
        "redis_connected": redis_alive,
        "environment": settings.environment,
    }
