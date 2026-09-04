import threading
import time
import pytest
from ai_jobs import RunControl
from stream_runtime import buffered_events
import stream_runtime


def test_burst_text_is_coalesced_without_loss_or_reordering():
    control=RunControl(lambda: True)
    ready=threading.Event()
    def source():
        for i in range(80):
            yield {'type':'delta','payload':{'text':str(i)+','}}
        ready.set()
        yield {'type':'progress','payload':{'message':'tool'}}
        yield {'type':'done','payload':{}}
    stream=buffered_events(source(),control,time.time()+5)
    first=next(stream)
    assert ready.wait(1)
    rest=list(stream)
    texts=[e['payload']['text'] for e in [first]+rest if e['type']=='delta']
    assert ''.join(texts)==''.join(str(i)+',' for i in range(80))
    assert len(texts)<80
    assert [e['type'] for e in rest][-2:]==['progress','done']


def test_total_deadline_applies_while_upstream_produces_nothing():
    release=threading.Event()
    control=RunControl(lambda: True)
    def source():
        release.wait(2)
        yield {'type':'done'}
    try:
        with pytest.raises(TimeoutError):
            list(buffered_events(source(),control,time.time()+.05))
    finally:
        release.set()


def test_busy_producer_capacity_waits_and_then_runs(monkeypatch):
    capacity = threading.BoundedSemaphore(1)
    capacity.acquire()
    monkeypatch.setattr(stream_runtime, '_PRODUCERS', capacity)
    control = RunControl(lambda: True)
    stream = buffered_events(iter([{'type': 'done'}]), control, time.time() + 2)
    waiting = next(stream)
    assert waiting['type'] == 'progress'
    assert waiting['payload']['phase'] == 'queue'
    capacity.release()
    assert list(stream) == [{'type': 'done'}]


@pytest.mark.parametrize('cancelled', [True, False])
def test_wait_for_producer_can_be_cancelled_or_reach_deadline(monkeypatch, cancelled):
    capacity = threading.BoundedSemaphore(1)
    capacity.acquire()
    monkeypatch.setattr(stream_runtime, '_PRODUCERS', capacity)
    control = RunControl(lambda: True)
    stream = buffered_events(iter([{'type': 'done'}]), control, time.time() + .05)
    assert next(stream)['payload']['phase'] == 'queue'
    if cancelled:
        control.cancel()
        assert list(stream) == []
    else:
        with pytest.raises(TimeoutError):
            list(stream)
    capacity.release()
