"""Evaluation harness runner for scoring 40 benchmark task types."""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from swarm.checkpoint.models import StepStatus, TaskStatus
from swarm.checkpoint.redis_store import MemoryCheckpointStore
from swarm.evals.dataset import EVAL_DATASET, EvalTask
from swarm.runtime.agent import SwarmAgent
from swarm.runtime.state import Step
from swarm.tools.builtin import FlakyMockTool, create_default_tool_registry

logger = logging.getLogger("swarm.evals.runner")


class EvalTaskResult(BaseModel):
    task_id: str
    category: str
    name: str
    passed: bool
    duration_ms: float
    retries_used: int = 0
    recovered: bool = False
    error: Optional[str] = None
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0


class EvalBenchmarkReport(BaseModel):
    total_tasks: int = 40
    passed_tasks: int = 0
    failed_tasks: int = 0
    accuracy_pct: float = 0.0
    recovery_rate_pct: float = 0.0
    total_duration_ms: float = 0.0
    avg_latency_ms: float = 0.0
    total_raw_tokens: int = 0
    total_cached_tokens: int = 0
    token_savings_pct: float = 0.0
    category_breakdown: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    task_results: List[EvalTaskResult] = Field(default_factory=list)


class EvalHarness:
    """Orchestrates test execution across the 40 benchmark task types."""

    def __init__(self, agent: Optional[SwarmAgent] = None) -> None:
        self.agent = agent

    async def _setup_agent_for_task(self, task: EvalTask) -> SwarmAgent:
        tools = create_default_tool_registry()

        # Configure flaky tool for recovery testing if applicable
        if task.category == "Failure Recovery":
            flaky = FlakyMockTool()
            tools.register(flaky)

        # Use an isolated store per eval task
        store = MemoryCheckpointStore()
        return SwarmAgent(tool_registry=tools, checkpoint_store=store)

    async def evaluate_single_task(self, task: EvalTask) -> EvalTaskResult:
        """Run and score a single evaluation task."""
        agent = await self._setup_agent_for_task(task)
        start_time = time.perf_counter()

        passed = False
        error_msg = None
        retries = 0
        recovered = False

        try:
            # Special simulation for durable checkpoint resumption tasks
            if task.category == "Durable Checkpoints":
                # Step 1: Run partial task
                state1 = await agent.run(goal=task.prompt)
                task_id = state1.task_id

                # Step 2: Simulate process crash/interruption by marking final step pending
                checkpoint = await agent._checkpoint_manager.store.load(task_id)
                if checkpoint and len(checkpoint.steps) >= 2:
                    # Reset the last step to pending to simulate mid-workflow crash
                    checkpoint.steps[-1].status = StepStatus.PENDING
                    checkpoint.steps[-1].tool_output = None
                    checkpoint.status = TaskStatus.RUNNING
                    await agent._checkpoint_manager.store.save(checkpoint)

                    # Step 3: Call durable resume_task
                    resumed_state = await agent.resume_task(task_id)
                    passed = resumed_state is not None and resumed_state.status == TaskStatus.COMPLETED
                    recovered = True
                else:
                    passed = state1.status == TaskStatus.COMPLETED
            else:
                # Standard task execution
                state = await agent.run(goal=task.prompt)
                passed = state.status == TaskStatus.COMPLETED
                retries = sum(s.retries for s in state.plan.steps) if state.plan else 0
                recovered = any(s.status == StepStatus.RECOVERED for s in state.plan.steps) if state.plan else False

        except Exception as e:
            error_msg = str(e)
            passed = False

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        token_snap = agent.prompt_cache.metrics.snapshot()
        return EvalTaskResult(
            task_id=task.id,
            category=task.category,
            name=task.name,
            passed=passed,
            duration_ms=round(duration_ms, 2),
            retries_used=retries,
            recovered=recovered,
            error=error_msg,
            prompt_tokens=token_snap.prompt_tokens,
            cached_tokens=token_snap.cached_prompt_tokens,
            completion_tokens=token_snap.completion_tokens,
        )

    async def run_benchmark(
        self,
        task_subset: Optional[List[str]] = None,
        concurrency: int = 4,
    ) -> EvalBenchmarkReport:
        """Run all 40 benchmark tasks and aggregate comprehensive score report."""
        tasks = EVAL_DATASET
        if task_subset:
            tasks = [t for t in EVAL_DATASET if t.id in task_subset or t.category in task_subset]

        logger.info(f"Starting eval benchmark over {len(tasks)} tasks (concurrency={concurrency})...")
        start_bench = time.perf_counter()

        semaphore = asyncio.Semaphore(concurrency)

        async def _eval_with_sem(t: EvalTask) -> EvalTaskResult:
            async with semaphore:
                return await self.evaluate_single_task(t)

        results = await asyncio.gather(*[_eval_with_sem(t) for t in tasks])

        total_duration = (time.perf_counter() - start_bench) * 1000.0
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        accuracy = round((passed_count / len(results)) * 100.0, 2) if results else 0.0

        # Failure recovery rate on recovery tasks
        recovery_tasks = [r for r in results if r.category in ("Failure Recovery", "Durable Checkpoints")]
        recovery_passed = sum(1 for r in recovery_tasks if r.passed)
        recovery_rate = round((recovery_passed / len(recovery_tasks)) * 100.0, 2) if recovery_tasks else 100.0

        # Category breakdowns
        categories: Dict[str, Dict[str, Any]] = {}
        for r in results:
            cat = r.category
            if cat not in categories:
                categories[cat] = {"total": 0, "passed": 0, "avg_duration_ms": 0.0, "total_duration": 0.0}
            categories[cat]["total"] += 1
            if r.passed:
                categories[cat]["passed"] += 1
            categories[cat]["total_duration"] += r.duration_ms

        for cat, data in categories.items():
            data["pass_rate_pct"] = round((data["passed"] / data["total"]) * 100.0, 1)
            data["avg_duration_ms"] = round(data["total_duration"] / data["total"], 1)
            del data["total_duration"]

        total_prompt = sum(r.prompt_tokens for r in results)
        total_cached = sum(r.cached_tokens for r in results)
        token_savings = round((total_cached / (total_prompt + total_cached)) * 100.0, 2) if (total_prompt + total_cached) > 0 else 0.0

        return EvalBenchmarkReport(
            total_tasks=len(results),
            passed_tasks=passed_count,
            failed_tasks=failed_count,
            accuracy_pct=accuracy,
            recovery_rate_pct=recovery_rate,
            total_duration_ms=round(total_duration, 1),
            avg_latency_ms=round(total_duration / len(results), 1) if results else 0.0,
            total_raw_tokens=total_prompt,
            total_cached_tokens=total_cached,
            token_savings_pct=token_savings,
            category_breakdown=categories,
            task_results=results,
        )
