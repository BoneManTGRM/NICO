"""Nonblocking fixed-protocol I/O seam; production launch is absent/disabled.

The fixture harness supplies its own already-created, fixed synthetic process.
Do not use this class on restored data until independently authorized transport,
runtime and data-boundary reviews qualify the exact implementation.
"""
import json
import os
import selectors
import stat
import time

from fixed_phase_adapter import Phase, _fixed_sql
from offline_read_runner import MAX_TRANSCRIPT, MAX_ROW, METADATA_MAX
from no_child_design import BEGIN_STMT, READY_STMT

def require(ok,code):
    if not ok: raise ValueError(code)

MarkerPrefix='nico_fixed_phase_end_'
CHUNK=64*1024

def fixture_wire(phase,sql,scope):
    approved,_=_fixed_sql(scope)
    require(type(phase) is Phase and type(sql) is str and sql==approved[phase.value-1],
            'pipe_phase_denied')
    sql=approved[phase.value-1]
    if phase is Phase.BOOTSTRAP:
        sql=BEGIN_STMT+"; SELECT pg_catalog.json_build_array("+READY_STMT.removeprefix('SELECT ')+");"
    mark=MarkerPrefix+str(phase.value)
    return (sql+"\nSELECT '"+mark+"';\n").encode('ascii'), (mark+'\n').encode('ascii')

class FixedPsqlPipeFixture:
    def __init__(self,input_fd,output_fd,*,scope,fixture_deadline,cleanup_deadline,close_owned_fixture,clock=time.monotonic):
        require(type(input_fd) is int and type(output_fd) is int and input_fd!=output_fd
                and input_fd>=0 and output_fd>=0,'pipe_unverified')
        require(all(stat.S_ISFIFO(os.fstat(fd).st_mode) for fd in (input_fd,output_fd)),
                'pipe_unverified')
        now=clock()
        require(0 < fixture_deadline-now <= 25 and
                fixture_deadline < cleanup_deadline <= now+60,'pipe_deadline')
        _fixed_sql(scope)  # Scope checked before any pipe I/O.
        self._scope=scope
        self._input=input_fd; self._output=output_fd; self._deadline=fixture_deadline
        self._cleanup_deadline=cleanup_deadline; self._close=close_owned_fixture; self._clock=clock; self._pending=bytearray()
        self._count=0; self._next=1
        require(not os.get_blocking(input_fd) and not os.get_blocking(output_fd),'pipe_unverified')

    def _wait(self,fd,event):
        timeout=self._deadline-self._clock()
        require(timeout>0,'pipe_deadline')
        with selectors.DefaultSelector() as s:
            s.register(fd,event)
            require(bool(s.select(timeout)) and self._clock()<self._deadline,'pipe_deadline')

    def _send(self,data):
        while data:
            self._wait(self._input,selectors.EVENT_WRITE)
            try:
                n=os.write(self._input,data)
            except BlockingIOError: continue
            require(n>0,'pipe_write_failed')
            data=data[n:]

    def _readline(self,limit):
        while True:
            require(self._clock()<self._deadline,'pipe_deadline')
            offset=self._pending.find(b'\n')
            if offset>=0:
                require(offset+1<=limit,'pipe_output_bound')
                output=bytes(self._pending[:offset+1]);del self._pending[:offset+1]
                return output
            require(len(self._pending)<limit,'pipe_output_bound')
            self._wait(self._output,selectors.EVENT_READ)
            try:
                chunk=os.read(self._output,min(CHUNK,limit-len(self._pending)))
            except BlockingIOError: continue
            require(bool(chunk),'pipe_truncated')
            self._count+=len(chunk)
            require(self._count<=MAX_TRANSCRIPT,'pipe_output_bound')
            self._pending.extend(chunk)

    def response(self,phase,sql):
        require(type(phase) is Phase and phase.value==self._next and not self._pending,
                'pipe_phase_denied')
        data,marker=fixture_wire(phase,sql,self._scope)
        self._send(data)
        rows=[]
        limit=MAX_ROW if phase is Phase.SAMPLE else METADATA_MAX
        while True:
            line=self._readline(limit)
            if line == marker:
                break
            rows.append(line)
            require(len(rows)<=(3 if phase is Phase.SAMPLE else 1),'pipe_framing_invalid')
        self._next+=1
        require(not self._pending,'pipe_framing_invalid')
        if phase is Phase.ROLLBACK:
            require(not rows,'pipe_framing_invalid')
            return b'{"completed":true}'
        if phase is Phase.SAMPLE:
            return b''.join(rows)
        require(len(rows)==1,'pipe_framing_invalid')
        if phase is Phase.BOOTSTRAP:
            # Fixture marker is not authoritative PostgreSQL transaction state.
            val=json.loads(rows[0])
            require(type(val) is list,'pipe_framing_invalid')
            return json.dumps({'values':val,'status':'ok',
                               'transaction_status':'in_read_transaction'}).encode()
        return rows[0]

    def close_fixture(self):
        return self._close(self._cleanup_deadline) is True and self._clock()<self._cleanup_deadline

def dispatch():
    raise ValueError('database_execution_disabled')
