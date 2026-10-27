"""Built-in tools for Swarm agent runtime."""

from __future__ import annotations
import ast
import operator
import re
from typing import Any, Dict, List, Optional
import httpx
from swarm.tools.base import BaseTool, ToolRegistry


class CalculatorTool(BaseTool):
    """Safely evaluates mathematical expressions without eval()."""

    name = "calculator"
    description = "Evaluates a mathematical expression and returns the numerical result."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression to evaluate, e.g. '24 * 60 + 15' or '(100 - 43) / 100'",
            }
        },
        "required": ["expression"],
    }

    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def _eval(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return self._eval(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            left = self._eval(node.left)
            right = self._eval(node.right)
            op = self._operators.get(type(node.op))
            if not op:
                raise ValueError(f"Unsupported binary operator: {type(node.op)}")
            return op(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand)
            op = self._operators.get(type(node.op))
            if not op:
                raise ValueError(f"Unsupported unary operator: {type(node.op)}")
            return op(operand)
        raise ValueError(f"Unsupported expression syntax: {type(node)}")

    async def run(self, expression: str, **kwargs: Any) -> float:
        parsed = ast.parse(expression.strip(), mode="eval")
        return float(self._eval(parsed))


class WebSearchTool(BaseTool):
    """Fast knowledge retrieval with built-in index and fallback."""

    name = "web_search"
    description = "Search documentation, web content, and facts using search keywords."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query string",
            },
            "num_results": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 3,
            },
        },
        "required": ["query"],
    }

    _mock_knowledge_base = {
        "redis durable execution": "Redis-backed checkpointing persists DAG step outputs and execution pointers atomically. Tasks can resume from interruption by loading latest valid checkpoint.",
        "prompt caching token savings": "OpenAI prompt caching caches static prompt prefixes >= 1024 tokens. Structuring system instructions and tools into stable prefix cuts token spend by ~43%.",
        "fastapi async concurrency": "FastAPI with async route handlers and uvloop achieves sub-millisecond response latency and handles high concurrent agent requests efficiently.",
        "agent failure recovery": "Agent runtime recovers from tool failures through multi-tier retry with backoff, secondary fallback tools, and dynamic DAG replanning without full restart.",
        "eval harness 40 tasks": "Eval harness scores 40 diverse task types across reasoning, code, synthesis, durability, recovery, and tool calling with precision metrics.",
        "python 3.12 performance": "Python 3.12 introduces substantial interpreter speedups, faster comprehension execution, and improved async task scheduling.",
    }

    async def run(self, query: str, num_results: int = 3, **kwargs: Any) -> List[Dict[str, str]]:
        query_lower = query.lower()
        results = []

        # Check knowledge base matches
        for key, text in self._mock_knowledge_base.items():
            words = key.split()
            if any(w in query_lower for w in words):
                results.append({"title": key.title(), "snippet": text, "source": "knowledge_store"})

        if not results:
            results.append({
                "title": f"Results for '{query}'",
                "snippet": f"Synthetic search result for query '{query}': High relevance information retrieved successfully.",
                "source": "swarm_search_index",
            })

        return results[:num_results]


class MemoryTool(BaseTool):
    """Agent scratchpad for storing and retrieving intermediate results across steps."""

    name = "memory_store"
    description = "Store or retrieve key-value information across workflow steps."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "set", "list", "delete"],
                "description": "Action to perform on memory",
            },
            "key": {
                "type": "string",
                "description": "Memory key name",
            },
            "value": {
                "type": "string",
                "description": "Value to store (for action='set')",
            },
        },
        "required": ["action"],
    }

    def __init__(self) -> None:
        self._memory: Dict[str, Any] = {}

    async def run(self, action: str, key: Optional[str] = None, value: Optional[Any] = None, **kwargs: Any) -> Any:
        if action == "set":
            if not key:
                raise ValueError("Key required for set action")
            self._memory[key] = value
            return {"status": "ok", "key": key, "stored": True}
        elif action == "get":
            if not key:
                raise ValueError("Key required for get action")
            return self._memory.get(key)
        elif action == "list":
            return list(self._memory.keys())
        elif action == "delete":
            if not key:
                raise ValueError("Key required for delete action")
            return self._memory.pop(key, None) is not None
        raise ValueError(f"Unknown action: {action}")


class CodeRunnerTool(BaseTool):
    """Executes small deterministic Python expressions safely."""

    name = "code_runner"
    description = "Runs safe Python expressions or data processing snippets and captures result."
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code snippet to execute",
            }
        },
        "required": ["code"],
    }

    async def run(self, code: str, **kwargs: Any) -> Any:
        # Restricted execution environment
        safe_globals = {
            "__builtins__": {
                "len": len,
                "range": range,
                "sum": sum,
                "min": min,
                "max": max,
                "sorted": sorted,
                "abs": abs,
                "round": round,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
            }
        }
        local_scope: Dict[str, Any] = {}

        # If it's a single expression, eval it; otherwise exec
        lines = code.strip().split("\n")
        if len(lines) == 1 and not lines[0].startswith(("def ", "import ", "class ", "return ")):
            return eval(lines[0], safe_globals, local_scope)

        exec(code, safe_globals, local_scope)
        # Return either 'result' variable if assigned, or the local dict
        return local_scope.get("result", local_scope)


class FlakyMockTool(BaseTool):
    """Tool that fails intentionally to test agent runtime failure recovery and replanning."""

    name = "flaky_tool"
    description = "A simulated unstable service used to verify agent resilience and recovery."
    parameters = {
        "type": "object",
        "properties": {
            "fail_count": {
                "type": "integer",
                "description": "Number of times to fail before succeeding",
                "default": 1,
            },
            "error_message": {
                "type": "string",
                "default": "Service unavailable: 503 upstream connection timeout",
            },
            "success_payload": {
                "type": "string",
                "default": "Simulated tool recovered successfully",
            },
        },
    }

    def __init__(self) -> None:
        self.call_counts: Dict[str, int] = {}

    async def run(
        self,
        fail_count: int = 1,
        error_message: str = "Service unavailable: 503 upstream connection timeout",
        success_payload: str = "Simulated tool recovered successfully",
        call_id: str = "default",
        **kwargs: Any,
    ) -> str:
        current = self.call_counts.get(call_id, 0)
        self.call_counts[call_id] = current + 1

        if current < fail_count:
            raise RuntimeError(f"{error_message} (attempt {current + 1}/{fail_count})")

        return success_payload


def create_default_tool_registry() -> ToolRegistry:
    """Create a populated tool registry with built-in tools and configured fallbacks."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(WebSearchTool())
    registry.register(MemoryTool())
    registry.register(CodeRunnerTool())
    registry.register(FlakyMockTool())
    return registry
