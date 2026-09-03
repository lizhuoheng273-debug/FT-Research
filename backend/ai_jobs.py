from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from ai_limits import LimitExceeded
from session_store import RUN_TERMINAL, NotFound

log = logging.getLogger(__name__)


class RunControl:
    def __init__(self, reserve):
        self._cancel = threading.Event()
        self._reserve = reserve

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float) -> bool:
        return self._cancel.wait(timeout)

    def reserve(self) -> bool:
        if self.cancelled:
            raise LimitExceeded("任务已停止")
        return self._reserve()


class RunManager:
    def __init__(self, store, runner, limits, clock, max_workers: int = 2, queue_size: int = 8):
        self.store, self.runner, self.limits, self.clock = store, runner, limits, clock
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ft-ai")
        self.slots = threading.BoundedSemaphore(max_workers + queue_size)
        self.controls: dict[str, RunControl] = {}
        self.lock = threading.RLock()
        self.store.recover_interrupted()

    def submit(self, principal, conversation_id, request_id, question, context, ip: str = "unknown") -> dict:
        run = self.store.create_run(principal, conversation_id, request_id, question, context)
        if not run["created"]:
            return run
        try:
            self.limits.reserve_question(principal)
        except LimitExceeded:
            self.store.transition_run(run["id"], "queued", "failed")
            self.store.append_event(run["id"], "error", {"code": "question_limit", "message": "本次游客体验的提问额度已用尽"})
            raise
        if not self.slots.acquire(blocking=False):
            self.store.transition_run(run["id"], "queued", "failed")
            self.store.append_event(run["id"], "error", {"code": "queue_full", "message": "任务队列已满"})
            raise LimitExceeded("任务队列已满")
        control = RunControl(lambda: self.limits.reserve(principal, ip, run["id"]))
        with self.lock:
            self.controls[run["id"]] = control
        self.executor.submit(self._execute, principal, run["id"], control)
        return run

    def _execute(self, principal, run_id: str, control: RunControl) -> None:
        answer: list[str] = []
        saw_done = False
        try:
            run = self.store.run_for_principal(principal, run_id)
            self.limits.reserve(principal, "worker", run_id)
            if not self.store.transition_run(run_id, "queued", "running"):
                return
            for event in self.runner(run, control):
                if control.cancelled:
                    break
                event_type = str(event.get("type", "error"))
                payload = dict(event.get("payload") or {})
                if "text" in event and "text" not in payload:
                    payload["text"] = event["text"]
                if event_type == "delta":
                    answer.append(str(payload.get("text", "")))
                if event_type == "done":
                    saw_done = True
                self.store.append_event(run_id, event_type, payload)
                if saw_done:
                    break
            if control.cancelled:
                self.store.append_event(run_id, "stopped", {"message": "已停止"})
                self.store.transition_run(run_id, "running", "stopped")
                self.store.finalize_messages(run_id, run.get("question", ""), "".join(answer), "stopped")
            elif saw_done:
                self.store.transition_run(run_id, "running", "completed")
                self.store.finalize_messages(run_id, run.get("question", ""), "".join(answer), "complete")
            else:
                self.store.append_event(run_id, "error", {"code": "eof", "message": "模型流未收到完整结束事件"})
                self.store.transition_run(run_id, "running", "failed")
                self.store.finalize_messages(run_id, run.get("question", ""), "".join(answer), "failed")
        except LimitExceeded as exc:
            self.store.append_event(run_id, "error", {"code": "limit", "message": str(exc)})
            self.store.transition_run(run_id, "queued", "failed") or self.store.transition_run(run_id, "running", "failed")
        except Exception as exc:  # noqa: BLE001
            log.warning("AI run %s failed (%s)", run_id, type(exc).__name__)
            self.store.append_event(run_id, "error", {"code": "runner_error", "message": "模型服务暂时不可用"})
            self.store.transition_run(run_id, "queued", "failed") or self.store.transition_run(run_id, "running", "failed")
        finally:
            with self.lock:
                self.controls.pop(run_id, None)
            self.slots.release()

    def cancel(self, principal, run_id: str) -> bool:
        run = self.store.run_for_principal(principal, run_id)
        if run["status"] in RUN_TERMINAL:
            return False
        with self.lock:
            control = self.controls.get(run_id)
            if control:
                control.cancel()
        self.store.append_event(run_id, "stopped", {"message": "已停止"})
        return self.store.transition_run(run_id, run["status"], "stopped") or self.store.run_for_principal(principal, run_id)["status"] == "stopped"

    def purge_guest(self, principal_id: str) -> None:
        try:
            principal = self.store.principal_by_id(principal_id)
        except NotFound:
            return
        with self.lock:
            ids = [run_id for run_id, control in self.controls.items() if self.store.run_for_principal(principal, run_id)["status"] in {"queued", "running"}]
            for run_id in ids:
                self.controls[run_id].cancel()
        self.store.purge_guest(principal_id)

    def tick(self) -> None:
        now = float(self.clock())
        for session in self.store.guest_sessions(now):
            try:
                principal = self.store.principal_by_id(session["principal_id"])
            except NotFound:
                continue
            with self.store._connect() as conn:
                runs = conn.execute("SELECT id,status FROM run WHERE principal_id=? AND status IN ('queued','running')", (principal.id,)).fetchall()
            for run in runs:
                if session["last_heartbeat"] + 90 <= now:
                    try:
                        self.cancel(principal, run["id"])
                    except NotFound:
                        pass
            if session["expires_at"] <= now or session["last_heartbeat"] + 1800 <= now:
                self.store.purge_guest(principal.id)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)
