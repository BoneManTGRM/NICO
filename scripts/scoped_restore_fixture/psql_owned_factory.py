"""Fixed client's acquisition/adoption seam, smoke-tested using a fake only.

There is no native launcher in the production dispatch. The injected opener in
the synthetic harness must create only its fixed, credential-free fixture.
"""
import math
import os
import re
import stat
import time

from fixed_psql_design import build_fixture_argv
from transport_bridge import OwnedFixture

def require(ok,code):
    if not ok: raise ValueError(code)

def native_profile_disabled(*, release, user, database, peer, claims):
    """Inspect the prospective fixed streaming profile without launching it."""
    p=build_fixture_argv(release=release,user=user,database=database,peer=peer,claims=claims)
    fixed=p['fixture_command'][:-2]+('-n','-f','-')
    return {'fixture_command':fixed,'fixture_environment':p['fixture_environment'],
            'database_execution_enabled':False}

def _seconds_left(deadline,clock):
    left=deadline-clock()
    require(math.isfinite(left) and left>0,'factory_deadline')
    return left

def adopt_synthetic_fixed_child(spawn_fixed, digest, work_until, *, clock=time.monotonic,
                                configure_nonblocking=os.set_blocking):
    """Own one fixed synthetic child or clean all known resources on failure.

    spawn_fixed is an internal test callback, not a dispatcher; it is separately
    responsible for any process it starts but does not return.
    """
    child=None
    cleanup_until=None
    def close_streams():
        ok=True
        for name in ('stdin','stdout'):
            try:
                s=getattr(child,name,None)
                if s is not None:
                    s.close()
                    ok=bool(s.closed) and ok
            except Exception:
                ok=False
        return ok
    def abort_and_reap(deadline):
        ok=False
        try:
            if child.poll() is None:
                child.kill()  # fixed direct child only, no caller PID
            child.wait(timeout=_seconds_left(deadline,clock))
            ok=child.returncode is not None and clock()<deadline
        except Exception:
            ok=False
        return close_streams() and ok
    try:
        require(type(digest) is str and re.fullmatch(r'[0-9a-f]{64}',digest)
                and digest != '0'*64,'factory_binding_invalid')
        require(type(work_until) in (int,float) and math.isfinite(work_until),'factory_deadline')
        require(_seconds_left(work_until,clock)<=25,'factory_deadline')
        cleanup_until=work_until+2.0
        # Only fixture creation is wired in this file. This checkpoint does
        # not assert that a callback stuck in native spawn can be preempted.
        child=spawn_fixed(work_until)
        _seconds_left(work_until,clock)
        require(child.poll() is None and child.stdin is not None and child.stdout is not None,
                'factory_child_unavailable')
        stdin,stdout=child.stdin.fileno(),child.stdout.fileno()
        require(stdin!=stdout and all(stat.S_ISFIFO(os.fstat(fd).st_mode) for fd in (stdin,stdout)),
                'factory_pipe_unverified')
        for fd in (stdin,stdout):
            configure_nonblocking(fd,False)
            require(not os.get_blocking(fd),'factory_pipe_unverified')
            _seconds_left(work_until,clock)
        def close_input():
            child.stdin.close()
            return child.stdin.closed
        def wait_exit(deadline):
            return child.wait(timeout=_seconds_left(deadline,clock))
        return OwnedFixture(stdin,stdout,digest,close_input,wait_exit,
                            abort_and_reap,close_streams)
    except Exception:
        if child is not None and not abort_and_reap(cleanup_until):
            raise ValueError('offline_factory_cleanup_unverified') from None
        raise ValueError('offline_fixed_factory_rejected') from None

def dispatch():
    raise ValueError('database_execution_disabled')
