"""Configuration settings for Swarm Agent Runtime."""

from typing import Optional
import os
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Runtime configuration settings."""

    # Server Settings
    app_name: str = "Swarm Agent Runtime"
    version: str = "0.1.0"
    host: str = os.getenv("SWARM_HOST", "0.0.0.0")
    port: int = int(os.getenv("SWARM_PORT", "8000"))
    environment: str = os.getenv("SWARM_ENV", "development")

    # Redis Settings
    redis_url: Optional[str] = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_ttl_seconds: int = int(os.getenv("REDIS_TTL_SECONDS", "86400"))  # 24 hours
    redis_checkpoint_prefix: str = "swarm:checkpoint:"
    redis_cache_prefix: str = "swarm:cache:prompt:"

    # LLM Settings
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY", None)
    openai_base_url: Optional[str] = os.getenv("OPENAI_BASE_URL", None)
    default_model: str = os.getenv("SWARM_MODEL", "gpt-4o-mini")
    use_mock_llm: bool = os.getenv("SWARM_USE_MOCK_LLM", "false").lower() in ("true", "1", "yes")

    # Runtime & Execution Settings
    max_steps_per_task: int = int(os.getenv("SWARM_MAX_STEPS", "30"))
    max_step_retries: int = int(os.getenv("SWARM_MAX_STEP_RETRIES", "3"))
    retry_backoff_factor: float = float(os.getenv("SWARM_RETRY_BACKOFF", "0.5"))
    enable_prompt_caching: bool = os.getenv("SWARM_ENABLE_PROMPT_CACHING", "true").lower() in ("true", "1", "yes")
    max_parallel_steps: int = int(os.getenv("SWARM_MAX_PARALLEL_STEPS", "4"))
    step_timeout_seconds: float = float(os.getenv("SWARM_STEP_TIMEOUT", "30.0"))


settings = Settings()
