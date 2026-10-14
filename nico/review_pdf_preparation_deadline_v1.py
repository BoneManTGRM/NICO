"""Independent wall/cancellation supervision with explicit COMMIT uncertainty.

Python/database calls cannot be forcibly stopped safely. They retain capacity
until they physically return; their caller stops advancing the lifecycle.
"""
from __future__ import annotations

from threading import Event, RLock, Thread
import time


class CommitOutcomeUnknown(RuntimeError):
    """COMMIT may have been sent; authenticated recovery must establish outcome."""


class DeadlineGuard:
    HEARTBEAT_INTERVAL = 5.

    def __init__(self, seconds, stop, *, clock=None):
        self.clock = clock or time.monotonic
        self.deadline = self.clock() + seconds
        self.external_stop = stop
        self.stop = Event()
        self.error = None
        self.commit_started = False
        self.commit_acknowledged = False
        self.threads = []
        self.lock = RLock()

    def begin_commit(self):
        with self.lock:
            self.check()
            self.commit_started = True

    def end_commit(self):
        with self.lock:
            self.commit_acknowledged = True

    def remaining(self):
        return max(0., self.deadline - self.clock())

    def check(self):
        with self.lock:
            if self.error is not None:
                raise self.error
            if self.stop.is_set() or self.external_stop.is_set() or not self.remaining():
                self.stop.set()
                if self.commit_started:
                    raise CommitOutcomeUnknown('review_pdf_commit_outcome_unknown')
                raise RuntimeError('review_pdf_cancelled_or_expired')


    def call(self, function, *args, timeout=None, **kwargs):
        self.check()
        done, result = Event(), {}
        def invoke():
            try:
                result['value'] = function(*args, **kwargs)
            except BaseException as error:
                result['error'] = error
            finally:
                done.set()
        thread = Thread(target=invoke, daemon=True, name='nico-review-bounded-call')
        with self.lock:
            self.threads.append(thread)
        started = self.clock()
        thread.start()
        while not done.wait(.02):
            self.check()
            with self.lock:
                if timeout is not None and self.clock() - started >= timeout:
                    self.stop.set()
                    if self.commit_started:
                        raise CommitOutcomeUnknown('review_pdf_commit_outcome_unknown')
                    raise RuntimeError('review_pdf_storage_operation_timeout')
        thread.join()
        self.check()
        if 'error' in result:
            if self.commit_started and not self.commit_acknowledged:
                raise CommitOutcomeUnknown('review_pdf_commit_outcome_unknown') from None
            raise result['error']
        return result.get('value')

    def idle(self):
        with self.lock:
            return all(not thread.is_alive() for thread in self.threads)

    def supervise_lease(self, heartbeat):
        finished = Event()
        def supervise():
            while not finished.wait(self.HEARTBEAT_INTERVAL):
                try:
                    self.call(heartbeat, timeout=5)
                except BaseException as error:
                    if not finished.is_set():
                        self.error = error
                        self.stop.set()
                    return
        thread = Thread(target=supervise, daemon=True, name='nico-review-lease')
        thread.start()
        return finished, thread
