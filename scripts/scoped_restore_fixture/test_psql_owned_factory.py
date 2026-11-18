import json
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock

from test_binding import NOW
import test_fixed_phase_adapter as setup
import test_no_child_design as profile
from test_psql_pipe_adapter import FAKE
import fixed_phase_adapter as phases
import psql_owned_factory as f
import transport_bridge as bridge

@unittest.skipUnless(os.name=='posix','requires POSIX test pipes')
class FactoryTests(unittest.TestCase):
    def make(self,mode):
        p,o,fixture=setup.FixedPhaseTests().state()
        data=fixture.data
        opts=[[data[phases.Phase.BOOTSTRAP]['values']],[data[phases.Phase.CATALOG]],
              [data[phases.Phase.LEDGER]],[json.loads(data[phases.Phase.SAMPLE])],[]]
        def spawn(_):
            child=subprocess.Popen([sys.executable,'-I','-S','-c',FAKE,json.dumps(opts),mode],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                env={'LANG':'C'},close_fds=True,shell=False,start_new_session=True)
            self.child=child
            def emergency():
                if child.poll() is None: child.kill()
                child.wait(timeout=1)
                child.stdin.close();child.stdout.close()
            self.addCleanup(emergency)
            return child
        return p,o,spawn
    def test_end_to_end_factory_adopts_only_test_child_and_bridge_reaps(self):
        p,o,spawn=self.make('normal')
        result=bridge.run_synthetic_bridge(p,o,lambda d,t:f.adopt_synthetic_fixed_child(spawn,d,t),
                                now=NOW,max_age_hours=36,io_seconds=4)
        self.assertEqual(result['sample_count'],1)
        self.assertFalse(result['restore_evidence_eligible'])
        self.assertEqual(self.child.returncode,0)
        self.assertTrue(self.child.stdin.closed and self.child.stdout.closed)
    def test_second_pipe_setup_failure_reaps_and_disposes(self):
        _,_,spawn=self.make('hang')
        calls=[]
        def setup_pipe(fd,blocking):
            calls.append(fd)
            if len(calls)==2:raise RuntimeError('do not echo')
            os.set_blocking(fd,blocking)
        with self.assertRaisesRegex(ValueError,'^offline_fixed_factory_rejected$') as e:
            f.adopt_synthetic_fixed_child(spawn,'a'*64,time.monotonic()+3,
                                          configure_nonblocking=setup_pipe)
        self.assertTrue(e.exception.__suppress_context__)
        self.assertIsNotNone(self.child.returncode)
        self.assertTrue(self.child.stdin.closed and self.child.stdout.closed)
    def test_expired_or_invalid_binding_does_not_spawn(self):
        fixture=Mock()
        for digest,end in [('a'*64,time.monotonic()-1),('0'*64,time.monotonic()+1),('b'*64,float('nan'))]:
            with self.assertRaisesRegex(ValueError,'^offline_fixed_factory_rejected$'):
                f.adopt_synthetic_fixed_child(fixture,digest,end)
        fixture.assert_not_called()
    def test_late_spawn_before_cleanup_deadline_reaps(self):
        _,_,spawn=self.make('hang')
        def late(end):
            child=spawn(end)
            time.sleep(max(0,end-time.monotonic())+.02)
            return child
        with self.assertRaisesRegex(ValueError,'^offline_fixed_factory_rejected$'):
            f.adopt_synthetic_fixed_child(late,'a'*64,time.monotonic()+.1)
        self.assertIsNotNone(self.child.returncode)
        self.assertTrue(self.child.stdin.closed and self.child.stdout.closed)
    def test_prospective_native_profile_is_fixed_and_never_invoked(self):
        result=f.native_profile_disabled(**profile.NoChildTests().good())
        self.assertFalse(result['database_execution_enabled'])
        self.assertEqual(result['fixture_command'][-3:],('-n','-f','-'))
        self.assertEqual(result['fixture_command'][0],'/usr/bin/psql')
        self.assertNotIn('PGPASSWORD',result['fixture_environment'])
        with self.assertRaisesRegex(ValueError,'^database_execution_disabled$'): f.dispatch()
