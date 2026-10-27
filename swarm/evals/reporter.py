"""Reporting and visualization of benchmark evaluation results."""

from __future__ import annotations
import json
from typing import Any, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from swarm.evals.runner import EvalBenchmarkReport


class EvalReporter:
    """Formats benchmark evaluation results into rich tables or markdown."""

    @staticmethod
    def print_console_summary(report: EvalBenchmarkReport) -> None:
        """Render beautiful Rich terminal tables summarizing evaluation results."""
        console = Console()

        # Overall summary panel
        summary_text = (
            f"[bold green]Tasks Evaluated:[/] {report.total_tasks} | "
            f"[bold green]Passed:[/] {report.passed_tasks} ({report.accuracy_pct}%) | "
            f"[bold red]Failed:[/] {report.failed_tasks}\n"
            f"[bold cyan]Recovery Rate:[/] {report.recovery_rate_pct}% | "
            f"[bold yellow]Token Savings via Cache:[/] {report.token_savings_pct}% | "
            f"[bold magenta]Avg Latency:[/] {report.avg_latency_ms:.1f}ms"
        )
        console.print(Panel(summary_text, title="[bold white]Swarm Agent Eval Benchmark (40 Task Types)[/]", expand=False))

        # Category table
        cat_table = Table(title="Performance By Task Category", header_style="bold cyan")
        cat_table.add_column("Category", style="white")
        cat_table.add_column("Tasks", justify="right", style="cyan")
        cat_table.add_column("Passed", justify="right", style="green")
        cat_table.add_column("Pass Rate", justify="right", style="bold green")
        cat_table.add_column("Avg Latency", justify="right", style="yellow")

        for cat, stats in report.category_breakdown.items():
            cat_table.add_row(
                cat,
                str(stats["total"]),
                str(stats["passed"]),
                f"{stats['pass_rate_pct']}%",
                f"{stats['avg_duration_ms']}ms",
            )
        console.print(cat_table)

    @staticmethod
    def to_markdown(report: EvalBenchmarkReport) -> str:
        """Export report as Markdown for documentation or README inclusion."""
        lines = [
            "# Swarm Agent Benchmark Report (40 Task Types)",
            "",
            f"**Overall Accuracy:** {report.accuracy_pct}% ({report.passed_tasks}/{report.total_tasks} passed)  ",
            f"**Failure Recovery Rate:** {report.recovery_rate_pct}%  ",
            f"**Token Spend Cut (Prompt Caching):** {report.token_savings_pct}%  ",
            f"**Average Task Latency:** {report.avg_latency_ms:.1f}ms  ",
            "",
            "## Category Breakdown",
            "",
            "| Category | Total Tasks | Passed | Pass Rate | Avg Latency |",
            "| :--- | :---: | :---: | :---: | :---: |",
        ]

        for cat, stats in report.category_breakdown.items():
            lines.append(
                f"| {cat} | {stats['total']} | {stats['passed']} | {stats['pass_rate_pct']}% | {stats['avg_duration_ms']}ms |"
            )

        lines.extend([
            "",
            "## Detailed Task Log",
            "",
            "| Task ID | Name | Category | Result | Duration | Retries | Recovery |",
            "| :--- | :--- | :--- | :---: | :---: | :---: | :---: |",
        ])

        for t in report.task_results:
            status_icon = "✅ PASS" if t.passed else "❌ FAIL"
            rec_str = "Yes" if t.recovered else "No"
            lines.append(
                f"| `{t.task_id}` | {t.name} | {t.category} | {status_icon} | {t.duration_ms:.1f}ms | {t.retries_used} | {rec_str} |"
            )

        return "\n".join(lines)
