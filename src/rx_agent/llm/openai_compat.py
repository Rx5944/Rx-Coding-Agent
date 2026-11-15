"""Streaming client for any OpenAI-compatible /chat/completions endpoint (stdlib only)."""
from __future__ import annotations

import asyncio
import json
import socket
import threading
import urllib.error
import urllib.request
from typing import Any

from ..errors import LLMError
from .base import LLMClient, LLMResponse, RetryCallback, TextCallback, ToolCall, Usage
from .retry import retry_async

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


HTTP_HINTS = {
    400: "The provider rejected the request. Check RX_MODEL (does this model support tools?) and RX_PROVIDER.",
    401: "The API key was rejected. Check the key in .env (e.g. OPENROUTER_API_KEY), then restart `rx serve`.",
    402: "The provider says you are out of credits or over a spending limit.",
    403: "The provider refused this request (key lacks access to this model, a usage limit was hit, or content was moderated).",
    404: "Model or endpoint not found. Check RX_MODEL and the provider's base URL.",
    408: "The provider timed out.",
    413: "The request was too large for the model's context window. Lower RX_CONTEXT_WINDOW or start a New session.",
    429: "Rate limited (free models are heavily throttled). Wait a moment, or switch to another model.",
}


def describe_http_error(code: int, body: str) -> str:
    """One readable line: the provider's own message plus what to do about it."""
    detail = body.strip()[:500]
    try:
        data = json.loads(body)
        err = data.get("error", data) if isinstance(data, dict) else data
        if isinstance(err, dict):
            detail = str(err.get("message") or err)[:500]
            raw = err.get("metadata", {}).get("raw") if isinstance(err.get("metadata"), dict) else None
            if raw:
                detail += f" ({str(raw)[:200]})"
    except (json.JSONDecodeError, AttributeError):
        pass
    hint = HTTP_HINTS.get(code) or ("The provider had a server-side problem; retrying usually helps." if code >= 500 else "")
    return f"HTTP {code} from model API: {detail}" + (f"\n→ {hint}" if hint else "")


class StreamAccumulator:
    """Pure state machine that folds SSE chunks into one LLMResponse (unit-testable)."""

    def __init__(self) -> None:
        self.content: list[str] = []
        self.calls: dict[int, dict[str, str]] = {}
        self.finish_reason: str | None = None
        self.usage = Usage()
        self.model: str | None = None

    def feed(self, chunk: dict[str, Any]) -> str:
        """Consume one decoded chunk; return any new text delta."""
        if chunk.get("error"):
            err = chunk["error"]
            message = err.get("message") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else None
            status = code if isinstance(code, int) else None
            raise LLMError(f"Provider error mid-stream: {message}", status=status,
                           retryable=bool(status in RETRYABLE_STATUS))
        self.model = chunk.get("model") or self.model
        usage = chunk.get("usage")
        if isinstance(usage, dict):
            self.usage = Usage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            )
        choices = chunk.get("choices") or []
        if not choices:
            return ""
        choice = choices[0]
        if choice.get("finish_reason"):
            self.finish_reason = choice["finish_reason"]
        delta = choice.get("delta") or choice.get("message") or {}
        text = delta.get("content") or ""
        if isinstance(text, str) and text:
            self.content.append(text)
        else:
            text = ""
        for tc in delta.get("tool_calls") or []:
            index = tc.get("index", len(self.calls))
            slot = self.calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
            if tc.get("id") and not slot["id"]:
                slot["id"] = tc["id"]
            fn = tc.get("function") or {}
            if fn.get("name") and not slot["name"]:
                slot["name"] = fn["name"]
            if fn.get("arguments"):
                slot["arguments"] += fn["arguments"]
        return text

    def result(self) -> LLMResponse:
        calls = []
        for n, index in enumerate(sorted(self.calls)):
            slot = self.calls[index]
            if not slot["name"]:
                continue
            calls.append(ToolCall(slot["id"] or f"call_{n}", slot["name"], slot["arguments"] or "{}"))
        return LLMResponse("".join(self.content), calls, self.usage, self.finish_reason, self.model)


