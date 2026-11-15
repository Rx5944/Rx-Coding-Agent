from __future__ import annotations

import asyncio
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rx_agent.errors import LLMError
from rx_agent.llm.openai_compat import OpenAICompatClient, StreamAccumulator, parse_full_response
from rx_agent.llm.retry import retry_async

from .helpers import run


class AccumulatorTests(unittest.TestCase):
    def test_text_and_fragmented_tool_calls(self):
        acc = StreamAccumulator()
        out = []
        chunks = [
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "read_file", "arguments": '{"pa'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'th": "a.py"}'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 1, "id": "c2", "function": {"name": "glob", "arguments": "{}"}}]}}]},
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
        ]
        for c in chunks:
            out.append(acc.feed(c))
        r = acc.result()
        self.assertEqual("".join(out), "Hello")
        self.assertEqual([(c.id, c.name, c.arguments) for c in r.tool_calls],
                         [("c1", "read_file", '{"path": "a.py"}'), ("c2", "glob", "{}")])
        self.assertEqual(r.usage.total_tokens, 15)
        self.assertEqual(r.finish_reason, "tool_calls")

    def test_missing_ids_are_generated_and_nameless_calls_dropped(self):
        acc = StreamAccumulator()
        acc.feed({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "x", "arguments": ""}}, {"index": 1, "function": {"arguments": "{}"}}]}}]})
        calls = acc.result().tool_calls
        self.assertEqual([(c.id, c.name, c.arguments) for c in calls], [("call_0", "x", "{}")])

    def test_midstream_error_is_retryable_for_5xx(self):
        with self.assertRaises(LLMError) as cm:
            StreamAccumulator().feed({"error": {"message": "overloaded", "code": 503}})
        self.assertTrue(cm.exception.retryable)

    def test_non_stream_body(self):
        r = parse_full_response({"choices": [{"message": {"content": "hi", "tool_calls": [
            {"id": "a", "function": {"name": "t", "arguments": "{}"}}]}, "finish_reason": "stop"}], "usage": {"total_tokens": 3}})
        self.assertEqual((r.content, r.tool_calls[0].name, r.usage.total_tokens), ("hi", "t", 3))


class RetryTests(unittest.TestCase):
    def test_retries_then_succeeds_and_honours_retry_after(self):
        calls, delays = [], []

        async def fn():
            calls.append(1)
            if len(calls) < 3:
                raise LLMError("rate", status=429, retryable=True, retry_after=7)
            return "ok"

        async def fake_sleep(d):
            delays.append(d)

        self.assertEqual(run(retry_async(fn, attempts=5, sleep=fake_sleep)), "ok")
        self.assertEqual(delays, [7, 7])

    def test_non_retryable_raises_immediately(self):
        async def fn():
            raise LLMError("bad key", status=401, retryable=False)

        with self.assertRaises(LLMError):
            run(retry_async(fn, attempts=5, sleep=lambda d: asyncio.sleep(0)))

    def test_gives_up_after_attempts(self):
        n = []

        async def fn():
            n.append(1)
            raise LLMError("down", status=503, retryable=True)

        with self.assertRaises(LLMError):
            run(retry_async(fn, attempts=3, sleep=lambda d: asyncio.sleep(0)))
        self.assertEqual(len(n), 3)


