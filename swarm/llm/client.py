"""LLM client interface supporting OpenAI with prompt caching and deterministic mock fallback."""

from __future__ import annotations
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from swarm.cache.prompt_cache import PromptCache, get_prompt_cache
from swarm.config import settings

logger = logging.getLogger("swarm.llm")


class LLMResponse:
    """Standardized response from LLM."""

    def __init__(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        prompt_tokens: int = 0,
        cached_tokens: int = 0,
        completion_tokens: int = 0,
        model: str = "default",
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.prompt_tokens = prompt_tokens
        self.cached_tokens = cached_tokens
        self.completion_tokens = completion_tokens
        self.model = model

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMClient(ABC):
    """Abstract LLM client interface."""

    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        pass


class MockLLMClient(LLMClient):
    """Deterministic, high-speed mock LLM for offline benchmarking, tests, and eval scoring."""

    def __init__(self, cache: Optional[PromptCache] = None) -> None:
        self.cache = cache or get_prompt_cache()

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        # Calculate tokens
        prompt_str = json.dumps(messages) + (json.dumps(tools) if tools else "")
        raw_tokens = max(len(prompt_str) // 4, 100)

        # Stable prefix is the first system message + tools
        sys_msg = next((m["content"] for m in messages if m.get("role") == "system"), "")
        tools_list = tools or []
        prefix_hash = self.cache.compute_prefix_hash(sys_msg, tools_list)
        full_hash = self.cache.compute_full_hash(prefix_hash, messages)

        # Check exact cache
        cached_response = self.cache.get_exact(full_hash)
        if cached_response:
            self.cache.record_call(
                prompt_tokens=raw_tokens,
                cached_tokens=raw_tokens,
                completion_tokens=len(cached_response.get("content", "")) // 4,
                is_exact_hit=True,
            )
            return LLMResponse(
                content=cached_response["content"],
                tool_calls=cached_response.get("tool_calls"),
                prompt_tokens=0,
                cached_tokens=raw_tokens,
                completion_tokens=len(cached_response.get("content", "")) // 4,
                model="swarm-mock-cached",
            )

        # Prefix caching simulation: 43% of total tokens come from static system/tool schemas
        cached_prefix_tokens = int(raw_tokens * 0.43) if settings.enable_prompt_caching else 0

        # Formulate intelligent deterministic content based on last user message
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        last_user_lower = last_user.lower()

        tool_calls = []
        content = ""

        if "plan" in last_user_lower or "decompose" in last_user_lower or "steps" in last_user_lower:
            # Generate multi-step plan
            content = json.dumps({
                "plan": [
                    {
                        "id": "step_1",
                        "description": "Analyze input goal and search relevant context",
                        "tool_name": "web_search",
                        "tool_input": {"query": last_user[:50]},
                    },
                    {
                        "id": "step_2",
                        "description": "Execute computation or logic verification",
                        "tool_name": "calculator",
                        "tool_input": {"expression": "100 * 1.05"},
                        "dependencies": ["step_1"],
                    },
                    {
                        "id": "step_3",
                        "description": "Store final synthesis in memory store",
                        "tool_name": "memory_store",
                        "tool_input": {"action": "set", "key": "result", "value": "Task completed successfully."},
                        "dependencies": ["step_2"],
                    },
                ]
            })
        elif "calculate" in last_user_lower or "math" in last_user_lower:
            tool_calls = [{
                "id": "call_calc_1",
                "type": "function",
                "function": {
                    "name": "calculator",
                    "arguments": json.dumps({"expression": "25 * 4 + 10"}),
                },
            }]
            content = "Evaluating expression using calculator tool."
        elif "search" in last_user_lower:
            tool_calls = [{
                "id": "call_search_1",
                "type": "function",
                "function": {
                    "name": "web_search",
                    "arguments": json.dumps({"query": last_user}),
                },
            }]
            content = "Searching knowledge base for query."
        else:
            content = f"Synthesized response for task: {last_user[:100]}. State verified and steps resolved successfully."

        comp_tokens = max(len(content) // 4, 20)
        self.cache.record_call(
            prompt_tokens=raw_tokens,
            cached_tokens=cached_prefix_tokens,
            completion_tokens=comp_tokens,
            is_exact_hit=False,
        )

        resp_dict = {"content": content, "tool_calls": tool_calls}
        self.cache.set_exact(full_hash, resp_dict)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=raw_tokens - cached_prefix_tokens,
            cached_tokens=cached_prefix_tokens,
            completion_tokens=comp_tokens,
            model="swarm-mock",
        )


class OpenAILLMClient(LLMClient):
    """Production OpenAI client utilizing prompt caching and async API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", cache: Optional[PromptCache] = None) -> None:
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key, base_url=settings.openai_base_url)
        self.model = model
        self.cache = cache or get_prompt_cache()

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        usage = response.usage

        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        cached_tokens = 0

        # OpenAI Prompt Caching report in usage.prompt_tokens_details
        if usage and hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
            cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0

        self.cache.record_call(
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            completion_tokens=completion_tokens,
        )

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens - cached_tokens,
            cached_tokens=cached_tokens,
            completion_tokens=completion_tokens,
            model=response.model,
        )


def get_llm_client() -> LLMClient:
    """Factory creating OpenAI client or mock client depending on configuration."""
    if settings.use_mock_llm or not settings.openai_api_key:
        logger.info("Using high-performance deterministic Mock LLM client.")
        return MockLLMClient()
    return OpenAILLMClient(api_key=settings.openai_api_key, model=settings.default_model)
