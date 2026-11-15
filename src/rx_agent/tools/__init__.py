from .base import Tool, ToolContext, ToolRegistry, ToolResult
from .edit import ApplyPatch, EditFile, MultiEdit
from .fs import ListDir, ReadFile, WriteFile
from .git import GitDiff, GitLog, GitStatus
from .search import FindSymbol, Glob, Grep, RepoMap
from .shell import RunCommand, RunTests
from .todo import TodoWrite


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (ReadFile(), ListDir(), Glob(), Grep(), RepoMap(), FindSymbol(), EditFile(), MultiEdit(),
                 ApplyPatch(), WriteFile(), RunCommand(), RunTests(), GitStatus(), GitDiff(), GitLog(), TodoWrite()):
        registry.register(tool)
    return registry


__all__ = ["Tool", "ToolContext", "ToolRegistry", "ToolResult", "default_registry"]
