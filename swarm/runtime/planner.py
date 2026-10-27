"""Task planning and dynamic replanning engine."""

from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional
from swarm.llm.client import LLMClient
from swarm.runtime.state import Plan, Step
from swarm.tools.base import ToolRegistry

logger = logging.getLogger("swarm.runtime.planner")

PLANNER_SYSTEM_PROMPT = """You are Swarm's High-Performance Task Planner.
Decompose the user's high-level goal into an optimal, non-redundant plan of execution steps.
Each step must specify:
- id: unique string identifier (e.g., step_1, step_2)
- description: clear, actionable step description
- tool_name: tool to call (or null if reasoning step)
- tool_input: dictionary of arguments matching tool schema
- dependencies: list of step IDs that must complete before this step

Available tools:
{tools_summary}

Respond ONLY with valid JSON in this format:
{{
  "plan": [
    {{
      "id": "step_1",
      "description": "...",
      "tool_name": "...",
      "tool_input": {{ ... }},
      "dependencies": []
    }}
  ]
}}
"""

REPLANNER_SYSTEM_PROMPT = """You are Swarm's Dynamic Replanner.
An execution step failed during a multi-step task run.
DO NOT restart from the beginning. Keep the already-completed steps intact.
Provide a revised list of NEW remaining steps that achieves the goal despite the failure.

Goal: {goal}
Completed Steps and Outputs:
{completed_steps}

Failed Step:
ID: {failed_step_id}
Description: {failed_step_desc}
Error: {error}

Respond ONLY with valid JSON with the revised remaining steps:
{{
  "revised_steps": [
    {{
      "id": "step_revised_1",
      "description": "...",
      "tool_name": "...",
      "tool_input": {{ ... }},
      "dependencies": []
    }}
  ]
}}
"""


class TaskPlanner:
    """Decomposes tasks into executable plans and generates dynamic replans on failures."""

    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry) -> None:
        self.llm = llm_client
        self.tools = tool_registry

    async def create_plan(self, goal: str) -> Plan:
        """Generate an initial structured execution plan for a goal."""
        tools_summary = "\n".join(
            f"- {tool.name}: {tool.description} (parameters: {list(tool.parameters.get('properties', {}).keys())})"
            for tool in [self.tools.get(name) for name in self.tools.list_tools() if self.tools.get(name)]
        )

        system_msg = PLANNER_SYSTEM_PROMPT.format(tools_summary=tools_summary)
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Decompose this goal into executable steps: {goal}"},
        ]

        logger.debug(f"Planning steps for goal: {goal}")
        response = await self.llm.complete(messages=messages, temperature=0.1)

        try:
            content = response.content.strip()
            # Extract JSON if wrapped in markdown code blocks
            if "```" in content:
                content = content.split("```json")[-1].split("```")[0].strip()
            data = json.loads(content)
            raw_steps = data.get("plan", [])
        except Exception as e:
            logger.warning(f"Planner JSON parsing fallback: {e}. Generating structured default plan.")
            raw_steps = [
                {
                    "id": "step_1",
                    "description": f"Gather context and execute research for '{goal[:40]}'",
                    "tool_name": "web_search",
                    "tool_input": {"query": goal},
                    "dependencies": [],
                },
                {
                    "id": "step_2",
                    "description": "Process information and synthesize results",
                    "tool_name": "memory_store",
                    "tool_input": {"action": "set", "key": "goal_result", "value": "Execution complete."},
                    "dependencies": ["step_1"],
                },
            ]

        steps = [
            Step(
                id=s.get("id", f"step_{i+1}"),
                description=s["description"],
                tool_name=s.get("tool_name"),
                tool_input=s.get("tool_input", {}),
                dependencies=s.get("dependencies", []),
            )
            for i, s in enumerate(raw_steps)
        ]

        return Plan(goal=goal, steps=steps)

    async def replan_on_failure(
        self,
        goal: str,
        completed_steps: List[Step],
        failed_step: Step,
        error: str,
    ) -> List[Step]:
        """Dynamic replanning to bypass a failure without restarting completed work."""
        completed_summary = json.dumps([
            {"id": s.id, "desc": s.description, "tool": s.tool_name, "output": s.output}
            for s in completed_steps
        ], indent=2)

        prompt = REPLANNER_SYSTEM_PROMPT.format(
            goal=goal,
            completed_steps=completed_summary,
            failed_step_id=failed_step.id,
            failed_step_desc=failed_step.description,
            error=error,
        )

        messages = [
            {"role": "system", "content": "You are Swarm's Dynamic Replanner."},
            {"role": "user", "content": prompt},
        ]

        logger.info(f"Replanning for task goal '{goal[:40]}' after failure in {failed_step.id}: {error}")
        response = await self.llm.complete(messages=messages, temperature=0.2)

        try:
            content = response.content.strip()
            if "```" in content:
                content = content.split("```json")[-1].split("```")[0].strip()
            data = json.loads(content)
            revised_raw = data.get("revised_steps", [])
        except Exception:
            revised_raw = [
                {
                    "id": f"{failed_step.id}_recovered",
                    "description": f"Fallback recovery for {failed_step.description}",
                    "tool_name": "memory_store",
                    "tool_input": {"action": "set", "key": "fallback_output", "value": "Bypassed failed step"},
                    "dependencies": [s.id for s in completed_steps],
                }
            ]

        return [
            Step(
                id=s.get("id", f"step_rep_{i+1}"),
                description=s["description"],
                tool_name=s.get("tool_name"),
                tool_input=s.get("tool_input", {}),
                dependencies=s.get("dependencies", [completed_steps[-1].id] if completed_steps else []),
            )
            for i, s in enumerate(revised_raw)
        ]
