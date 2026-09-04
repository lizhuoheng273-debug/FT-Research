"""Bounded upstream ingestion, independent of SQLite write latency."""
from __future__ import annotations

import queue
import threading
import time

_PRODUCERS = threading.BoundedSemaphore(4)


def buffered_events(source, control, deadline, clock=time.time):
    capacity = _PRODUCERS
    events = queue.Queue(maxsize=128)
    stopped = threading.Event()
    end = object()

    def put(value):
        while not stopped.is_set() and not control.cancelled:
            try:
                events.put(value, timeout=0.05)
                return
            except queue.Full:
                pass

    def produce():
        try:
            for event in source:
                if stopped.is_set() or control.cancelled:
                    break
                put(event)
        except Exception as exc:
            put(exc)
        finally:
            try:
                if hasattr(source, 'close'):
                    source.close()
            finally:
                put(end)
                capacity.release()

    acquired = False
    started = False
    try:
        acquired = capacity.acquire(blocking=False)
        if not acquired:
            yield {'type': 'progress', 'payload': {
                'phase': 'queue', 'status': 'running', 'message': '正在等待可用模型连接…',
            }}
        while not acquired:
            if control.cancelled:
                return
            if clock() >= deadline:
                raise TimeoutError('分析已达总时限')
            acquired = capacity.acquire(timeout=0.1)
        if control.cancelled:
            return
        if clock() >= deadline:
            raise TimeoutError('分析已达总时限')
        threading.Thread(target=produce, name='ft-upstream', daemon=True).start()
        started = True
    finally:
        if not started:
            if acquired:
                capacity.release()
            if hasattr(source, 'close'):
                source.close()
    pending = None
    try:
        while not control.cancelled:
            if clock() >= deadline:
                raise TimeoutError('分析已达总时限')
            if pending is None:
                try:
                    event = events.get(timeout=0.1)
                except queue.Empty:
                    continue
            else:
                event, pending = pending, None
            if event is end:
                return
            if isinstance(event, Exception):
                raise event
            if event.get('type') == 'delta':
                # Drain only text already received; never delay the first token
                # to manufacture an animation or a fixed-size batch.
                payload = dict(event.get('payload') or {})
                text = str(payload.get('text', event.get('text', '')))
                while len(text) < 16384:
                    try:
                        candidate = events.get_nowait()
                    except queue.Empty:
                        break
                    if not isinstance(candidate, dict) or candidate.get('type') != 'delta':
                        pending = candidate
                        break
                    text += str((candidate.get('payload') or {}).get('text', candidate.get('text', '')))
                yield {'type':'delta', 'payload':{**payload, 'text':text}}
            else:
                yield event
    finally:
        stopped.set()
