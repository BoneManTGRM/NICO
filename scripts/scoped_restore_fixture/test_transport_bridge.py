from dataclasses import replace
import json
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock

from test_binding import NOW
import test_fixed_phase_adapter as setup
from test_psql_pipe_adapter import FAKE
import fixed_phase_adapter as phases
import transport_bridge as b

@unittest.skipUnless(os.name=='posix','requires POSIX test pipes')
class BridgeTests(unittest.TestCase):
    def make(self,mode):
        p,o,fixture=setup.FixedPhaseTests().state()
        data=fixture.data
        outs=[[data[phases.Phase.BOOTSTRAP]['values']],[data[phases.Phase.CATALOG]],
              [data[phases.Phase.LEDGER]],[json.loads(data[phases.Phase.SAMPLE])],[]]
        self.opened=0
        self.aborted=0
        self.disposed=0
        def opener(digest,deadline):
            self.opened+=1
            child=subprocess.Popen([sys.executable,'-I','-S','-c',FAKE,json.dumps(outs),mode],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                env={'LANG':'C'},close_fds=True,shell=False,start_new_session=True)
            self.child=child
            def emergency():
                if child.poll() is None: child.kill()
                child.wait(timeout=1)
                child.stdin.close();child.stdout.close()
            self.addCleanup(emergency)
            for f in (child.stdin,child.stdout):os.set_blocking(f.fileno(),False)
            def close_input():
                child.stdin.close()
                return child.stdin.closed
            def wait_exit(end):
                return child.wait(timeout=max(0,end-time.monotonic()))
            def abort(end):
                self.aborted+=1
                if child.poll() is None: child.kill()
                wait_exit(end)
                return child.returncode is not None
            def dispose():
                self.disposed+=1
                child.stdin.close();child.stdout.close()
                return child.stdin.closed and child.stdout.closed
            if mode=='wrong_binding':digest='0'*64
            return b.OwnedFixture(child.stdin.fileno(),child.stdout.fileno(),digest,
                  close_input,wait_exit,abort,dispose)
        return p,o,opener
    def run_case(self,p,o,opener,limit=4):
        return b.run_synthetic_bridge(p,o,opener,now=NOW,max_age_hours=36,io_seconds=limit)
    def test_fixed_full_pipeline_closes_both_pipes_and_waits_zero(self):
        p,o,open_=self.make('normal')
        result=self.run_case(p,o,open_)
        self.assertFalse(result['restore_evidence_eligible'])
        self.assertEqual(self.child.returncode,0)
        self.assertTrue(self.child.stdin.closed and self.child.stdout.closed)
        self.assertEqual((self.opened,self.aborted,self.disposed),(1,0,1))
    def test_bad_lineage_or_target_never_calls_open(self):
        p,o,_=self.make('normal')
        p['restored_backup_reference_sha256']='c'*64
        never=Mock()
        with self.assertRaisesRegex(ValueError,'^offline_transport_bridge_rejected$'):
            self.run_case(p,o,never)
        never.assert_not_called()
    def test_wrong_owned_binding_times_out_or_trailing_or_nonzero_fail_closed(self):
        for mode,limit in [('wrong_binding',4),('hang',.3),('late_end',4),('failed_exit',4)]:
            with self.subTest(mode=mode):
                p,o,open_=self.make(mode)
                with self.assertRaisesRegex(ValueError,'^offline_transport_bridge_rejected$') as e:
                    self.run_case(p,o,open_,limit=limit)
                self.assertTrue(e.exception.__suppress_context__)
                self.assertIsNotNone(self.child.returncode)
                self.assertTrue(self.child.stdin.closed and self.child.stdout.closed)
                self.assertEqual(self.opened,1)
                self.assertEqual(self.aborted,1)
    def test_unverified_cleanup_is_a_distinct_redacted_failure(self):
        p,o,baseline=self.make('wrong_binding')
        def opener(digest,end):
            lease=baseline(digest,end)
            def failed(end):
                lease.abort_and_reap(end)  # Keep the local fixture safe.
                raise RuntimeError('do not echo details')
            return replace(lease,abort_and_reap=failed)
        with self.assertRaisesRegex(ValueError,'^offline_transport_cleanup_unverified$') as err:
            self.run_case(p,o,opener)
        self.assertTrue(err.exception.__suppress_context__)
        self.assertIsNotNone(self.child.returncode)
    def test_no_dispatch(self):
        with self.assertRaisesRegex(ValueError,'^database_execution_disabled$'):b.dispatch()
