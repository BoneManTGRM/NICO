import json
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import fixed_phase_adapter as phases
import psql_pipe_adapter as p
from test_binding import NOW
import test_fixed_phase_adapter as setup

# A fixed, local synthetic executable selected by the test, never psql/DB.
# No network/credentials or caller executable selection exist.
FAKE=(
'import json,os,sys,time\n'
'answers=json.loads(sys.argv[1]); mode=sys.argv[2]; expected=1\n'
'for line in sys.stdin:\n'
' mark="nico_fixed_phase_end_"+str(expected)\n'
' if line!="SELECT \'"+mark+"\';\\n": continue\n'
' if mode=="truncate" and expected==1: sys.exit(0)\n'
' if mode=="hang" and expected==1: time.sleep(30)\n'
' for value in answers[expected-1]:\n'
'  payload=(json.dumps(value)+"\\n").encode()\n'
'  if mode=="fragment": os.write(1,payload[:1]); time.sleep(.01); os.write(1,payload[1:])\n'
'  else: os.write(1,payload)\n'
' os.write(1,(mark+"\\n").encode())\n'
' if mode=="late" and expected==1: time.sleep(.02); os.write(1,b"unexpected\\n")\n'
' expected+=1\n'
' if expected==6:\n'
'  if mode=="late_end": time.sleep(.02); os.write(1,b"late suffix\\n")\n'
'  if mode=="failed_exit": sys.exit(7)\n'
'  break\n'
)

@unittest.skipUnless(os.name=='posix','requires POSIX test pipes')
class PipeTests(unittest.TestCase):
    def state(self,mode,seconds):
        self.plan,self.observed,fixture=setup.FixedPhaseTests().state()
        ans=fixture.data
        outs=[[ans[phases.Phase.BOOTSTRAP]['values']],[ans[phases.Phase.CATALOG]],
              [ans[phases.Phase.LEDGER]],[json.loads(ans[phases.Phase.SAMPLE])],[]]
        self.child=subprocess.Popen([sys.executable,'-I','-S','-c',FAKE,json.dumps(outs),mode],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env={'LANG':'C'},close_fds=True,shell=False,start_new_session=True)
        self.addCleanup(self.finish,time.monotonic()+2,self.child)
        for f in (self.child.stdin,self.child.stdout):os.set_blocking(f.fileno(),False)
        self.pipe=p.FixedPsqlPipeFixture(self.child.stdin.fileno(),self.child.stdout.fileno(),scope=('synthetic','synthetic'),
                    fixture_deadline=time.monotonic()+seconds,cleanup_deadline=time.monotonic()+seconds+1,
                    close_owned_fixture=self.finish)
    def finish(self,deadline,child=None):
        child=self.child if child is None else child
        if child.poll() is None:
            child.kill()
        try:
            child.wait(timeout=max(0,deadline-time.monotonic()))
        finally:
            child.stdin.close();child.stdout.close()
        return child.poll() is not None
    def verify(self):
        return phases.validate_fixture(self.pipe,self.plan,self.observed,now=NOW,max_age_hours=36)
    def test_real_fixed_fake_child_io_same_pipe_and_offline_result(self):
        self.state('normal',4)
        result=self.verify()
        self.assertEqual(result['sample_count'],1)
        self.assertFalse(result['restore_evidence_eligible'])
        self.assertEqual(self.child.wait(timeout=1),0)
    def test_truncated_and_timed_out_fixture_are_reaped(self):
        for mode in ('truncate','hang'):
            with self.subTest(mode=mode):
                self.state(mode,.3 if mode=='hang' else 4)
                with self.assertRaisesRegex(ValueError,'^fixed_phase_fixture_rejected$'):self.verify()
                self.assertIsNotNone(self.child.returncode)
    def test_fragmented_output_and_bounded_oversize(self):
        self.state('fragment',4)
        self.assertEqual(self.verify()['sample_count'],1)
        self.assertEqual(self.child.wait(timeout=1),0)
        self.state('normal',4)
        with patch.object(p,'MAX_ROW',32):
            with self.assertRaisesRegex(ValueError,'^fixed_phase_fixture_rejected$'):self.verify()
        self.assertIsNotNone(self.child.returncode)
    def test_unsolicited_delayed_output_rejected_on_next_phase(self):
        self.state('late',4)
        with self.assertRaisesRegex(ValueError,'^fixed_phase_fixture_rejected$'):self.verify()
        self.assertIsNotNone(self.child.returncode)
    def test_wrong_sql_wrong_phase_and_execution_disabled(self):
        self.state('normal',4)
        for phase,sql in ((phases.Phase.BOOTSTRAP,'SELECT 1;'),
                          (phases.Phase.LEDGER,phases._fixed_sql(('synthetic','synthetic'))[0][2])):
            with self.assertRaisesRegex(ValueError,'^pipe_phase_denied$'):self.pipe.response(phase,sql)
        with self.assertRaisesRegex(ValueError,'^database_execution_disabled$'):p.dispatch()
