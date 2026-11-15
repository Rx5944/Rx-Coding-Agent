"""Keeps long sessions inside the model's context window without losing the thread."""
from __future__ import annotations

import json
import logging
from typing import Any

from ..config import Settings
from ..events import EventBus
from ..llm.base import LLMClient
from ..util import estimate_message_tokens, truncate_middle

log = logging.getLogger("rx.context")

PRUNE_NOTE = "\n[output pruned to save context; re-run the tool if you need it again]"
SUMMARY_SYSTEM = (
    "You compress the history of a coding-agent session so work can continue seamlessly. "
    "Be factual and specific; never invent details."
)
SUMMARY_PROMPT = """Summarize the session transcript below for the agent that will continue the work.
Use these sections (omit empty ones):
GOAL: what the user wants, including constraints and preferences they stated.
DONE: what has been accomplished, with exact file paths and function names.
FILE STATE: files created/modified/deleted and anything the agent must re-read before editing.
COMMANDS & RESULTS: important commands run, test results, errors seen (exact messages if short).
OPEN ISSUES: unresolved failures, hypotheses, things tried that did NOT work.
NEXT STEPS: what to do next.

<transcript>
{transcript}
</transcript>"""


BIG_ARG_KEYS = {"content", "old_text", "new_text", "patch"}
ARG_LIMIT = 400


