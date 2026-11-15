from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any


class LoopGuard:
    """Detects the model repeating the exact same call with the same outcome (a classic agent death spiral)."""

    def __init__(self, warn_at: int = 3, stop_at: int = 6, window: int = 14):
        self.warn_at, self.stop_at = warn_at, stop_at
        self.recent: deque[str] = deque(maxlen=window)

    def record(self, name: str, args: dict[str, Any], content: str) -> str:
        raw = json.dumps([name, args, content[:300]], sort_keys=True, default=str)
        sig = hashlib.sha1(raw.encode()).hexdigest()
        self.recent.append(sig)
        count = self.recent.count(sig)
        if count >= self.stop_at:
            return "stop"
        if count >= self.warn_at:
            return "warn"
        return "ok"
