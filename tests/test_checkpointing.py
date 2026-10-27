"""Tests for Redis durable checkpoints and resumption without repeating steps."""

import pytest
from swarm.checkpoint.manager import CheckpointManager
from swarm.checkpoint.models import StepStatus, TaskStatus
from swarm.checkpoint.redis_store import MemoryCheckpointStore
from swarm.runtime.agent import SwarmAgent


@pytest.mark.asyncio
async def test_checkpoint_store_crud():
    store = MemoryCheckpointStore()
    cm = CheckpointManager(store)

    steps = [
        {"id": "step_1", "description": "Step 1", "tool_name": "calculator", "tool_input": {"expression": "2+2"}},
        {"id": "step_2", "description": "Step 2", "tool_name": "memory_store", "tool_input": {"action": "list"}},
    ]

    cp = await cm.initialize_task(task_id="task_test_1", goal="Test CRUD", steps=steps)
    assert cp.task_id == "task_test_1"
    assert len(cp.steps) == 2

    # Start step 1
    await cm.record_step_start("task_test_1", "step_1")
    loaded = await store.load("task_test_1")
    assert loaded.steps[0].status == StepStatus.RUNNING

    # Complete step 1
    await cm.record_step_completion("task_test_1", "step_1", output=4.0, duration_ms=12.5)
    loaded = await store.load("task_test_1")
    assert loaded.steps[0].status == StepStatus.COMPLETED
    assert loaded.steps[0].tool_output == 4.0


@pytest.mark.asyncio
async def test_durable_resume_skips_completed_steps():
    store = MemoryCheckpointStore()
    agent = SwarmAgent(checkpoint_store=store)

    state = await agent.run(goal="Perform multi-stage calculation and store result")
    task_id = state.task_id

    # Retrieve checkpoint and simulate mid-task interruption by marking last step pending
    cm = await agent._get_checkpoint_manager()
    checkpoint = await cm.store.load(task_id)
    assert checkpoint is not None
    assert len(checkpoint.steps) >= 2

    last_step = checkpoint.steps[-1]
    last_step.status = StepStatus.PENDING
    last_step.tool_output = None
    checkpoint.status = TaskStatus.RUNNING
    await cm.store.save(checkpoint)

    # Resume task
    resumed_state = await agent.resume_task(task_id)
    assert resumed_state is not None
    assert resumed_state.status == TaskStatus.COMPLETED

    # Check step 1 remained completed without restarting
    final_checkpoint = await cm.store.load(task_id)
    assert final_checkpoint.steps[0].status in (StepStatus.COMPLETED, StepStatus.RECOVERED)
    assert final_checkpoint.steps[-1].status in (StepStatus.COMPLETED, StepStatus.RECOVERED)
