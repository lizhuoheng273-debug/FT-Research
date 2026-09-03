"""Bounded execution helpers for data sources that may block indefinitely."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable, Literal


ToolStatus = Literal["ok", "timeout", "error"]


@dataclass(frozen=True)
class ToolOutcome:
    status: ToolStatus
    value: Any = None
    error: Exception | None = None


# Upstream libraries are not uniformly cancellable. A bounded number of timed-out
# daemon calls may finish in the background without exhausting the process.
_UPSTREAM_SLOTS = threading.BoundedSemaphore(8)


def run_with_deadline(fn: Callable[[], Any], timeout_seconds: float) -> ToolOutcome:
    """Run ``fn`` in a daemon worker and return by the deadline."""
    result_queue: queue.Queue[ToolOutcome] = queue.Queue(maxsize=1)
    deadline = max(float(timeout_seconds), 0.0)

    def worker() -> None:
        acquired = _UPSTREAM_SLOTS.acquire(timeout=deadline)
        if not acquired:
            result_queue.put(ToolOutcome("timeout"))
            return
        try:
            result_queue.put(ToolOutcome("ok", value=fn()))
        except Exception as exc:  # noqa: BLE001 - caller converts it to a data gap
            result_queue.put(ToolOutcome("error", error=exc))
        finally:
            _UPSTREAM_SLOTS.release()

    threading.Thread(target=worker, name="ft-tool", daemon=True).start()
    try:
        return result_queue.get(timeout=deadline)
    except queue.Empty:
        return ToolOutcome("timeout")
