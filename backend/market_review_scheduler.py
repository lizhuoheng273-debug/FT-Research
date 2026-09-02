"""Non-blocking 15:30 scheduler for the post-close market brief."""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
from typing import Any, Callable

from market_review import BEIJING
from market_review_brief import brief_ready


def _ensure_beijing(value: datetime) -> datetime:
    return value.replace(tzinfo=BEIJING) if value.tzinfo is None else value.astimezone(BEIJING)


class PostCloseReviewScheduler:
    def __init__(self, snapshot_service: Any, brief_service: Any,
                 now_fn: Callable[[], datetime] | None = None,
                 trading_day_fn: Callable[[date], bool] | None = None,
                 interval_seconds: int = 60):
        self.snapshot_service = snapshot_service
        self.brief_service = brief_service
        self.now_fn = now_fn or (lambda: datetime.now(BEIJING))
        self.trading_day_fn = trading_day_fn or (lambda value: value.weekday() < 5)
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> dict[str, Any]:
        now = _ensure_beijing(self.now_fn())
        if not self.trading_day_fn(now.date()):
            return {"status": "non_trading_day"}
        if (now.hour, now.minute) < (15, 30):
            return {"status": "before_close"}
        snapshot = self.snapshot_service.get_review()
        if not brief_ready(snapshot):
            return {"status": "missing", "brief": {"status": "missing"}}
        result = self.brief_service.generate(snapshot)
        setter = getattr(self.snapshot_service, "set_brief", None)
        if setter:
            setter(snapshot.get("tradingDate"), result)
        return result

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ft-market-review-brief", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                pass
            self._stop.wait(self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._thread = None
