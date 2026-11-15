from __future__ import annotations

from typing import Any

from .base import Tool, ToolContext, ToolResult

STATUSES = ["pending", "in_progress", "completed"]


class TodoWrite(Tool):
    name = "todo_write"
    category = "meta"
    description = (
        "Maintain your task list for multi-step work. Send the FULL list each time. Keep exactly one item "
        "in_progress; mark items completed as soon as they are done."
    )
    parameters = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": STATUSES},
                    },
                    "required": ["content", "status"],
                },
            }
        },
        "required": ["todos"],
    }

    def summary(self, args: dict[str, Any]) -> str:
        return f"update todos ({len(args.get('todos', []))})"

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        todos = [{"content": t["content"], "status": t["status"]} for t in args["todos"]]
        if ctx.session is not None:
            ctx.session.todos = todos
        ctx.events.emit("todos_updated", todos=todos)
        done = sum(1 for t in todos if t["status"] == "completed")
        return ToolResult.success(f"Todos updated ({done}/{len(todos)} completed).")
