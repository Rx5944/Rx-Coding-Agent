from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol


@dataclass
class ApprovalRequest:
    tool: str
    summary: str
    reason: str
    risk: str
    arguments: dict[str, Any] = field(default_factory=dict)
    preview: str | None = None
    can_remember: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class ApprovalResponse:
    approved: bool
    remember: bool = False
    message: str | None = None


class Approver(Protocol):
    async def request(self, req: ApprovalRequest) -> ApprovalResponse: ...


class StaticApprover:
    """Always answers the same way (tests, CI, HTTP API runs: approve=False means 'deny anything that asks')."""

    def __init__(self, approve: bool, remember: bool = False):
        self.approve, self.remember = approve, remember
        self.requests: list[ApprovalRequest] = []

    async def request(self, req: ApprovalRequest) -> ApprovalResponse:
        self.requests.append(req)
        return ApprovalResponse(self.approve, self.remember and self.approve,
                                None if self.approve else "Non-interactive run: approval is not available.")


class CallbackApprover:
    def __init__(self, fn: Callable[[ApprovalRequest], Awaitable[ApprovalResponse]]):
        self.fn = fn

    async def request(self, req: ApprovalRequest) -> ApprovalResponse:
        return await self.fn(req)


class BrokerApprover:
    """Async round-trip for server clients: the loop emits `approval_required`; the client replies with
    `approval_response`; the handler calls resolve(). Replaces the old blocking input() on server stdin."""

    def __init__(self, timeout: float = 600.0):
        self.timeout = timeout
        self._pending: dict[str, asyncio.Future[ApprovalResponse]] = {}

    async def request(self, req: ApprovalRequest) -> ApprovalResponse:
        fut: asyncio.Future[ApprovalResponse] = asyncio.get_running_loop().create_future()
        self._pending[req.id] = fut
        try:
            return await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            return ApprovalResponse(False, message="Approval timed out; the action was not performed.")
        finally:
            self._pending.pop(req.id, None)

    def resolve(self, request_id: str, approved: bool, remember: bool = False, message: str | None = None) -> bool:
        fut = self._pending.get(request_id)
        if fut is None or fut.done():
            return False
        fut.set_result(ApprovalResponse(bool(approved), bool(remember), message))
        return True

    def pending_ids(self) -> list[str]:
        return list(self._pending)

    def cancel_all(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_result(ApprovalResponse(False, message="Connection closed."))
