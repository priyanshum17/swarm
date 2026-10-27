"""Benchmark dataset containing 40 distinct task types across 8 core capability categories."""

from __future__ import annotations
from typing import Any, Dict, List
from pydantic import BaseModel


class EvalTask(BaseModel):
    """Specification of an evaluation benchmark task."""
    id: str
    category: str
    name: str
    prompt: str
    expected_tools: List[str]
    success_criteria: str
    difficulty: str = "medium"


EVAL_DATASET: List[EvalTask] = [
    # ---------------- Category 1: Code Debugging & Refactoring ----------------
    EvalTask(
        id="code_01",
        category="Code Debugging",
        name="Off-by-one Index Partition",
        prompt="Debug an off-by-one error in binary search partition where high pointer causes IndexError.",
        expected_tools=["code_runner"],
        success_criteria="Identifies boundary condition high = mid - 1",
    ),
    EvalTask(
        id="code_02",
        category="Code Debugging",
        name="Unhandled NoneType Dereference",
        prompt="Fix nested JSON traversal that throws AttributeError: 'NoneType' object has no attribute 'get'.",
        expected_tools=["code_runner"],
        success_criteria="Implements safe optional chaining or dictionary get fallback",
    ),
    EvalTask(
        id="code_03",
        category="Code Debugging",
        name="Async Concurrency Race Condition",
        prompt="Refactor concurrent dictionary mutation in asyncio worker pool to prevent dirty writes.",
        expected_tools=["code_runner"],
        success_criteria="Applies asyncio.Lock or thread-safe state container",
    ),
    EvalTask(
        id="code_04",
        category="Code Debugging",
        name="Unclosed Socket Generator Leak",
        prompt="Fix resource leak in async streaming generator leaving open TCP sockets under client disconnect.",
        expected_tools=["code_runner"],
        success_criteria="Adds async context manager or try/finally socket closure",
    ),
    EvalTask(
        id="code_05",
        category="Code Debugging",
        name="Dynamic SQL Injection Mitigation",
        prompt="Refactor string-formatted raw SQL query into parameterized prepared statements.",
        expected_tools=["code_runner"],
        success_criteria="Eliminates raw f-string concatenation in query statement",
    ),

    # ---------------- Category 2: Mathematical & Algorithmic Reasoning ----------------
    EvalTask(
        id="math_01",
        category="Math Reasoning",
        name="Compound Interest with Monthly Inflows",
        prompt="Calculate the final balance of $15,000 principal at 7.2% APR compounded monthly over 12 years with $250 monthly contributions.",
        expected_tools=["calculator"],
        success_criteria="Computes numerical balance within 1% margin of error",
    ),
    EvalTask(
        id="math_02",
        category="Math Reasoning",
        name="Prime Factorization & Euler Totient",
        prompt="Compute the prime factorization and Euler totient phi(n) for n = 840.",
        expected_tools=["calculator"],
        success_criteria="Returns correct prime factors 2^3 * 3 * 5 * 7 and phi(840) = 192",
    ),
    EvalTask(
        id="math_03",
        category="Math Reasoning",
        name="Knapsack Dynamic Optimization",
        prompt="Solve 0/1 knapsack with capacity 15 kg and 5 items: (w:3, v:25), (w:4, v:32), (w:6, v:45), (w:5, v:40), (w:2, v:18).",
        expected_tools=["code_runner", "calculator"],
        success_criteria="Computes global maximum value = 115",
    ),
    EvalTask(
        id="math_04",
        category="Math Reasoning",
        name="Graph Shortest Path Dijkstra",
        prompt="Find shortest path from Node A to Node F with edge weights: A-B:4, A-C:2, B-C:1, B-D:5, C-E:8, D-F:3, E-F:2.",
        expected_tools=["code_runner"],
        success_criteria="Calculates minimum distance = 11",
    ),
    EvalTask(
        id="math_05",
        category="Math Reasoning",
        name="Convex Hull Perimeter",
        prompt="Compute perimeter of convex hull enclosing 2D points: (0,0), (4,0), (4,3), (0,3), (2,2), (1,1).",
        expected_tools=["calculator"],
        success_criteria="Calculates perimeter = 14.0",
    ),

    # ---------------- Category 3: Web Research & Multi-Source Synthesis ----------------
    EvalTask(
        id="research_01",
        category="Research Synthesis",
        name="Database Replication Consensus Protocols",
        prompt="Search and compare Raft vs Multi-Paxos consensus protocols in edge distributed databases.",
        expected_tools=["web_search"],
        success_criteria="Synthesizes leader election and log compaction trade-offs",
    ),
    EvalTask(
        id="research_02",
        category="Research Synthesis",
        name="Edge Computing IoT Gateway Latency",
        prompt="Investigate edge machine latency constraints when buffering telemetry under intermittent WAN.",
        expected_tools=["web_search"],
        success_criteria="Details queue overflow, durability, and store-and-forward architectures",
    ),
    EvalTask(
        id="research_03",
        category="Research Synthesis",
        name="Rollup Security Trade-offs",
        prompt="Evaluate optimistic rollups with fraud proofs vs zero-knowledge validity rollups.",
        expected_tools=["web_search"],
        success_criteria="Analyzes finality window vs proof generation computational costs",
    ),
    EvalTask(
        id="research_04",
        category="Research Synthesis",
        name="Prompt Caching & KV Cache Invariants",
        prompt="Investigate how prompt caching cuts token spend and latency in LLM agent runtimes.",
        expected_tools=["web_search"],
        success_criteria="Identifies prefix alignment, hash matching, and 40%+ token reduction",
    ),
    EvalTask(
        id="research_05",
        category="Research Synthesis",
        name="Raft Invariants Under Network Partitions",
        prompt="Synthesize split-brain prevention mechanisms when a 5-node Raft cluster divides 3/2.",
        expected_tools=["web_search"],
        success_criteria="Explains majority quorum rule preventing 2-node partition from committing",
    ),

    # ---------------- Category 4: Structured Data Extraction & Schema Validation ----------------
    EvalTask(
        id="extract_01",
        category="Data Extraction",
        name="Unstructured Invoice Line-Item Extraction",
        prompt="Extract subtotal, tax rate, and line items from raw text invoice into a validated JSON schema.",
        expected_tools=["code_runner", "memory_store"],
        success_criteria="Generates valid structured JSON with arithmetic consistency",
    ),
    EvalTask(
        id="extract_02",
        category="Data Extraction",
        name="Syslog to OpenTelemetry Event Schema",
        prompt="Parse raw Apache and Nginx access logs into OpenTelemetry structured attributes.",
        expected_tools=["code_runner"],
        success_criteria="Extracts timestamp, client_ip, method, uri, status_code, and user_agent",
    ),
    EvalTask(
        id="extract_03",
        category="Data Extraction",
        name="Polymorphic Address Normalization",
        prompt="Normalize international street addresses across USA, UK, and Japan formats.",
        expected_tools=["code_runner"],
        success_criteria="Maps fields to standard ISO recipient, line1, city, postal_code, country",
    ),
    EvalTask(
        id="extract_04",
        category="Data Extraction",
        name="Resume Entity Extraction",
        prompt="Extract candidate skills, years of experience, and degrees from candidate resume text.",
        expected_tools=["memory_store"],
        success_criteria="Extracts structured technical skills array and degrees list",
    ),
    EvalTask(
        id="extract_05",
        category="Data Extraction",
        name="Nested XML Config to JSON Tree",
        prompt="Transform deeply nested XML configuration with attributes into typed JSON structure.",
        expected_tools=["code_runner"],
        success_criteria="Preserves node hierarchy and converts attributes to JSON properties",
    ),

    # ---------------- Category 5: Tool Calling & API Orchestration ----------------
    EvalTask(
        id="tool_01",
        category="Tool Orchestration",
        name="ETL Pipeline with Outlier Rejection",
        prompt="Fetch numerical series, compute median and 3-sigma outliers using code runner, and store clean set in memory.",
        expected_tools=["code_runner", "memory_store"],
        success_criteria="Computes statistics and stores filtered records",
    ),
    EvalTask(
        id="tool_02",
        category="Tool Orchestration",
        name="Multi-Currency Tax Settlement Chain",
        prompt="Convert EUR 4,500 to USD at 1.085 rate, calculate 8.25% state tax using calculator, and store ledger record.",
        expected_tools=["calculator", "memory_store"],
        success_criteria="Computes correct net USD total and records ledger checkpoint",
    ),
    EvalTask(
        id="tool_03",
        category="Tool Orchestration",
        name="Database Query with Fallback Store",
        prompt="Perform key lookup for customer account; if primary key is missing, query by secondary index.",
        expected_tools=["memory_store"],
        success_criteria="Successfully resolves record through secondary key lookup",
    ),
    EvalTask(
        id="tool_04",
        category="Tool Orchestration",
        name="Safe Sandboxed Matrix Multiplication",
        prompt="Execute 3x3 matrix multiplication via sandboxed code runner tool.",
        expected_tools=["code_runner"],
        success_criteria="Outputs exact dot product result matrix",
    ),
    EvalTask(
        id="tool_05",
        category="Tool Orchestration",
        name="Distributed Agent Scratchpad Synchronization",
        prompt="Store intermediate sub-results into memory scratchpad across 3 sequential dependent steps.",
        expected_tools=["memory_store"],
        success_criteria="All 3 state keys accessible in memory store",
    ),

    # ---------------- Category 6: Failure Recovery & Dynamic Replanning ----------------
    EvalTask(
        id="recovery_01",
        category="Failure Recovery",
        name="Upstream 503 Timeout Exponential Backoff",
        prompt="Call flaky service that fails once with 503 timeout; recover via automatic retry backoff without restart.",
        expected_tools=["flaky_tool"],
        success_criteria="Recovers on second attempt and marks step RECOVERED",
    ),
    EvalTask(
        id="recovery_02",
        category="Failure Recovery",
        name="Intermittent Network Socket Disconnect",
        prompt="Handle socket disconnect on attempt 1, successfully completing on attempt 2.",
        expected_tools=["flaky_tool"],
        success_criteria="Completes without task failure",
    ),
    EvalTask(
        id="recovery_03",
        category="Failure Recovery",
        name="Primary Search Endpoint Fallback",
        prompt="When primary web search tool fails, automatically invoke registered fallback knowledge store.",
        expected_tools=["web_search"],
        success_criteria="Fallback tool executed and verified",
    ),
    EvalTask(
        id="recovery_04",
        category="Failure Recovery",
        name="Tool Parameter Auto-Correction",
        prompt="Recover from malformed input schema by inspecting error feedback and retrying with valid arguments.",
        expected_tools=["calculator"],
        success_criteria="Successfully recovers and executes valid calculation",
    ),
    EvalTask(
        id="recovery_05",
        category="Failure Recovery",
        name="Dynamic Plan Rewrite on Hard Failure",
        prompt="When critical tool fails permanently, trigger Tier 3 replanner to rewrite remaining steps without restarting completed work.",
        expected_tools=["flaky_tool", "memory_store"],
        success_criteria="Replanner rewrites remaining steps, retains completed step, and finishes task",
    ),

    # ---------------- Category 7: Durable Checkpoint Resumption ----------------
    EvalTask(
        id="durable_01",
        category="Durable Checkpoints",
        name="Mid-Run Crash at Step 2 Resumption",
        prompt="Simulate process termination after step 2; resume task from Redis checkpoint to execute step 3 without repeating steps 1-2.",
        expected_tools=["memory_store"],
        success_criteria="Completed steps 1-2 skipped, step 3 finishes, task marked COMPLETED",
    ),
    EvalTask(
        id="durable_02",
        category="Durable Checkpoints",
        name="SIGKILL Simulation During Pipeline",
        prompt="Restore long pipeline state from durable checkpoint after simulated hard shutdown.",
        expected_tools=["calculator", "memory_store"],
        success_criteria="State perfectly restored from Redis without data loss",
    ),
    EvalTask(
        id="durable_03",
        category="Durable Checkpoints",
        name="Batch Processing Offset Resumption",
        prompt="Resume processing a 1,000-item batch from exact checkpoint index 450 after worker interruption.",
        expected_tools=["memory_store"],
        success_criteria="Execution continues from offset 450",
    ),
    EvalTask(
        id="durable_04",
        category="Durable Checkpoints",
        name="Memory Scratchpad State Restoration",
        prompt="Verify all intermediate keys in agent memory are intact upon restoring from checkpoint.",
        expected_tools=["memory_store"],
        success_criteria="Prior keys retrieved accurately from restored context",
    ),
    EvalTask(
        id="durable_05",
        category="Durable Checkpoints",
        name="Token Telemetry Reconciliation",
        prompt="Verify token usage accumulators and prompt cache savings carry over seamlessly across resumes.",
        expected_tools=["memory_store"],
        success_criteria="Cumulative token counts match aggregate total across run segments",
    ),

    # ---------------- Category 8: Long-Horizon Workflow & Decomposition ----------------
    EvalTask(
        id="horizon_01",
        category="Long-Horizon Workflows",
        name="Multi-Stage Architecture Document",
        prompt="Plan and orchestrate 4-stage technical document: context search, calculation, drafting, and final memory save.",
        expected_tools=["web_search", "calculator", "memory_store"],
        success_criteria="All 4 stages executed in correct DAG sequence",
    ),
    EvalTask(
        id="horizon_02",
        category="Long-Horizon Workflows",
        name="Competitive Feature Matrix Synthesis",
        prompt="Extract 5 product feature sets, compute comparison score, and generate comprehensive summary.",
        expected_tools=["web_search", "code_runner", "memory_store"],
        success_criteria="Multi-step synthesis produced with structured score",
    ),
    EvalTask(
        id="horizon_03",
        category="Long-Horizon Workflows",
        name="CI/CD Build Failure Diagnosis & Fix",
        prompt="Analyze pipeline failure logs, verify source code fix in sandbox, and generate remediation commit plan.",
        expected_tools=["code_runner", "memory_store"],
        success_criteria="Remediation steps generated and verified",
    ),
    EvalTask(
        id="horizon_04",
        category="Long-Horizon Workflows",
        name="Database Migration Integrity Verification",
        prompt="Verify record count checksums across source and target tables, calculating row drift percentage.",
        expected_tools=["calculator", "code_runner"],
        success_criteria="Computes zero-drift status accurately",
    ),
    EvalTask(
        id="horizon_05",
        category="Long-Horizon Workflows",
        name="Incident Postmortem Timeline Reconstruction",
        prompt="Assemble incident event stream into chronologically ordered timeline with root cause diagnosis.",
        expected_tools=["memory_store", "web_search"],
        success_criteria="Chronological timeline synthesized and stored",
    ),
]