def _shrink_arg(value: str, limit: int = ARG_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return f"[omitted {len(value):,} chars; this is already applied on disk, re-read the file if you need it]"


def _shrink_arguments(raw: str) -> str:
    """Replace big string arguments of an OLD tool call with a short note. Output stays valid JSON."""
    try:
        args = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if not isinstance(args, dict):
        return raw
    changed = False

    def shrink(d: dict) -> None:
        nonlocal changed
        for k, v in list(d.items()):
            if k in BIG_ARG_KEYS and isinstance(v, str) and len(v) > ARG_LIMIT:
                d[k], changed = _shrink_arg(v), True
            elif k == "command" and isinstance(v, str) and len(v) > 300:
                d[k], changed = v[:200] + f" …[{len(v) - 200:,} more chars omitted]", True
            elif k == "edits" and isinstance(v, list):
                for e in v:
                    if isinstance(e, dict):
                        shrink(e)

    shrink(args)
    return json.dumps(args) if changed else raw


class ContextManager:
    def __init__(self, settings: Settings, events: EventBus):
        self.settings = settings
        self.events = events
        self.calibration = 1.0  # real_tokens / estimated_tokens, learned from provider usage

    def estimate(self, messages: list[dict[str, Any]], fixed_tokens: int = 0) -> int:
        return int((sum(estimate_message_tokens(m) for m in messages) + fixed_tokens) * self.calibration)

    def observe(self, real_prompt_tokens: int, estimated_before_call: int) -> None:
        if real_prompt_tokens > 0 and estimated_before_call > 0:
            ratio = max(0.5, min(3.0, real_prompt_tokens / (estimated_before_call / self.calibration)))
            self.calibration = 0.7 * self.calibration + 0.3 * ratio

    @staticmethod
    def prune_tool_outputs(messages: list[dict[str, Any]], keep_recent: int = 8, min_len: int = 400) -> int:
        tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
        pruned = 0
        for i in tool_idx[: max(0, len(tool_idx) - keep_recent)]:
            content = messages[i].get("content") or ""
            if len(content) > min_len and not content.endswith(PRUNE_NOTE):
                messages[i] = {**messages[i], "content": content[:200] + PRUNE_NOTE}
                pruned += 1
        return pruned

    @staticmethod
    def age_prune(messages: list[dict[str, Any]], keep_turns: int = 6) -> int:
        """Cheap, deterministic, every-step compression of OLD history.

        Everything the agent wrote or read more than `keep_turns` assistant turns ago is dead weight: file bodies are
        on disk and can be re-read. Without this, each step re-sends every file ever written (quadratic cost).
        Idempotent; never changes message order or tool_call ids, so the transcript stays valid."""
        if keep_turns <= 0:
            return 0
        assistant_idx = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
        if len(assistant_idx) <= keep_turns:
            return 0
        boundary = assistant_idx[-keep_turns]
        changed = 0
        for i in range(boundary):
            m = messages[i]
            if m.get("role") == "assistant" and m.get("tool_calls"):
                new_calls = []
                touched = False
                for call in m["tool_calls"]:
                    fn = call.get("function", {})
                    shrunk = _shrink_arguments(fn.get("arguments", ""))
                    if shrunk != fn.get("arguments"):
                        touched = True
                        call = {**call, "function": {**fn, "arguments": shrunk}}
                    new_calls.append(call)
                if touched:
                    messages[i] = {**m, "tool_calls": new_calls}
                    changed += 1
            elif m.get("role") == "tool":
                content = m.get("content") or ""
                if len(content) > 700 and PRUNE_NOTE not in content:
                    messages[i] = {**m, "content": content[:350] + PRUNE_NOTE + content[-250:]}
                    changed += 1
        return changed

    @staticmethod
    def choose_cut(messages: list[dict[str, Any]], keep_tail_tokens: int) -> int:
        """Index where the preserved tail starts. Never a 'tool' message (that would orphan it)."""
        acc, cut = 0, len(messages)
        for i in range(len(messages) - 1, -1, -1):
            acc += estimate_message_tokens(messages[i])
            if acc > keep_tail_tokens:
                break
            if messages[i].get("role") != "tool":
                cut = i
        if cut >= len(messages):
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") != "tool":
                    return i
        return cut

    @staticmethod
    def render(messages: list[dict[str, Any]], limit: int = 60_000) -> str:
        lines: list[str] = []
        for m in messages:
            role = m.get("role")
            if role == "tool":
                lines.append(f"[tool result] {truncate_middle(m.get('content') or '', 1200)}")
            elif role == "assistant":
                if m.get("content"):
                    lines.append(f"[assistant] {truncate_middle(m['content'], 1500)}")
                for call in m.get("tool_calls") or []:
                    fn = call.get("function", {})
                    lines.append(f"[assistant called] {fn.get('name')}({truncate_middle(fn.get('arguments', ''), 400)})")
            else:
                lines.append(f"[{role}] {truncate_middle(str(m.get('content') or ''), 3000)}")
        return truncate_middle("\n".join(lines), limit)

    @staticmethod
    def fallback_summary(messages: list[dict[str, Any]]) -> str:
        first_user = next((str(m.get("content")) for m in messages if m.get("role") == "user"), "")
        calls = []
        for m in messages:
            for call in m.get("tool_calls") or []:
                fn = call.get("function", {})
                calls.append(f"- {fn.get('name')}({truncate_middle(fn.get('arguments', ''), 120)})")
        return (f"GOAL (original request): {truncate_middle(first_user, 2000)}\n"
                f"ACTIONS TAKEN (details elided, re-read files before editing):\n" + "\n".join(calls[-60:]))

    async def maybe_compact(self, session: Any, llm: LLMClient, fixed_tokens: int = 0) -> bool:
        window = self.settings.context_window
        limit = int(window * 0.75)
        messages: list[dict[str, Any]] = session.messages
        before = self.estimate(messages, fixed_tokens)
        if before <= limit:
            return False
        self.prune_tool_outputs(messages)
        if self.estimate(messages, fixed_tokens) <= limit:
            self.events.emit("context_compacted", before_tokens=before,
                             after_tokens=self.estimate(messages, fixed_tokens), method="prune")
            return True
        cut = self.choose_cut(messages, int(limit * 0.4))
        if cut <= 0:
            self.prune_tool_outputs(messages, keep_recent=2, min_len=200)
            return True
        head, tail = messages[:cut], messages[cut:]
        method = "summary"
        try:
            resp = await llm.complete(
                [{"role": "system", "content": SUMMARY_SYSTEM},
                 {"role": "user", "content": SUMMARY_PROMPT.format(transcript=self.render(head))}],
                None,
            )
            summary = resp.content.strip()
            if not summary:
                raise ValueError("empty summary")
        except Exception as exc:  # noqa: BLE001 - compaction must never kill the run
            log.warning("LLM summary failed (%s); using deterministic fallback", exc)
            summary, method = self.fallback_summary(head), "fallback"
        note = ("<conversation_summary>\nEarlier messages were compacted to fit the context window.\n"
                f"{summary}\n</conversation_summary>")
        if tail and tail[0].get("role") == "user":
            tail = [{**tail[0], "content": f"{note}\n\n{tail[0].get('content') or ''}"}, *tail[1:]]
            session.messages = tail
        else:
            session.messages = [{"role": "user", "content": note}, *tail]
        self.events.emit("context_compacted", before_tokens=before,
                         after_tokens=self.estimate(session.messages, fixed_tokens), method=method)
        return True


def tools_tokens(tools: list[dict[str, Any]]) -> int:
    from ..util import estimate_tokens

    return estimate_tokens(json.dumps(tools))
