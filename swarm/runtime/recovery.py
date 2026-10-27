"""Multi-tier failure recovery engine for agent tasks."""

from __future__ import annotations
import asyncio
import logging
import random
from typing import Any, Callable, Dict, Optional, Tuple
from swarm.config import settings
from swarm.runtime.state import Step
from swarm.tools.base import ToolRegistry, ToolResult

logger = logging.getLogger("swarm.runtime.recovery")


class RecoveryResult:
    """Outcome of recovery attempt."""
    def __init__(
        self,
        recovered: bool,
        output: Optional[Any] = None,
        strategy: Optional[str] = None,
        retries: int = 0,
        error: Optional[str] = None,
    ) -> None:
        self.recovered = recovered
        self.output = output
        self.strategy = strategy
        self.retries = retries
        self.error = error


class RecoveryEngine:
    """Executes multi-tier recovery strategies to handle failures without restarting the agent."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        self.tools = tool_registry
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def execute_with_recovery(
        self,
        step: Step,
        execute_fn: Callable[[Step], Any],
    ) -> RecoveryResult:
        """Executes a step with automatic multi-tiered fault recovery."""
        retries = 0
        last_error = ""

        # --- Tier 1: Retry with exponential backoff & jitter ---
        while retries <= self.max_retries:
            try:
                res: ToolResult = await execute_fn(step)
                if res.success:
                    strategy = "retry_success" if retries > 0 else "direct_success"
                    if res.fallback_used:
                        strategy = "fallback_tool"
                    return RecoveryResult(
                        recovered=True,
                        output=res.data,
                        strategy=strategy,
                        retries=retries,
                    )
                last_error = res.error or "Unknown tool error"
            except Exception as e:
                last_error = str(e)

            retries += 1
            if retries <= self.max_retries:
                # Exponential backoff + small jitter
                delay = (self.backoff_factor * (2 ** (retries - 1))) + random.uniform(0.01, 0.05)
                logger.info(
                    f"Step {step.id} failed ({last_error}). Retrying ({retries}/{self.max_retries}) in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)

        # --- Tier 2: Check for fallback tool if primary failed ---
        if step.tool_name:
            fallback_name = self.tools.get_fallback_name(step.tool_name)
            if fallback_name:
                logger.info(f"Tier 2 Recovery: Attempting fallback tool '{fallback_name}' for step {step.id}")
                try:
                    fallback_result = await self.tools.execute(fallback_name, **step.tool_input)
                    if fallback_result.success:
                        return RecoveryResult(
                            recovered=True,
                            output=fallback_result.data,
                            strategy="fallback_tool",
                            retries=retries,
                        )
                    last_error = f"Fallback {fallback_name} failed: {fallback_result.error}"
                except Exception as fb_err:
                    last_error = f"Fallback error: {fb_err}"

        # If tier 1 and tier 2 both failed, return recovery failure so Tier 3 (Dynamic Replan) can trigger
        return RecoveryResult(
            recovered=False,
            strategy="unrecovered_needs_replan",
            retries=retries,
            error=last_error,
        )
