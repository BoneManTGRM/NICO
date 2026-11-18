"""Data-path bridge qualified on fixed synthetic children only.

No native client launcher, socket connector, real dispatch or registration hook.
"""
from copy import deepcopy
from dataclasses import dataclass
import math
import os
import selectors
import time

from binding import derive_synthetic_transport_binding, validate_read_scope
from fixed_phase_adapter import validate_fixture
from psql_pipe_adapter import FixedPsqlPipeFixture

@dataclass(frozen=True)
class OwnedFixture:
    input_fd: int
    output_fd: int
    binding_digest: str
    close_input: object
    wait_exit: object
    abort_and_reap: object
    dispose: object

def require(ok,code):
    if not ok: raise ValueError(code)

def _expect_eof(fd, deadline, clock):
    while True:
        remaining=deadline-clock()
        require(remaining>0,'bridge_finish_timeout')
        with selectors.DefaultSelector() as poll:
            poll.register(fd,selectors.EVENT_READ)
            ready=poll.select(remaining)
        require(bool(ready) and clock()<deadline,'bridge_finish_timeout')
        try:
            require(os.read(fd,1)==b'','bridge_trailing_output')
            return
        except BlockingIOError:
            continue

def run_synthetic_bridge(plan, observed, open_owned_fixture, *, now, max_age_hours,
                         io_seconds=20.0, clock=time.monotonic):
    """Use already-owned synthetic subprocess pipes. Output is never evidence."""
    owned=None
    aborted=False
    completed=False
    cleanup_ok=None
    def abort(deadline):
        nonlocal aborted,cleanup_ok
        if aborted:
            return cleanup_ok is True
        aborted=True
        cleanup_ok=False
        cleanup_ok=owned.abort_and_reap(deadline) is True and clock()<deadline
        return cleanup_ok
    try:
        plan,observed=deepcopy(plan),deepcopy(observed)
        digest=derive_synthetic_transport_binding(plan,observed,now=now,max_age_hours=max_age_hours)
        require(type(io_seconds) in (float,int) and math.isfinite(io_seconds)
                and 0<io_seconds<=25,'bridge_deadline_invalid')
        began=clock()
        require(type(began) in (float,int) and math.isfinite(began),'bridge_deadline_invalid')
        work_until=began+io_seconds
        outer=work_until+2.0
        # This opener exists in the synthetic harness only. In a future live
        # approved factory launch itself must obey the absolute work deadline.
        owned=open_owned_fixture(digest,work_until)
        require(type(owned) is OwnedFixture and owned.binding_digest==digest and clock()<work_until,
                'bridge_fixture_unverified')
        pipe=FixedPsqlPipeFixture(owned.input_fd,owned.output_fd,
                                 scope=validate_read_scope(plan['approved_read_scope']),fixture_deadline=work_until,
                                 cleanup_deadline=outer,close_owned_fixture=abort,clock=clock)
        result=validate_fixture(pipe,plan,observed,now=now,max_age_hours=max_age_hours)
        require(owned.close_input() is True,'bridge_finish_unverified')
        _expect_eof(owned.output_fd,outer,clock)
        code=owned.wait_exit(outer)
        require(type(code) is int and code==0 and clock()<outer,'bridge_finish_unverified')
        completed=True
        require(owned.dispose() is True and clock()<outer,'bridge_finish_unverified')
        return result
    except Exception:
        if type(owned) is OwnedFixture:
            try:
                if not completed and not aborted:
                    abort(outer)
            except Exception:
                pass
            try:
                require(owned.dispose() is True,'bridge_disposal_unverified')
            except Exception:
                raise ValueError('offline_transport_cleanup_unverified') from None
            if not completed and cleanup_ok is not True:
                raise ValueError('offline_transport_cleanup_unverified') from None
        raise ValueError('offline_transport_bridge_rejected') from None

def dispatch():
    raise ValueError('database_execution_disabled')