class FakeServer:
    """A real local HTTP server that speaks OpenAI-style SSE, so the stdlib client is tested end to end."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"body": body, "auth": self.headers.get("Authorization")})
                outer.script.pop(0)(self)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        self.release = threading.Event()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.release.set()
        self.httpd.shutdown()
        self.httpd.server_close()


def sse(handler, chunks, pause=None):
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.end_headers()
    for c in chunks:
        handler.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
        handler.wfile.flush()
        if pause:
            pause()
    handler.wfile.write(b"data: [DONE]\n\n")
    handler.wfile.flush()


def error(handler, code, body="{}", headers=None):
    handler.send_response(code)
    for k, v in (headers or {}).items():
        handler.send_header(k, v)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body.encode())


class HttpClientTests(unittest.TestCase):
    def make(self, script, **kw):
        server = FakeServer(script)
        self.addCleanup(server.close)
        return server, OpenAICompatClient("m", "sk-test", server.url, retries=kw.pop("retries", 3), timeout=5, **kw)

    def test_streams_text_and_tool_calls(self):
        chunks = [{"choices": [{"delta": {"content": "Hi "}}]}, {"choices": [{"delta": {"content": "there"}}]},
                  {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "t1", "function": {"name": "glob", "arguments": "{\"pattern\":\"*\"}"}}]}}]},
                  {"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}}]
        server, client = self.make([lambda h: sse(h, chunks)])
        seen = []
        r = run(client.complete([{"role": "user", "content": "x"}], [{"type": "function"}], on_text=seen.append))
        self.assertEqual(seen, ["Hi ", "there"])
        self.assertEqual((r.content, r.tool_calls[0].name, r.usage.total_tokens), ("Hi there", "glob", 6))
        req = server.requests[0]
        self.assertEqual(req["auth"], "Bearer sk-test")
        self.assertTrue(req["body"]["stream"])
        self.assertEqual(req["body"]["stream_options"], {"include_usage": True})

    def test_retries_429_with_retry_after_then_succeeds(self):
        ok = [{"choices": [{"delta": {"content": "done"}}]}]
        server, client = self.make([lambda h: error(h, 429, "{}", {"Retry-After": "0"}), lambda h: sse(h, ok)])
        retries = []
        r = run(client.complete([{"role": "user", "content": "x"}], on_retry=lambda **kw: retries.append(kw)))
        self.assertEqual(r.content, "done")
        self.assertEqual(len(retries), 1)

    def test_auth_error_is_not_retried(self):
        server, client = self.make([lambda h: error(h, 401, '{"error":"bad key"}')])
        with self.assertRaises(LLMError) as cm:
            run(client.complete([{"role": "user", "content": "x"}]))
        self.assertEqual(cm.exception.status, 401)
        self.assertEqual(len(server.requests), 1)

    def test_falls_back_when_provider_rejects_stream_options(self):
        ok = [{"choices": [{"delta": {"content": "fine"}}]}]
        server, client = self.make([lambda h: error(h, 400, '{"error":"unknown field stream_options"}'), lambda h: sse(h, ok)])
        self.assertEqual(run(client.complete([{"role": "user", "content": "x"}])).content, "fine")
        self.assertNotIn("stream_options", server.requests[1]["body"])

    def test_non_streaming_json_response(self):
        def plain(h):
            body = json.dumps({"choices": [{"message": {"content": "plain"}}]})
            h.send_response(200)
            h.send_header("Content-Type", "application/json")
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body.encode())

        server, client = self.make([plain])
        self.assertEqual(run(client.complete([{"role": "user", "content": "x"}])).content, "plain")

    def test_cancellation_aborts_a_hanging_stream_quickly(self):
        holder = {}

        def hang(h):
            h.send_response(200)
            h.send_header("Content-Type", "text/event-stream")
            h.end_headers()
            h.wfile.write(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')
            h.wfile.flush()
            holder["server"].release.wait(20)

        server, client = self.make([hang])
        holder["server"] = server

        async def go():
            got = []
            task = asyncio.create_task(client.complete([{"role": "user", "content": "x"}], on_text=got.append))
            for _ in range(50):
                if got:
                    break
                await asyncio.sleep(0.05)
            started = time.time()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            return time.time() - started

        self.assertLess(run(go()), 2)

    def test_unreachable_server_is_retryable_error(self):
        client = OpenAICompatClient("m", None, "http://127.0.0.1:9/v1", retries=1, timeout=2)
        with self.assertRaises(LLMError) as cm:
            run(client.complete([{"role": "user", "content": "x"}]))
        self.assertTrue(cm.exception.retryable)


class FriendlyErrorTests(unittest.TestCase):
    def test_provider_message_and_actionable_hint(self):
        from rx_agent.llm.openai_compat import describe_http_error

        msg = describe_http_error(401, '{"error":{"message":"No auth credentials found","code":401}}')
        self.assertIn("No auth credentials found", msg)
        self.assertIn("API key was rejected", msg)
        self.assertIn("402", describe_http_error(402, "{}"))
        self.assertIn("out of credits", describe_http_error(402, "{}"))
        self.assertIn("not found", describe_http_error(404, "plain text body"))
        self.assertIn("plain text body", describe_http_error(404, "plain text body"))
        self.assertIn("server-side", describe_http_error(502, ""))
        nested = describe_http_error(400, '{"error":{"message":"Provider returned error","metadata":{"raw":"model does not support tools"}}}')
        self.assertIn("does not support tools", nested)

    def test_real_401_surfaces_the_hint_to_the_caller(self):
        server = FakeServer([lambda h: error(h, 401, '{"error":{"message":"bad key"}}')])
        self.addCleanup(server.close)
        client = OpenAICompatClient("m", "x", server.url, retries=5, timeout=5)
        with self.assertRaises(LLMError) as cm:
            run(client.complete([{"role": "user", "content": "x"}]))
        self.assertIn("restart `rx serve`", str(cm.exception))
        self.assertEqual(len(server.requests), 1)  # auth errors are not retried
