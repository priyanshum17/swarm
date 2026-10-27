"""Checkpoint Manager for durable agent execution and recovery."""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from swarm.checkpoint.models import (
    StepCheckpoint,
    StepStatus,
    TaskCheckpoint,
    TaskStatus,
    TokenUsageSnapshot,
)
from swarm.checkpoint.redis_store import CheckpointStoreInterface

logger = logging.getLogger("swarm.checkpoint.manager")


class CheckpointManager:
    """Coordinates persistence, state updates, and durable resumption for agent tasks."""

    def __init__(self, store: CheckpointStoreInterface) -> None:
        self.store = store

    async def initialize_task(
        self,
        task_id: str,
        goal: str,
        steps: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskCheckpoint:
        """Create and persist the initial checkpoint for a task."""
        step_checkpoints = [
            StepCheckpoint(
                step_id=s.get("id", f"step_{i+1}"),
                index=i,
                description=s["description"],
                tool_name=s.get("tool_name"),
                tool_input=s.get("tool_input"),
                dependencies=s.get("dependencies", []),
                status=StepStatus.PENDING,
            )
            for i, s in enumerate(steps)
        ]

        checkpoint = TaskCheckpoint(
            task_id=task_id,
            goal=goal,
            status=TaskStatus.RUNNING,
            current_step_index=0,
            steps=step_checkpoints,
            metadata=metadata or {},
        )
        await self.store.save(checkpoint)
        logger.debug(f"Task {task_id} initialized with {len(steps)} steps.")
        return checkpoint

    async def record_step_start(self, task_id: str, step_id: str) -> Optional[TaskCheckpoint]:
        """Mark a step as RUNNING with timestamp."""
        checkpoint = await self.store.load(task_id)
        if not checkpoint:
            return None

        for step in checkpoint.steps:
            if step.step_id == step_id:
                step.status = StepStatus.RUNNING
                step.started_at = datetime.now(timezone.utc).isoformat()
                break

        checkpoint.status = TaskStatus.RUNNING
        checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        checkpoint.version += 1
        await self.store.save(checkpoint)
        return checkpoint

    async def record_step_completion(
        self,
        task_id: str,
        step_id: str,
        output: Any,
        duration_ms: float,
        tokens_used: Optional[TokenUsageSnapshot] = None,
        memory_updates: Optional[Dict[str, Any]] = None,
    ) -> Optional[TaskCheckpoint]:
        """Atomically commit a completed step and update agent memory."""
        checkpoint = await self.store.load(task_id)
        if not checkpoint:
            return None

        for step in checkpoint.steps:
            if step.step_id == step_id:
                step.status = StepStatus.COMPLETED
                step.tool_output = output
                step.completed_at = datetime.now(timezone.utc).isoformat()
                step.execution_time_ms = duration_ms
                step.error = None
                break

        if memory_updates:
            checkpoint.context_memory.update(memory_updates)

        if tokens_used:
            checkpoint.tokens = tokens_used

        # Check if all steps are completed
        all_done = all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.RECOVERED) for s in checkpoint.steps)
        if all_done:
            checkpoint.status = TaskStatus.COMPLETED

        checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        checkpoint.version += 1
        await self.store.save(checkpoint)
        return checkpoint

    async def record_step_failure(
        self,
        task_id: str,
        step_id: str,
        error: str,
        retries: int,
        recovery_strategy: Optional[str] = None,
        recovered: bool = False,
        output: Optional[Any] = None,
    ) -> Optional[TaskCheckpoint]:
        """Record step error, retry count, and recovery outcome."""
        checkpoint = await self.store.load(task_id)
        if not checkpoint:
            return None

        for step in checkpoint.steps:
            if step.step_id == step_id:
                step.retries = retries
                step.recovery_strategy_used = recovery_strategy
                step.error = error
                if recovered:
                    step.status = StepStatus.RECOVERED
                    step.tool_output = output
                    step.completed_at = datetime.now(timezone.utc).isoformat()
                else:
                    step.status = StepStatus.FAILED
                break

        if not recovered:
            checkpoint.status = TaskStatus.FAILED
            checkpoint.error_summary = f"Step {step_id} failed: {error}"

        checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        checkpoint.version += 1
        await self.store.save(checkpoint)
        return checkpoint

    async def update_plan_dynamically(
        self,
        task_id: str,
        new_remaining_steps: List[Dict[str, Any]],
        reason: str,
    ) -> Optional[TaskCheckpoint]:
        """Dynamically update plan during runtime recovery without restarting completed steps."""
        checkpoint = await self.store.load(task_id)
        if not checkpoint:
            return None

        # Keep completed/recovered steps
        retained_steps = [
            s for s in checkpoint.steps
            if s.status in (StepStatus.COMPLETED, StepStatus.RECOVERED)
        ]

        # Append new steps
        base_index = len(retained_steps)
        new_step_checkpoints = [
            StepCheckpoint(
                step_id=s.get("id", f"step_replanned_{base_index + i + 1}"),
                index=base_index + i,
                description=s["description"],
                tool_name=s.get("tool_name"),
                tool_input=s.get("tool_input"),
                dependencies=s.get("dependencies", []),
                status=StepStatus.PENDING,
            )
            for i, s in enumerate(new_remaining_steps)
        ]

        checkpoint.steps = retained_steps + new_step_checkpoints
        checkpoint.metadata["last_replan_reason"] = reason
        checkpoint.metadata["replanned_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint.status = TaskStatus.RUNNING
        checkpoint.version += 1
        checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        await self.store.save(checkpoint)
        logger.info(f"Task {task_id} replanned dynamically. Retained {len(retained_steps)} steps, added {len(new_step_checkpoints)} steps.")
        return checkpoint

    async def get_resumption_state(self, task_id: str) -> Optional[Tuple[TaskCheckpoint, List[StepCheckpoint]]]:
        """Fetch checkpoint and compute exactly which steps need execution upon resume."""
        checkpoint = await self.store.load(task_id)
        if not checkpoint:
            return None

        # Determine pending steps
        pending_steps = [
            s for s in checkpoint.steps
            if s.status not in (StepStatus.COMPLETED, StepStatus.RECOVERED, StepStatus.SKIPPED)
        ]
        return checkpoint, pending_steps
