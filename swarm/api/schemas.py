"""Pydantic request and response schemas for FastAPI endpoints."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from swarm.checkpoint.models import StepCheckpoint, TaskStatus, TokenUsageSnapshot


class CreateTaskRequest(BaseModel):
    goal: str = Field(..., description="The objective or instruction for the agent")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional caller metadata")


class TaskResponse(BaseModel):
    task_id: str
    goal: str
    status: TaskStatus
    steps: List[StepCheckpoint] = Field(default_factory=list)
    tokens: TokenUsageSnapshot = Field(default_factory=TokenUsageSnapshot)
    context_memory: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    error_summary: Optional[str] = None


class ResumeTaskRequest(BaseModel):
    task_id: str = Field(..., description="ID of the task to resume from Redis checkpoint")


class MetricsResponse(BaseModel):
    app_name: str
    version: str
    redis_connected: bool
    total_requests: int
    raw_prompt_tokens: int
    cached_prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    token_savings_pct: float
    cache_hit_rate_pct: float
    estimated_cost_usd: float


class RunEvalRequest(BaseModel):
    task_subset: Optional[List[str]] = Field(default=None, description="Optional task IDs or categories to run")
    concurrency: int = Field(default=4, ge=1, le=16)
