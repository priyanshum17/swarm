"""Data models for durable checkpointing in Swarm."""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RECOVERED = "recovered"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepCheckpoint(BaseModel):
    """Snapshot of a single step in a plan."""
    step_id: str
    index: int
    description: str
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Any] = None
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None
    retries: int = 0
    recovery_strategy_used: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    execution_time_ms: Optional[float] = None


class TokenUsageSnapshot(BaseModel):
    """Aggregated token telemetry snapshot for this checkpoint."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_prompt_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    cache_savings_pct: float = 0.0


class TaskCheckpoint(BaseModel):
    """Full durable snapshot of an agent task state stored in Redis."""
    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.QUEUED
    current_step_index: int = 0
    steps: List[StepCheckpoint] = Field(default_factory=list)
    context_memory: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tokens: TokenUsageSnapshot = Field(default_factory=TokenUsageSnapshot)
    version: int = 1
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_summary: Optional[str] = None

    def completed_step_ids(self) -> List[str]:
        return [s.step_id for s in self.steps if s.status in (StepStatus.COMPLETED, StepStatus.RECOVERED)]

    def pending_steps(self) -> List[StepCheckpoint]:
        return [s for s in self.steps if s.status in (StepStatus.PENDING, StepStatus.RUNNING, StepStatus.FAILED)]
