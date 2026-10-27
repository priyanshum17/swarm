"""FastAPI application entrypoint and Swarm CLI commands."""

from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from swarm.api.routes import router as api_router
from swarm.checkpoint.redis_store import get_checkpoint_store
from swarm.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("swarm")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle management."""
    logger.info(f"Starting {settings.app_name} v{settings.version}...")
    store = await get_checkpoint_store(settings.redis_url)
    redis_alive = await store.ping()
    if redis_alive:
        logger.info(f"Connected to Redis at {settings.redis_url}")
    else:
        logger.warning(f"Could not reach Redis at {settings.redis_url}; running with fast in-memory checkpoint store.")
    yield
    logger.info("Swarm agent runtime shutting down.")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Fast, resilient agent runtime with Redis-backed durable execution, prompt caching, and multi-step recovery.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    return app


app = create_app()


def cli() -> None:
    """Swarm CLI runner."""
    parser = argparse.ArgumentParser(description="Swarm Agent Runtime CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: serve
    serve_parser = subparsers.add_parser("serve", help="Run the FastAPI application server")
    serve_parser.add_argument("--host", default=settings.host, help="Host address")
    serve_parser.add_argument("--port", type=int, default=settings.port, help="Port")
    serve_parser.add_argument("--reload", action="store_true", help="Enable live code reload")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run a multi-step agent task from the terminal")
    run_parser.add_argument("goal", help="Task prompt or goal")

    # Command: eval
    eval_parser = subparsers.add_parser("eval", help="Run the 40-task benchmark evaluation harness")
    eval_parser.add_argument("--concurrency", type=int, default=4, help="Evaluation concurrency")
    eval_parser.add_argument("--markdown", action="store_true", help="Print report as Markdown")

    # Command: resume
    resume_parser = subparsers.add_parser("resume", help="Resume interrupted task from checkpoint")
    resume_parser.add_argument("task_id", help="Task ID to resume")

    args = parser.parse_args()

    if args.command == "serve":
        uvicorn.run("swarm.main:app", host=args.host, port=args.port, reload=args.reload)
    elif args.command == "run":
        from swarm.runtime.agent import SwarmAgent
        agent = SwarmAgent()
        result = asyncio.run(agent.run(goal=args.goal))
        print(f"\n[Task {result.task_id}] Status: {result.status.value}")
        if result.plan:
            for s in result.plan.steps:
                print(f"  [{s.status.value.upper()}] {s.id}: {s.description} -> {s.output or s.error}")
        snap = result.tokens
        print(f"\nTokens: {snap.total_tokens} (Raw: {snap.prompt_tokens}, Cached: {snap.cached_prompt_tokens}, Cut: {snap.cache_savings_pct}%)")
    elif args.command == "eval":
        from swarm.evals.runner import EvalHarness
        from swarm.evals.reporter import EvalReporter
        harness = EvalHarness()
        report = asyncio.run(harness.run_benchmark(concurrency=args.concurrency))
        if args.markdown:
            print(EvalReporter.to_markdown(report))
        else:
            EvalReporter.print_console_summary(report)
    elif args.command == "resume":
        from swarm.runtime.agent import SwarmAgent
        agent = SwarmAgent()
        result = asyncio.run(agent.resume_task(task_id=args.task_id))
        if result:
            print(f"\n[Task {result.task_id}] Resumed and concluded with Status: {result.status.value}")
        else:
            print(f"Failed to resume task {args.task_id}")
    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
