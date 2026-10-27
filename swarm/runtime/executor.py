"""DAG step executor with parallel execution and atomic checkpoint commits."""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from swarm.checkpoint.manager import CheckpointManager
from swarm.checkpoint.models import StepStatus
from swarm.runtime.planner import TaskPlanner
from swarm.runtime.recovery import RecoveryEngine
from swarm.runtime.state import Plan, Step
from swarm.tools.base import ToolRegistry, ToolResult

logger = logging.getLogger("swarm.runtime.executor")


class StepExecutor:
    """Executes DAG plan steps with concurrency, recovery, and durable Redis checkpointing."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        checkpoint_manager: CheckpointManager,
        recovery_engine: RecoveryEngine,
        planner: TaskPlanner,
        max_parallel_steps: int = 4,
    ) -> None:
        self.tools = tool_registry
        self.checkpoint_manager = checkpoint_manager
        self.recovery = recovery_engine
        self.planner = planner
        self.semaphore = asyncio.Semaphore(max_parallel_steps)

    async def _execute_single_tool(self, step: Step) -> ToolResult:
        if not step.tool_name:
            # Reasoning or no-op step
            return ToolResult(success=True, data=f"Completed reasoning: {step.description}")
        return await self.tools.execute(step.tool_name, **step.tool_input)

    async def execute_step(self, task_id: str, step: Step, plan: Plan) -> bool:
        """Execute a single step with concurrency limits, multi-tier recovery, and checkpointing."""
        async with self.semaphore:
            logger.info(f"Starting step [{step.id}] for task {task_id}: {step.description}")
            await self.checkpoint_manager.record_step_start(task_id, step.id)
            step.status = StepStatus.RUNNING

            start_time = time.perf_counter()

            # Execute via recovery engine (Tier 1 retries + Tier 2 fallbacks)
            recovery_result = await self.recovery.execute_with_recovery(
                step=step,
                execute_fn=self._execute_single_tool,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            step.duration_ms = duration_ms

            if recovery_result.recovered:
                step.status = StepStatus.COMPLETED if recovery_result.retries == 0 else StepStatus.RECOVERED
                step.output = recovery_result.output
                step.retries = recovery_result.retries

                # Commit to durable store
                await self.checkpoint_manager.record_step_completion(
                    task_id=task_id,
                    step_id=step.id,
                    output=step.output,
                    duration_ms=duration_ms,
                    memory_updates={f"step_output_{step.id}": step.output},
                )
                logger.info(
                    f"Step [{step.id}] succeeded in {duration_ms:.1f}ms "
                    f"(strategy: {recovery_result.strategy}, retries: {recovery_result.retries})"
                )
                return True

            # If unrecovered, trigger Tier 3: Dynamic Replanning without full restart!
            logger.warning(
                f"Step [{step.id}] failed after {recovery_result.retries} retries: {recovery_result.error}. "
                f"Triggering Tier 3 Dynamic Replanning..."
            )
            step.status = StepStatus.FAILED
            step.error = recovery_result.error

            await self.checkpoint_manager.record_step_failure(
                task_id=task_id,
                step_id=step.id,
                error=recovery_result.error or "Unknown failure",
                retries=recovery_result.retries,
                recovered=False,
            )

            # Attempt dynamic replan
            completed_steps = [s for s in plan.steps if s.status in (StepStatus.COMPLETED, StepStatus.RECOVERED)]
            try:
                revised_steps = await self.planner.replan_on_failure(
                    goal=plan.goal,
                    completed_steps=completed_steps,
                    failed_step=step,
                    error=recovery_result.error or "Tool failure",
                )
                if revised_steps:
                    # Update active plan
                    plan.steps = completed_steps + revised_steps
                    await self.checkpoint_manager.update_plan_dynamically(
                        task_id=task_id,
                        new_remaining_steps=[s.model_dump() for s in revised_steps],
                        reason=f"Dynamic replan after step {step.id} failure ({recovery_result.error})",
                    )
                    logger.info(f"Task {task_id} successfully replanned with {len(revised_steps)} new steps!")
                    return True
            except Exception as replan_err:
                logger.error(f"Dynamic replan failed: {replan_err}")

            return False

    async def execute_plan(
        self,
        task_id: str,
        plan: Plan,
        step_callback: Optional[Callable[[Step], Any]] = None,
    ) -> bool:
        """Executes plan steps respecting dependency ordering and allowing parallel execution."""
        while not plan.is_finished():
            ready = plan.ready_steps()
            if not ready:
                # No ready steps and not finished: either deadlocked on failure or complete
                failed = [s for s in plan.steps if s.status == StepStatus.FAILED]
                if failed:
                    logger.error(f"Execution halted on failed steps: {[s.id for s in failed]}")
                    return False
                break

            # Execute ready steps concurrently
            tasks = [self.execute_step(task_id, step, plan) for step in ready]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, res in zip(ready, results):
                if isinstance(res, Exception) or res is False:
                    # If any step failed and could not be recovered/replanned, halt
                    if step.status == StepStatus.FAILED:
                        return False

                if step_callback:
                    try:
                        step_callback(step)
                    except Exception:
                        pass

        return plan.is_finished()
