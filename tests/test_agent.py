"""Tests for Swarm agent planning, execution, and multi-tier recovery."""

import pytest
from swarm.checkpoint.models import StepStatus, TaskStatus
from swarm.checkpoint.redis_store import MemoryCheckpointStore
from swarm.runtime.agent import SwarmAgent
from swarm.runtime.state import Step
from swarm.tools.builtin import FlakyMockTool, create_default_tool_registry


@pytest.mark.asyncio
async def test_agent_basic_run():
    store = MemoryCheckpointStore()
    agent = SwarmAgent(checkpoint_store=store)
    state = await agent.run(goal="Calculate 50 * 20 and store the answer in memory")

    assert state.status == TaskStatus.COMPLETED
    assert state.plan is not None
    assert len(state.plan.steps) > 0
    assert all(s.status in (StepStatus.COMPLETED, StepStatus.RECOVERED) for s in state.plan.steps)


@pytest.mark.asyncio
async def test_agent_recovers_without_restarting():
    tools = create_default_tool_registry()
    flaky = FlakyMockTool()
    tools.register(flaky)

    store = MemoryCheckpointStore()
    agent = SwarmAgent(tool_registry=tools, checkpoint_store=store)

    # Goal triggers multi-step execution with a tool that fails on first attempt
    state = await agent.run(goal="Test flaky service retry recovery and report results")

    assert state.status == TaskStatus.COMPLETED
    assert state.plan is not None