def parse_full_response(body: dict[str, Any]) -> LLMResponse:
    """Parse a non-streaming /chat/completions body."""
    if body.get("error"):
        err = body["error"]
        raise LLMError(f"Provider error: {err.get('message') if isinstance(err, dict) else err}\n"
                       "→ Check RX_MODEL / RX_PROVIDER, or run `rx doctor --ping`.")
    acc = StreamAccumulator()
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    acc.feed({
        "model": body.get("model"),
        "usage": body.get("usage"),
        "choices": [{
            "finish_reason": choice.get("finish_reason"),
            "delta": {
                "content": message.get("content"),
                "tool_calls": [{**tc, "index": i} for i, tc in enumerate(message.get("tool_calls") or [])],
            },
        }],
    })
    return acc.result()


class OpenAICompatClient(LLMClient):
    def __init__(
        self,
        model: str,
        api_key: str | None,
        base_url: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout: float = 120.0,
        stream: bool = True,
        retries: int = 5,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.stream = stream
        self.retries = retries
        self.extra_headers = extra_headers or {}
        self._stream_options = True

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        on_text: TextCallback | None = None,
        on_retry: RetryCallback | None = None,
    ) -> LLMResponse:
        return await retry_async(
            lambda: self._attempt(messages, tools, on_text),
            attempts=max(1, self.retries),
            on_retry=on_retry,
        )

    def _payload(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": self.stream,
        }
        if self.stream and self._stream_options:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = tools
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if self.stream else "application/json",
            "User-Agent": "rx-coding-agent/1.0",
            **self.extra_headers,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _attempt(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, on_text: TextCallback | None
    ) -> LLMResponse:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        stop = threading.Event()
        holder: dict[str, Any] = {}
        payload = self._payload(messages, tools)

        def push(kind: str, value: Any) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, value))

        def worker() -> None:
            try:
                push("done", self._blocking_request(payload, push, stop, holder))
            except BaseException as exc:  # noqa: BLE001 - forwarded to the awaiting coroutine
                push("error", exc)

        loop.run_in_executor(None, worker)
        try:
            while True:
                kind, value = await queue.get()
                if kind == "text":
                    if on_text:
                        on_text(value)
                elif kind == "done":
                    return value
                else:
                    raise value
        except asyncio.CancelledError:
            stop.set()
            # close() would block on the reader lock the worker thread holds; shutting the socket down
            # unblocks the worker's read immediately.
            sock = holder.get("sock")
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            raise

    def _blocking_request(self, payload: dict[str, Any], push, stop: threading.Event, holder: dict[str, Any]) -> LLMResponse:
        request = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"), headers=self._headers(), method="POST"
        )
        try:
            resp = urllib.request.urlopen(request, timeout=self.timeout)  # noqa: S310 - URL is user configured
        except urllib.error.HTTPError as exc:
            body = exc.read(4000).decode("utf-8", "replace")
            if exc.code == 400 and "stream_options" in body and self._stream_options:
                self._stream_options = False
                raise LLMError("provider rejected stream_options; retrying without", status=400,
                               retryable=True, retry_after=0.0) from exc
            retry_after = None
            raw = exc.headers.get("Retry-After") if exc.headers else None
            if raw:
                try:
                    retry_after = float(raw)
                except ValueError:
                    retry_after = None
            raise LLMError(describe_http_error(exc.code, body), status=exc.code,
                           retryable=exc.code in RETRYABLE_STATUS, retry_after=retry_after) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise LLMError(f"Could not reach model API: {exc}", retryable=True) from exc

        holder["resp"] = resp
        try:
            holder["sock"] = resp.fp.raw._sock  # type: ignore[attr-defined]
        except AttributeError:
            pass
        try:
            if stop.is_set():
                raise LLMError("cancelled")
            ctype = resp.headers.get("Content-Type", "")
            if "text/event-stream" not in ctype:
                body = json.loads(resp.read().decode("utf-8", "replace"))
                result = parse_full_response(body)
                if result.content:
                    push("text", result.content)
                return result
            acc = StreamAccumulator()
            for raw in resp:
                if stop.is_set():
                    raise LLMError("cancelled")
                line = raw.decode("utf-8", "replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                text = acc.feed(chunk)
                if text:
                    push("text", text)
            return acc.result()
        except (OSError, ValueError) as exc:
            if stop.is_set():
                raise LLMError("cancelled") from exc
            raise LLMError(f"Connection to model API dropped: {exc}", retryable=True) from exc
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
