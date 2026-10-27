"""Runtime state structures for Swarm agent execution."""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from swarm.checkpoint.models import StepStatus, TaskStatus, TokenUsageSnapshot


class Step(BaseModel):
    """Runtime unit of execution."""
    id: str = Field(default_factory=lambda: f"step_{uuid.uuid4().hex[:8]}")
    description: str
    tool_name: Optional[str] = None
    tool_input: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    output: Optional[Any] = None
    error: Optional[str] = None
    retries: int = 0
    duration_ms: float = 0.0

    def is_ready(self, completed_step_ids: set[str]) -> bool:
        """A step is ready if all its dependencies have completed."""
        return set(self.dependencies).issubset(completed_step_ids)


class Plan(BaseModel):
    """Decomposed execution plan for a goal."""
    goal: str
    steps: List[Step] = Field(default_factory=list)

    def get_step(self, step_id: str) -> Optional[Step]:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    def completed_step_ids(self) -> set[str]:
        return {
            s.id for s in self.steps
            if s.status in (StepStatus.COMPLETED, StepStatus.RECOVERED, StepStatus.SKIPPED)
        }

    def ready_steps(self) -> List[Step]:
        completed = self.completed_step_ids()
        return [
            s for s in self.steps
            if s.status == StepStatus.PENDING and s.is_ready(completed)
        ]

    def is_finished(self) -> bool:
        return all(
            s.status in (StepStatus.COMPLETED, StepStatus.RECOVERED, StepStatus.SKIPPED)
            for s in self.steps
        )


class AgentState(BaseModel):
    """Active runtime state of an agent execution."""
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    goal: str
    plan: Optional[Plan] = None
    memory: Dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.QUEUED
    current_step_index: int = 0
    tokens: TokenUsageSnapshot = Field(default_factory=TokenUsageSnapshot)
    error_summary: Optional[str] = None
    recovered_failures_count: int = 0
