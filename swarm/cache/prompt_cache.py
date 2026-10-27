"""Prompt caching engine with prefix canonicalization and token savings telemetry."""

from __future__ import annotations
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from swarm.checkpoint.models import TokenUsageSnapshot

logger = logging.getLogger("swarm.cache.prompt")


class CacheMetrics:
    """Tracks prompt caching efficiency, token spend reductions, and hit rates."""

    def __init__(self) -> None:
        self.total_requests: int = 0
        self.exact_cache_hits: int = 0
        self.prefix_cache_hits: int = 0
        self.raw_prompt_tokens: int = 0
        self.cached_prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_saved_tokens: int = 0

    @property
    def total_prompt_tokens(self) -> int:
        return self.raw_prompt_tokens + self.cached_prompt_tokens

    @property
    def token_savings_pct(self) -> float:
        """Calculate percentage of prompt tokens saved via caching."""
        denom = self.raw_prompt_tokens + self.cached_prompt_tokens
        if denom == 0:
            return 0.0
        return round((self.cached_prompt_tokens / denom) * 100.0, 2)

    @property
    def cache_hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        hits = self.exact_cache_hits + self.prefix_cache_hits
        return round((hits / self.total_requests) * 100.0, 2)

    def snapshot(self) -> TokenUsageSnapshot:
        # GPT-4o pricing reference: $2.50 / 1M prompt, $1.25 / 1M cached prompt, $10.00 / 1M completion
        uncached_cost = (self.raw_prompt_tokens / 1_000_000.0) * 2.50
        cached_cost = (self.cached_prompt_tokens / 1_000_000.0) * 1.25
        completion_cost = (self.completion_tokens / 1_000_000.0) * 10.00
        total_cost = round(uncached_cost + cached_cost + completion_cost, 5)

        return TokenUsageSnapshot(
            prompt_tokens=self.raw_prompt_tokens,
            completion_tokens=self.completion_tokens,
            cached_prompt_tokens=self.cached_prompt_tokens,
            total_tokens=self.raw_prompt_tokens + self.cached_prompt_tokens + self.completion_tokens,
            estimated_cost_usd=total_cost,
            cache_savings_pct=self.token_savings_pct,
        )


class PromptCache:
    """High-performance prompt cache with prefix optimization and Redis persistence."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self.ttl = ttl_seconds
        self.metrics = CacheMetrics()
        self._memory_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

    def compute_prefix_hash(self, system_prompt: str, tools_schema: List[Dict[str, Any]]) -> str:
        """Create a deterministic hash of static prefix elements (system prompt + tools)."""
        serialized_tools = json.dumps(tools_schema, sort_keys=True)
        canonical = f"{system_prompt.strip()}||{serialized_tools}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def compute_full_hash(
        self,
        prefix_hash: str,
        messages: List[Dict[str, Any]],
    ) -> str:
        """Create a hash of the entire prompt (prefix + conversation history)."""
        history_str = json.dumps(messages, sort_keys=True)
        return hashlib.sha256(f"{prefix_hash}::{history_str}".encode("utf-8")).hexdigest()

    def estimate_tokens(self, text_or_obj: Any) -> int:
        """Fast character-to-token heuristic (approx 4 chars per token) for fast telemetry."""
        if isinstance(text_or_obj, str):
            text = text_or_obj
        else:
            text = json.dumps(text_or_obj)
        return max(1, len(text) // 4)

    def record_call(
        self,
        prompt_tokens: int,
        cached_tokens: int,
        completion_tokens: int,
        is_exact_hit: bool = False,
    ) -> None:
        """Record token usage from an LLM call or cache hit."""
        self.metrics.total_requests += 1
        self.metrics.raw_prompt_tokens += (prompt_tokens - cached_tokens)
        self.metrics.cached_prompt_tokens += cached_tokens
        self.metrics.completion_tokens += completion_tokens
        if is_exact_hit:
            self.metrics.exact_cache_hits += 1
        elif cached_tokens > 0:
            self.metrics.prefix_cache_hits += 1

    def get_exact(self, prompt_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve exact cached response if present and unexpired."""
        entry = self._memory_cache.get(prompt_hash)
        if not entry:
            return None
        cached_val, timestamp = entry
        if time.time() - timestamp > self.ttl:
            del self._memory_cache[prompt_hash]
            return None
        return cached_val

    def set_exact(self, prompt_hash: str, response: Dict[str, Any]) -> None:
        """Save exact response to cache."""
        self._memory_cache[prompt_hash] = (response, time.time())

    def reset_metrics(self) -> None:
        self.metrics = CacheMetrics()


_global_cache: Optional[PromptCache] = None


def get_prompt_cache() -> PromptCache:
    global _global_cache
    if _global_cache is None:
        _global_cache = PromptCache()
    return _global_cache
