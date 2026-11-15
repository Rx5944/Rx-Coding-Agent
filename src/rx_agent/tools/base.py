from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, replace
from typing import Any

from ..config import Settings
from ..errors import ToolError
from ..events import EventBus
from ..util import truncate_middle
from ..workspace.index import CodeIndex
from ..workspace.paths import Workspace
from .tracker import FileTracker
from .validate import validate_args

log = logging.getLogger("rx.tools")


@dataclass
class ToolResult:
    ok: bool
    content: str
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, content: str, **meta: Any) -> ToolResult:
        return cls(True, content, meta)

    @classmethod
    def error(cls, content: str, **meta: Any) -> ToolResult:
        return cls(False, content, meta)


@dataclass
class ToolContext:
    workspace: Workspace
    tracker: FileTracker
    settings: Settings
    events: EventBus
    index: CodeIndex
    sandbox: Any = None  # rx_agent.sandbox.base.Sandbox
    verifier: Any = None  # rx_agent.verify.Verifier
    session: Any = None  # rx_agent.core.session.Session
    call_id: str | None = None

    def for_call(self, call_id: str) -> ToolContext:
        return replace(self, call_id=call_id)


class Tool:
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    # read: inspects only | edit: changes files | exec: runs commands | meta: agent bookkeeping
    category: str = "read"
    concurrency_safe: bool = False

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:  # pragma: no cover
        raise NotImplementedError

    def summary(self, args: dict[str, Any]) -> str:
        return self.name

    def paths(self, args: dict[str, Any]) -> list[str]:
        """Workspace-relative paths this call may write (used by the permission policy)."""
        return []

    async def preview(self, ctx: ToolContext, args: dict[str, Any]) -> str | None:
        """Optional human-readable preview (e.g. a diff) shown with approval prompts."""
        return None

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self, mode: str = "ask") -> list[dict[str, Any]]:
        """Plan mode hides tools that change files so the model doesn't waste turns on them."""
        return [t.schema() for t in self._tools.values() if not (mode == "plan" and t.category == "edit")]

    async def execute(self, ctx: ToolContext, tool: Tool, raw_args: dict[str, Any]) -> ToolResult:
        clean, err = validate_args(tool.parameters, raw_args)
        if err or clean is None:
            return ToolResult.error(
                f"Invalid arguments for {tool.name}: {err}\nExpected parameters: {json.dumps(tool.parameters)}"
            )
        try:
            result = await tool.run(ctx, clean)
        except ToolError as exc:
            return ToolResult.error(str(exc))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("tool %s crashed", tool.name)
            return ToolResult.error(f"{tool.name} failed unexpectedly: {type(exc).__name__}: {exc}")
        result.content = truncate_middle(result.content, ctx.settings.max_output_chars)
        return result
