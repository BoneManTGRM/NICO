"""Deterministic cancellation schedules around the real bounded permit."""
from __future__ import annotations
import threading
import pytest
import nico.comprehensive_final_report_background_v1 as background

@pytest.mark.parametrize('cancel_phase',['before_permit_grant','after_permit_grant'])
def test_cancelled_acquire_returns_the_permit(monkeypatch,cancel_phase):
    permit=threading.BoundedSemaphore(value=1)
    assert permit.acquire(blocking=False)
    entered=threading.Event();commence=threading.Event();granted=threading.Event();resume=threading.Event()
    stop=threading.Event();answers=[];errors=[]
    class ControlledPermit:
        def acquire(self,*,timeout):
            entered.set()
            assert timeout==0.25
            assert commence.wait(2.0),'control did not permit acquisition'
            acquired=permit.acquire(timeout=timeout)
            if acquired:
                granted.set()
                assert resume.wait(2.0),'control did not resume permit grant'
            return acquired
        def release(self):
            permit.release()
    monkeypatch.setattr(background,'_PUBLICATION_SLOT',ControlledPermit())
    def invoke():
        try: answers.append(background._acquire_publication_slot(stop))
        except BaseException as exc: errors.append(exc)
    worker=threading.Thread(target=invoke,name='owned-cancelled-slot-control')
    holder_released=False
    try:
        worker.start()
        assert entered.wait(2.0),'control did not reach acquisition after stop precheck'
        if cancel_phase=='before_permit_grant':stop.set()
        permit.release();holder_released=True
        commence.set()
        assert granted.wait(2.0),'control did not acquire real permit'
        if cancel_phase=='after_permit_grant':stop.set()
        resume.set();worker.join(timeout=2.0)
        assert not worker.is_alive()
        assert errors==[]
        assert answers==[False],'cancelled task was admitted after semaphore acquisition'
        assert permit.acquire(blocking=False),'cancelled acquisition leaked its permit'
        assert not permit.acquire(blocking=False),'cancelled acquisition over-released capacity'
        permit.release()
        with pytest.raises(ValueError):permit.release()
    finally:
        stop.set();commence.set();resume.set()
        if not holder_released:permit.release()
        worker.join(timeout=2.0)

def test_pre_cancelled_acquire_does_not_consume_capacity(monkeypatch):
    permit=threading.BoundedSemaphore(value=1)
    stop=threading.Event();stop.set()
    monkeypatch.setattr(background,'_PUBLICATION_SLOT',permit)
    assert background._acquire_publication_slot(stop) is False
    assert permit.acquire(blocking=False)
    assert not permit.acquire(blocking=False)
    permit.release()

def test_live_acquire_keeps_the_permit_until_released(monkeypatch):
    permit=threading.BoundedSemaphore(value=1)
    monkeypatch.setattr(background,'_PUBLICATION_SLOT',permit)
    assert background._acquire_publication_slot(threading.Event()) is True
    assert not permit.acquire(blocking=False)
    permit.release()
    assert permit.acquire(blocking=False)
    permit.release()
