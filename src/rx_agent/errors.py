from __future__ import annotations


class RXError(Exception):
    """Base class for all RX errors."""


class ToolError(RXError):
    """An expected, model-recoverable tool failure. The message is shown to the model."""


class ConfigError(RXError):
    """Invalid or missing configuration."""


class SandboxUnavailable(RXError):
    """The requested sandbox backend cannot be used on this machine."""


class LLMError(RXError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after
