"""Tests for the 40-task benchmark evaluation harness."""

import pytest
from swarm.evals.dataset import EVAL_DATASET
from swarm.evals.runner import EvalHarness


def test_eval_dataset_has_40_tasks():
    assert len(EVAL_DATASET) == 40
    categories = {t.category for t in EVAL_DATASET}
    assert len(categories) == 8
    for cat in categories:
        cat_tasks = [t for t in EVAL_DATASET if t.category == cat]
        assert len(cat_tasks) == 5, f"Category {cat} does not have exactly 5 tasks"


@pytest.mark.asyncio
async def test_eval_harness_subset_run():
    harness = EvalHarness()
    # Test a small subset of 3 tasks for speed
    report = await harness.run_benchmark(task_subset=["code_01", "math_01", "tool_01"], concurrency=3)
    assert report.total_tasks == 3
    assert report.passed_tasks == 3
    assert report.accuracy_pct == 100.0
