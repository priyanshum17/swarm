"""High-level Swarm Agent coordinator with durable execution and resumption."""

from __future__ import annotations
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional
from swarm.cache.prompt_cache import PromptCache, get_prompt_cache
from swarm.checkpoint.manager import CheckpointManager
from swarm.checkpoint.models import StepStatus, TaskCheckpoint, TaskStatus
from swarm.checkpoint.redis_store import CheckpointStoreInterface, get_checkpoint_store
from swarm.config import settings
from swarm.llm.client import LLMClient, get_llm_client
from swarm.runtime.executor import StepExecutor
from swarm.runtime.planner import TaskPlanner
from swarm.runtime.recovery import RecoveryEngine
from swarm.runtime.state import AgentState, Plan, Step
from swarm.tools.base import ToolRegistry
from swarm.tools.builtin import create_default_tool_registry

logger = logging.getLogger("swarm.runtime.agent")


class SwarmAgent:
    """Production agent runtime that plans multi-step tasks, calls tools, and recovers from failures."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
        checkpoint_store: Optional[CheckpointStoreInterface] = None,
        prompt_cache: Optional[PromptCache] = None,
    ) -> None:
        self.prompt_cache = prompt_cache or get_prompt_cache()
        self.llm = llm_client or get_llm_client()
        if hasattr(self.llm, "cache"):
            self.llm.cache = self.prompt_cache
        self.tools = tool_registry or create_default_tool_registry()
        self._store = checkpoint_store
        self._checkpoint_manager: Optional[CheckpointManager] = None
        self._planner = TaskPlanner(self.llm, self.tools)
        self._recovery = RecoveryEngine(
            tool_registry=self.tools,
            max_retries=settings.max_step_retries,
            backoff_factor=settings.retry_backoff_factor,
        )

    async def _get_checkpoint_manager(self) -> CheckpointManager:
        if self._checkpoint_manager is None:
            if self._store is None:
                self._store = await get_checkpoint_store(settings.redis_url)
            self._checkpoint_manager = CheckpointManager(self._store)
        return self._checkpoint_manager

    async def run(
        self,
        goal: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        step_callback: Optional[Callable[[Step], Any]] = None,
    ) -> AgentState:
        """Run an agent goal from inception to completion with durable Redis checkpoints."""
        task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        cm = await self._get_checkpoint_manager()

        logger.info(f"Initiating agent run for task {task_id}: {goal}")

        # 1. Plan decomposition
        plan = await self._planner.create_plan(goal)

        # 2. Durable checkpoint initialization
        raw_steps = [s.model_dump() for s in plan.steps]
        await cm.initialize_task(task_id=task_id, goal=goal, steps=raw_steps, metadata=metadata)

        # 3. Step execution with recovery & concurrency
        executor = StepExecutor(
            tool_registry=self.tools,
            checkpoint_manager=cm,
            recovery_engine=self._recovery,
            planner=self._planner,
            max_parallel_steps=settings.max_parallel_steps,
        )

        success = await executor.execute_plan(task_id, plan, step_callback=step_callback)

        # 4. Final state packaging & token metrics
        final_checkpoint = await cm.store.load(task_id)
        token_snapshot = self.prompt_cache.metrics.snapshot()

        state = AgentState(
            task_id=task_id,
            goal=goal,
            plan=plan,
            memory=final_checkpoint.context_memory if final_checkpoint else {},
            status=TaskStatus.COMPLETED if success else TaskStatus.FAILED,
            tokens=token_snapshot,
            recovered_failures_count=sum(
                1 for s in plan.steps if s.status == StepStatus.RECOVERED or s.retries > 0
            ),
        )

        # Commit final token snapshot to checkpoint
        if final_checkpoint:
            final_checkpoint.tokens = token_snapshot
            final_checkpoint.status = state.status
            await cm.store.save(final_checkpoint)

        logger.info(f"Task {task_id} concluded with status: {state.status.value}")
        return state

    async def resume_task(
        self,
        task_id: str,
        step_callback: Optional[Callable[[Step], Any]] = None,
    ) -> Optional[AgentState]:
        """Resume an interrupted or failed task from its latest Redis checkpoint."""
        cm = await self._get_checkpoint_manager()
        res = await cm.get_resumption_state(task_id)
        if not res:
            logger.error(f"Cannot resume task {task_id}: Checkpoint not found.")
            return None

        checkpoint, pending = res
        logger.info(
            f"Resuming task {task_id}. Total steps: {len(checkpoint.steps)}, "
            f"Already completed: {len(checkpoint.completed_step_ids())}, Pending: {len(pending)}"
        )

        # Reconstruct runtime Plan
        runtime_steps: List[Step] = []
        for s in checkpoint.steps:
            runtime_steps.append(
                Step(
                    id=s.step_id,
                    description=s.description,
                    tool_name=s.tool_name,
                    tool_input=s.tool_input or {},
                    dependencies=s.dependencies,
                    status=s.status,
                    output=s.tool_output,
                    error=s.error,
                    retries=s.retries,
                    duration_ms=s.execution_time_ms or 0.0,
                )
            )

        plan = Plan(goal=checkpoint.goal, steps=runtime_steps)

        executor = StepExecutor(
            tool_registry=self.tools,
            checkpoint_manager=cm,
            recovery_engine=self._recovery,
            planner=self._planner,
            max_parallel_steps=settings.max_parallel_steps,
        )

        # Execute only non-completed steps
        success = await executor.execute_plan(task_id, plan, step_callback=step_callback)

        token_snapshot = self.prompt_cache.metrics.snapshot()
        state = AgentState(
            task_id=task_id,
            goal=checkpoint.goal,
            plan=plan,
            memory=checkpoint.context_memory,
            status=TaskStatus.COMPLETED if success else TaskStatus.FAILED,
            tokens=token_snapshot,
            recovered_failures_count=sum(
                1 for s in plan.steps if s.status == StepStatus.RECOVERED or s.retries > 0
            ),
        )

        fresh_checkpoint = await cm.store.load(task_id) or checkpoint
        fresh_checkpoint.status = state.status
        fresh_checkpoint.tokens = token_snapshot
        await cm.store.save(fresh_checkpoint)
        return state
