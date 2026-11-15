from __future__ import annotations

from ..config import PROVIDERS, Settings
from ..errors import ConfigError
from .base import LLMClient
from .openai_compat import OpenAICompatClient


def create_llm(settings: Settings) -> LLMClient:
    provider = settings.provider
    if provider not in PROVIDERS:
        raise ConfigError(f"Unsupported provider {provider!r}")
    default_url, key_env, key_required = PROVIDERS[provider]
    base_url = settings.base_url or default_url
    if not base_url:
        raise ConfigError(f"{provider} requires a base URL (set OPENAI_COMPATIBLE_BASE_URL or RX_BASE_URL)")
    if key_required and not settings.api_key:
        raise ConfigError(f"{key_env} is required when provider={provider}. Put it in .env or the environment.")
    headers = {"X-Title": "RX Coding Agent"} if provider == "openrouter" else {}
    return OpenAICompatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=base_url,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.llm_timeout,
        stream=settings.stream,
        retries=settings.llm_retries,
        extra_headers=headers,
    )
