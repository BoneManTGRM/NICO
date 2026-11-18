import json
import unittest
from unittest.mock import patch

from test_binding import base,NOW
import test_offline_read_runner as fixture
import fixed_phase_adapter as a

class FakePsql:
    def __init__(self,data): self.data=data; self.calls=[]; self.closed=False
    def response(self,phase,sql):
        self.calls.append((phase,sql))
        x=self.data[phase]
        if isinstance(x,Exception): raise x
        if type(x) is bytes: return x
        return json.dumps(x).encode()
    def close_fixture(self):
        self.closed=True
        return True

class FixedPhaseTests(unittest.TestCase):
    def state(self):
        p,o,f=fixture.StagedReadTest().state()
        m=f[1]['metadata']
        for name, table in m['tables'].items():
            table['types']=a.READ_TYPES.get(name,{}).copy()
        return p,o,FakePsql({a.Phase.BOOTSTRAP:f[0]['session'],
            a.Phase.CATALOG:{k:v for k,v in m.items() if k!='migrations'},
            a.Phase.LEDGER:{'migrations':m['migrations']},
            a.Phase.SAMPLE:json.dumps({'row':f[2]['row']}).encode()+b'\n',
            a.Phase.ROLLBACK:{'completed':True}})
    def verify(self,p,o,f):return a.validate_fixture(f,p,o,now=NOW,max_age_hours=36)
    def deny(self,p,o,f):
        with self.assertRaisesRegex(ValueError,'^fixed_phase_fixture_rejected$') as e:
            self.verify(p,o,f)
        self.assertTrue(e.exception.__suppress_context__)
    def test_end_to_end_fixed_order_and_no_evidence(self):
        p,o,f=self.state();r=self.verify(p,o,f)
        self.assertEqual([x[0] for x in f.calls],list(a.Phase))
        self.assertIn('READ ONLY',f.calls[0][1])
        self.assertNotIn('public.nico_comprehensive_runs',f.calls[1][1])
        self.assertIn('FROM ONLY public.nico_schema_migrations',f.calls[2][1])
        self.assertIn('LIMIT 3',f.calls[3][1])
        self.assertEqual(f.calls[-1][1],'ROLLBACK;')
        self.assertEqual(r,{'status':'synthetic_only','sample_count':1,
                             'database_execution_enabled':False,'restore_evidence_eligible':False})
    def test_scope_is_fixed_binary_exact_before_limit_and_not_interpolated_freely(self):
        sequence,_=a._fixed_sql(('customer.A','project:Z'))
        sql=sequence[a.Phase.SAMPLE.value-1]
        c='r.customer_id COLLATE pg_catalog."C" = \'customer.A\'::pg_catalog.text'
        p='r.project_id COLLATE pg_catalog."C" = \'project:Z\'::pg_catalog.text'
        self.assertLess(sql.index(c),sql.index('LIMIT 3'))
        self.assertLess(sql.index(p),sql.index('LIMIT 3'))
        for invalid in (('x','*'),('x',"p' OR 1=1"),('ALL','p'),('','p')):
            with self.assertRaisesRegex(ValueError,'fixture_read_scope_invalid'):
                a._fixed_sql(invalid)
    def test_source_run_table_needs_physical_shape_and_scoped_read_types(self):
        for variant in ('missing','view','wrong_type'):
            p,o,f=self.state()
            tables=f.data[a.Phase.CATALOG]['tables']
            if variant=='missing':del tables[a.RUN_TABLE]
            if variant=='view':tables[a.RUN_TABLE]['kind']='view'
            if variant=='wrong_type':tables[a.RUN_TABLE]['types']['project_id']='custom'
            self.deny(p,o,f)
            self.assertNotIn(a.Phase.LEDGER,[x[0] for x in f.calls])
    def test_scope_cannot_be_changed_mid_session(self):
        p,o,f=self.state()
        original=f.response
        def mutate(phase,sql):
            if phase==a.Phase.BOOTSTRAP:
                p['approved_read_scope']['project_id']='forged-new'
            return original(phase,sql)
        f.response=mutate
        self.assertEqual(self.verify(p,o,f)['sample_count'],1)
        self.assertNotIn('forged-new',f.calls[a.Phase.SAMPLE.value-1][1])

    def test_bad_role_target_or_lineage_never_emits_a_statement(self):
        p,o,f=self.state();p['restored_backup_reference_sha256']='b'*64
        self.deny(p,o,f);self.assertFalse(f.calls);self.assertFalse(f.closed)
        p,o,f=self.state();self.deny(p,p['production'],f);self.assertFalse(f.calls)
    def test_view_or_bad_local_state_stops_before_ledger_and_sample(self):
        p,o,f=self.state();f.data[a.Phase.CATALOG]['tables'][a.EXTRA_TABLE]['kind']='view'
        self.deny(p,o,f);self.assertEqual([x[0] for x in f.calls],[a.Phase.BOOTSTRAP,a.Phase.CATALOG]);self.assertTrue(f.closed)
        p,o,f=self.state();f.data[a.Phase.BOOTSTRAP]['values'][-1]=False
        self.deny(p,o,f);self.assertEqual([x[0] for x in f.calls],[a.Phase.BOOTSTRAP])
    def test_bad_ledger_relation_type_or_missing_columns_stops_before_ledger(self):
        p,o,f=self.state()
        f.data[a.Phase.CATALOG]['tables']['nico_schema_migrations']['types']['version']='custom'
        self.deny(p,o,f); self.assertNotIn(a.Phase.LEDGER,[x[0] for x in f.calls])
        p,o,f=self.state()
        f.data[a.Phase.CATALOG]['tables']['nico_schema_migrations']['columns']=[]
        self.deny(p,o,f); self.assertNotIn(a.Phase.LEDGER,[x[0] for x in f.calls])
    def test_bad_ledger_stops_before_sample_and_mock_errors_are_redacted(self):
        p,o,f=self.state();f.data[a.Phase.LEDGER]['migrations']=[]
        self.deny(p,o,f);self.assertNotIn(a.Phase.SAMPLE,[x[0] for x in f.calls])
        p,o,f=self.state();f.data[a.Phase.BOOTSTRAP]=RuntimeError('do not echo')
        self.deny(p,o,f)
    def test_psql_one_object_per_line_no_array_partial_or_noise(self):
        for bad in (b'{"rows":[]}\n',b'{"row":{}}',b'{}\n{}\n{}\n{}\n',b'warning\n'):
            p,o,f=self.state(); f.data[a.Phase.SAMPLE]=bad
            self.deny(p,o,f)
            self.assertTrue(f.closed)
    def test_output_bound_and_failed_rollback_refuse_evidence(self):
        p,o,f=self.state()
        with patch.object(a,'MAX_TRANSCRIPT',100):self.deny(p,o,f)
        p,o,f=self.state();f.data[a.Phase.ROLLBACK]['completed']=False
        self.deny(p,o,f)
        with self.assertRaisesRegex(ValueError,'^database_execution_disabled$'):a.dispatch()
