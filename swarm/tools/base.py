"""Base tool abstractions and registry for Swarm runtime."""

from __future__ import annotations
import inspect
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("swarm.tools")


class ToolResult(BaseModel):
    """Standardized tool execution outcome."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    fallback_used: bool = False


class BaseTool(ABC):
    """Abstract base class for all agent tools."""

    name: str
    description: str
    parameters: Dict[str, Any]

    @abstractmethod
    async def run(self, **kwargs: Any) -> Any:
        """Execute the tool logic asynchronously."""
        pass

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert tool to OpenAI Function Calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class FunctionalTool(BaseTool):
    """Wraps a standard Python async or sync function as an agent tool."""

    def __init__(
        self,
        name: str,
        description: str,
        fn: Callable[..., Any],
        parameters: Dict[str, Any],
    ) -> None:
        self.name = name
        self.description = description
        self.fn = fn
        self.parameters = parameters

    async def run(self, **kwargs: Any) -> Any:
        if inspect.iscoroutinefunction(self.fn):
            return await self.fn(**kwargs)
        return self.fn(**kwargs)


class ToolRegistry:
    """Registry managing available agent tools and dynamic execution."""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self._fallbacks: Dict[str, str] = {}  # primary_tool -> fallback_tool

    def register(self, tool: BaseTool, fallback_tool: Optional[str] = None) -> None:
        self._tools[tool.name] = tool
        if fallback_tool:
            self._fallbacks[tool.name] = fallback_tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_fallback_name(self, name: str) -> Optional[str]:
        return self._fallbacks.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def execute(self, tool_name: str, **kwargs: Any) -> ToolResult:
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found in registry. Available: {self.list_tools()}",
            )

        start = time.perf_counter()
        try:
            output = await tool.run(**kwargs)
            duration = (time.perf_counter() - start) * 1000.0
            return ToolResult(success=True, data=output, execution_time_ms=duration)
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000.0
            logger.warning(f"Tool {tool_name} failed: {e}. Checking for fallback...")

            # Check if there is an alternative fallback tool registered
            fallback_name = self.get_fallback_name(tool_name)
            if fallback_name and fallback_name in self._tools:
                logger.info(f"Executing registered fallback tool '{fallback_name}' for '{tool_name}'")
                fb_start = time.perf_counter()
                try:
                    fb_tool = self._tools[fallback_name]
                    fb_output = await fb_tool.run(**kwargs)
                    fb_duration = (time.perf_counter() - fb_start) * 1000.0
                    return ToolResult(
                        success=True,
                        data=fb_output,
                        execution_time_ms=duration + fb_duration,
                        fallback_used=True,
                    )
                except Exception as fb_err:
                    return ToolResult(
                        success=False,
                        error=f"Primary tool '{tool_name}' failed ({e}) and fallback '{fallback_name}' also failed ({fb_err})",
                        execution_time_ms=duration,
                    )

            return ToolResult(
                success=False,
                error=str(e),
                execution_time_ms=duration,
            )
