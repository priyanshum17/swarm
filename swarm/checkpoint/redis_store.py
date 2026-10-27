"""Redis-backed durable storage with automatic in-memory fallback."""

from __future__ import annotations
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import redis.asyncio as aioredis
from swarm.checkpoint.models import TaskCheckpoint

logger = logging.getLogger("swarm.checkpoint.redis")


class CheckpointStoreInterface(ABC):
    """Abstract interface for checkpoint persistence."""

    @abstractmethod
    async def save(self, checkpoint: TaskCheckpoint) -> None:
        """Persist a task checkpoint."""
        pass

    @abstractmethod
    async def load(self, task_id: str) -> Optional[TaskCheckpoint]:
        """Load the latest checkpoint for a task."""
        pass

    @abstractmethod
    async def delete(self, task_id: str) -> bool:
        """Delete task checkpoint."""
        pass

    @abstractmethod
    async def list_tasks(self, limit: int = 50) -> List[str]:
        """List active/persisted task IDs."""
        pass

    @abstractmethod
    async def ping(self) -> bool:
        """Check if backend is healthy."""
        pass


class MemoryCheckpointStore(CheckpointStoreInterface):
    """Thread-safe in-memory store for unit tests or standalone mode."""

    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    async def save(self, checkpoint: TaskCheckpoint) -> None:
        self._store[checkpoint.task_id] = checkpoint.model_dump_json()

    async def load(self, task_id: str) -> Optional[TaskCheckpoint]:
        data = self._store.get(task_id)
        if not data:
            return None
        return TaskCheckpoint.model_validate_json(data)

    async def delete(self, task_id: str) -> bool:
        return self._store.pop(task_id, None) is not None

    async def list_tasks(self, limit: int = 50) -> List[str]:
        return list(self._store.keys())[:limit]

    async def ping(self) -> bool:
        return True


class RedisCheckpointStore(CheckpointStoreInterface):
    """Production Redis checkpoint store utilizing async pipelines for <1ms durability."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        ttl_seconds: int = 86400,
        prefix: str = "swarm:checkpoint:",
    ) -> None:
        self.redis_url = redis_url
        self.ttl = ttl_seconds
        self.prefix = prefix
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
        return self._client

    def _key(self, task_id: str) -> str:
        return f"{self.prefix}{task_id}"

    async def ping(self) -> bool:
        try:
            client = await self._get_client()
            return await client.ping()
        except Exception:
            return False

    async def save(self, checkpoint: TaskCheckpoint) -> None:
        client = await self._get_client()
        key = self._key(checkpoint.task_id)
        payload = checkpoint.model_dump_json()
        async with client.pipeline(transaction=True) as pipe:
            pipe.set(key, payload, ex=self.ttl)
            pipe.sadd(f"{self.prefix}index", checkpoint.task_id)
            await pipe.execute()

    async def load(self, task_id: str) -> Optional[TaskCheckpoint]:
        client = await self._get_client()
        raw = await client.get(self._key(task_id))
        if not raw:
            return None
        return TaskCheckpoint.model_validate_json(raw)

    async def delete(self, task_id: str) -> bool:
        client = await self._get_client()
        async with client.pipeline(transaction=True) as pipe:
            pipe.delete(self._key(task_id))
            pipe.srem(f"{self.prefix}index", task_id)
            results = await pipe.execute()
        return bool(results[0])

    async def list_tasks(self, limit: int = 50) -> List[str]:
        client = await self._get_client()
        members = await client.smembers(f"{self.prefix}index")
        return list(members)[:limit]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


_global_store: Optional[CheckpointStoreInterface] = None


async def get_checkpoint_store(
    redis_url: Optional[str] = None, force_memory: bool = False
) -> CheckpointStoreInterface:
    """Returns an active checkpoint store, falling back to in-memory if Redis is unreachable."""
    global _global_store
    if _global_store is not None:
        return _global_store

    if force_memory or not redis_url:
        logger.info("Using in-memory checkpoint store.")
        _global_store = MemoryCheckpointStore()
        return _global_store

    store = RedisCheckpointStore(redis_url=redis_url)
    if await store.ping():
        logger.info(f"Connected to Redis checkpoint store at {redis_url}")
        _global_store = store
        return store

    logger.warning("Redis unavailable at %s. Falling back to in-memory checkpoint store.", redis_url)
    _global_store = MemoryCheckpointStore()
    return _global_store
