from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .errors import ConfigError

# provider -> (default base_url, api-key env var, key required)
PROVIDERS: dict[str, tuple[str | None, str | None, bool]] = {
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", True),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", True),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", True),
    "ollama": ("http://localhost:11434/v1", None, False),
    "openai-compatible": (None, "OPENAI_COMPATIBLE_API_KEY", False),
}

PROVIDER_BASE_URL_ENV = {
    "openrouter": "OPENROUTER_BASE_URL",
    "nvidia": "NVIDIA_BASE_URL",
    "openai": "OPENAI_BASE_URL",
    "ollama": "OLLAMA_BASE_URL",
    "openai-compatible": "OPENAI_COMPATIBLE_BASE_URL",
}

MODES = ("plan", "ask", "auto_edit", "auto")


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError as exc:
        raise ConfigError(f"Expected an integer, got {value!r}") from exc


def _float(value: str | None, default: float) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except ValueError as exc:
        raise ConfigError(f"Expected a number, got {value!r}") from exc


def _list(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser (KEY=VALUE, quotes, comments). No dependency on python-dotenv."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in {'"', "'"} and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        values[key.strip()] = value
    return values


def load_env_files(cwd: Path | None = None, environ: dict[str, str] | None = None) -> None:
    """Load .env from cwd and ~/.rx without overriding variables that are already set."""
    env = os.environ if environ is None else environ
    cwd = cwd or Path.cwd()
    home = Path(env.get("RX_HOME", Path.home() / ".rx"))
    for candidate in (cwd / ".env", home / ".env"):
        for key, value in parse_env_file(candidate).items():
            env.setdefault(key, value)


@dataclass
class Settings:
    # --- model ---
    provider: str = "openrouter"
    model: str = "openrouter/free"
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    context_window: int = 128_000
    stream: bool = True
    llm_timeout: float = 120.0
    llm_retries: int = 5
    # --- behaviour ---
    mode: str = "ask"
    max_iterations: int = 60
    max_verify_nudges: int = 2
    max_verify_failures: int = 8
    prune_keep_turns: int = 6       # tool inputs/outputs older than this many assistant turns are compressed (0 = off)
    max_run_tokens: int = 400_000   # per-run token budget; the run ends with a report when exceeded (0 = off)
    max_run_seconds: int = 1800     # per-run ACTIVE time budget; time spent waiting for approvals is excluded (0 = off)
    command_timeout: int = 120
    max_output_chars: int = 30_000
    # --- sandbox ---
    sandbox: str = "auto"  # auto | bwrap | docker | local
    sandbox_network: bool = False
    docker_image: str = "python:3.12-slim"
    ro_paths: list[str] = field(default_factory=list)
    env_passthrough: list[str] = field(default_factory=list)
    allow_unsandboxed_auto: bool = False
    # --- state ---
    data_dir: Path = field(default_factory=lambda: Path.home() / ".rx")
    snapshots: bool = True

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        provider = (env.get("RX_PROVIDER") or env.get("MODEL_PROVIDER") or "openrouter").strip().lower()
        if provider not in PROVIDERS:
            raise ConfigError(f"Unsupported provider {provider!r}. Choose one of: {', '.join(sorted(PROVIDERS))}")
        default_url, key_env, _ = PROVIDERS[provider]
        base_url = env.get("RX_BASE_URL") or env.get(PROVIDER_BASE_URL_ENV[provider]) or default_url
        api_key = env.get("RX_API_KEY") or (env.get(key_env) if key_env else None)
        mode = (env.get("RX_MODE") or "ask").strip().lower().replace("-", "_")
        if mode not in MODES:
            raise ConfigError(f"Invalid RX_MODE {mode!r}. Choose one of: {', '.join(MODES)}")
        max_tokens = env.get("RX_MAX_TOKENS")
        return cls(
            provider=provider,
            model=(env.get("RX_MODEL") or env.get("CODING_AGENT_MODEL") or "openrouter/free").strip(),
            api_key=api_key,
            base_url=base_url,
            temperature=_float(env.get("RX_TEMPERATURE"), 0.0),
            max_tokens=_int(max_tokens, 0) or None,
            context_window=_int(env.get("RX_CONTEXT_WINDOW"), 128_000),
            stream=_bool(env.get("RX_STREAM"), True),
            llm_timeout=_float(env.get("RX_LLM_TIMEOUT"), 120.0),
            llm_retries=_int(env.get("RX_LLM_RETRIES"), 5),
            mode=mode,
            max_iterations=_int(env.get("RX_MAX_ITERATIONS"), 60),
            max_verify_nudges=_int(env.get("RX_MAX_VERIFY_NUDGES"), 2),
            max_verify_failures=_int(env.get("RX_MAX_VERIFY_FAILURES"), 8),
            prune_keep_turns=_int(env.get("RX_PRUNE_KEEP_TURNS"), 6),
            max_run_tokens=_int(env.get("RX_MAX_RUN_TOKENS"), 400_000),
            max_run_seconds=_int(env.get("RX_MAX_RUN_SECONDS"), 1800),
            command_timeout=_int(env.get("RX_COMMAND_TIMEOUT"), 120),
            max_output_chars=_int(env.get("RX_MAX_OUTPUT_CHARS"), 30_000),
            sandbox=(env.get("RX_SANDBOX") or "auto").strip().lower(),
            sandbox_network=_bool(env.get("RX_SANDBOX_NETWORK"), False),
            docker_image=env.get("RX_DOCKER_IMAGE") or "python:3.12-slim",
            ro_paths=_list(env.get("RX_SANDBOX_RO_PATHS")),
            env_passthrough=_list(env.get("RX_ENV_PASSTHROUGH")),
            allow_unsandboxed_auto=_bool(env.get("RX_ALLOW_UNSANDBOXED_AUTO"), False),
            data_dir=Path(env.get("RX_HOME") or (Path.home() / ".rx")).expanduser(),
            snapshots=_bool(env.get("RX_SNAPSHOTS"), True),
        )
