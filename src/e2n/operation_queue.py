"""Resumable operation queue primitives with Notion rate limiting."""

from __future__ import annotations

from collections import deque
import threading
import time
from typing import Callable

from e2n.state import OperationRecord, ProcessingStateStore


class NotionRateLimiter:
    """Global token window limiter enforcing a max operation rate."""

    def __init__(self, max_operations: int = 3, per_seconds: float = 1.0) -> None:
        if max_operations < 1:
            raise ValueError("max_operations must be at least 1")
        if per_seconds <= 0:
            raise ValueError("per_seconds must be positive")
        self._max_operations = max_operations
        self._per_seconds = per_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until the next token is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._evict_expired(now)
                if len(self._timestamps) < self._max_operations:
                    self._timestamps.append(now)
                    return
                wait_seconds = self._per_seconds - (now - self._timestamps[0])
            if wait_seconds > 0:
                time.sleep(wait_seconds)

    def _evict_expired(self, now: float) -> None:
        while self._timestamps and now - self._timestamps[0] >= self._per_seconds:
            self._timestamps.popleft()


class ResumableOperationQueue:
    """Small queue runner that claims, executes, and checkpoints operations."""

    def __init__(self, store: ProcessingStateStore, rate_limiter: NotionRateLimiter | None = None) -> None:
        self._store = store
        self._rate_limiter = rate_limiter or NotionRateLimiter(max_operations=3, per_seconds=1.0)

    def run_once(
        self,
        run_id: str,
        handler: Callable[[OperationRecord], str],
        retry_after_seconds: int = 1,
    ) -> OperationRecord | None:
        """Execute one due operation and persist success or failure state."""
        operation = self._store.claim_next_operation(run_id)
        if operation is None:
            return None

        self._rate_limiter.acquire()
        try:
            notion_object_id = handler(operation)
        except Exception as exc:
            self._store.mark_operation_failed(
                operation.operation_id,
                error_message=str(exc),
                retry_after_seconds=retry_after_seconds,
            )
            return operation

        self._store.mark_operation_committed(operation.operation_id, notion_object_id=notion_object_id)
        return operation
