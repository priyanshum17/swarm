"""Tests for prompt caching prefix hashing and token spend reduction."""

import pytest
from swarm.cache.prompt_cache import PromptCache


def test_prefix_hash_deterministic():
    cache = PromptCache()
    sys_prompt = "You are a helpful AI agent."
    tools = [{"type": "function", "function": {"name": "calculator"}}]

    h1 = cache.compute_prefix_hash(sys_prompt, tools)
    h2 = cache.compute_prefix_hash(sys_prompt, tools)
    assert h1 == h2


def test_token_savings_metrics():
    cache = PromptCache()

    # Turn 1: 1000 prompt tokens (430 cached prefix, 570 raw), 50 completion
    cache.record_call(prompt_tokens=1000, cached_tokens=430, completion_tokens=50)

    # Turn 2: 1000 prompt tokens (430 cached prefix, 570 raw), 50 completion
    cache.record_call(prompt_tokens=1000, cached_tokens=430, completion_tokens=50)

    snap = cache.metrics.snapshot()
    assert snap.prompt_tokens == 1140
    assert snap.cached_prompt_tokens == 860
    assert snap.total_tokens == 2100
    assert snap.cache_savings_pct == 43.0
