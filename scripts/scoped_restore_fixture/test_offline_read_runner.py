from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from binding import derive_synthetic_transport_binding
from test_binding import base,NOW
from test_verifier import row
import offline_read_runner as r

class StagedReadTest(unittest.TestCase):
    def state(self):
        p,o=base()
        e=json.loads((r.ROOT/'expected-schema.json').read_text())
        t={k:{'kind':'base_table','columns':v} for k,v in e['tables'].items()}
        for name,cols in r.SUPPLEMENTAL.items():
            t[name]={'kind':'base_table','columns':sorted(cols|set(t.get(name,{}).get('columns',[])))}
        frames=[dict(phase='bootstrap',session={'values':['on','15s','1s','30s','pg_catalog',True],
                     'status':'ok','transaction_status':'in_read_transaction'}),
                dict(phase='catalog_and_ledger',metadata={'schema':'public','tables':t,
                     'migrations':[dict(version=e['version'],contract_sha256=e['contract_sha256'])]}),
                dict(phase='sample',row=dict(row(),customer_id='synthetic',project_id='synthetic')), dict(phase='rollback',completed=True)]
        return p,o,frames
    def transcript(self,p,o,frames,*,digest=None):
        token='fixture:one'
        b=digest or derive_synthetic_transport_binding(p,o,now=NOW,max_age_hours=36)
        records=tuple(json.dumps(dict(x,fixture_token=token)).encode() if type(x) is dict else x for x in frames)
        return r.SyntheticTranscript(token,r.RELEASE,b,records)
    def verify(self,t,p,o):
        return r.verify_fixture(t,p,o,now=NOW,max_age_hours=36)
    def rejects(self,t,p,o):
        with self.assertRaisesRegex(ValueError,'^offline_read_fixture_rejected$') as e:
            self.verify(t,p,o)
        self.assertTrue(e.exception.__suppress_context__)
    def test_verified_decode_remains_synthetic_without_evidence_fields(self):
        p,o,f=self.state()
        answer=self.verify(self.transcript(p,o,f),p,o)
        self.assertEqual(answer,{'status':'synthetic_only','sample_count':1,
            'database_execution_enabled':False,'restore_evidence_eligible':False})
    def test_lineage_and_target_rejected_before_any_fixture_read(self):
        p,o,f=self.state(); t=self.transcript(p,o,f)
        with patch.object(r,'handle_obj') as parser:
            for key in ('backup_reference_sha256','restored_backup_reference_sha256','receipts'):
                altered=deepcopy(p); del altered[key]
                self.rejects(t,altered,o)
            changed=deepcopy(p);changed['restored_backup_reference_sha256']='f'*64
            self.rejects(t,changed,o)
            self.rejects(t,p,p['production'])
        parser.assert_not_called()
    def test_catalog_and_transaction_checked_before_sample(self):
        for mutation in ('view','wrong_schema','missing_columns','wrong_ledger','not_read_only','idle'):
            p,o,f=self.state();md=f[1]['metadata']
            if mutation=='view': md['tables'][r.EXTRA_TABLE]['kind']='view'
            if mutation=='wrong_schema': md['schema']='other'
            if mutation=='missing_columns':md['tables'][r.EXTRA_TABLE]['columns']=[]
            if mutation=='wrong_ledger':md['migrations'][0]['contract_sha256']='0'*64
            if mutation=='not_read_only':f[0]['session']['values'][0]='off'
            if mutation=='idle':f[0]['session']['transaction_status']='idle'
            with self.subTest(mutation=mutation),patch.object(r.verify,'validate_row') as sample:
                self.rejects(self.transcript(p,o,f),p,o)
                sample.assert_not_called()
    def test_unsupported_duplicate_corrupt_and_incomplete_samples(self):
        for variant in ('duplicate','corrupt','reviewed','no_finish','too_many','mixed_session','nonfinite'):
            p,o,f=self.state()
            if variant=='duplicate': f.insert(3,deepcopy(f[2]))
            if variant=='corrupt': f[2]['row']['integrity_sha256']='f'*64
            if variant=='reviewed': f[2]['row']['payload']['status']='approved'
            if variant=='no_finish': f[-1]['completed']=False
            if variant=='too_many': f[2:2]=[deepcopy(f[2])]*3
            if variant=='mixed_session':f[2]=json.dumps(dict(f[2],fixture_token='fixture:other')).encode()
            if variant=='nonfinite': f[2]=b'{"fixture_token":"fixture:one","phase":"sample","row":{"one":1e999}}'
            with self.subTest(variant=variant): self.rejects(self.transcript(p,o,f),p,o)
    def test_db_scope_and_decoded_identity_must_match_the_bound_exact_scope(self):
        for field in ('customer_id','project_id'):
            p,o,f=self.state()
            f[2]['row'][field]='other'
            with self.subTest(field=field,layer='sql columns'),patch.object(r.verify,'validate_row') as dec:
                self.rejects(self.transcript(p,o,f),p,o)
                dec.assert_not_called()
            p,o,f=self.state()
            item=f[2]['row']
            item['payload']['identity'][field]='other'
            _, record, _, _=r.verify.load_code_offline()
            # Record still passes the ordinary integrity check; mismatch is scope.
            item['payload']['integrity_sha256']=record['_record_hash'](item['payload'])
            item['integrity_sha256']=item['payload']['integrity_sha256']
            other=deepcopy(item);other[field]='other'
            r.verify.validate_row(other,expected_scope=(other['customer_id'],other['project_id']))
            with self.subTest(field=field,layer='decoded canonical identity'):
                self.rejects(self.transcript(p,o,f),p,o)
    def test_changed_bound_scope_rejects_before_parsing(self):
        p,o,f=self.state(); t=self.transcript(p,o,f)
        p['approved_read_scope']['project_id']='changed'
        with patch.object(r,'handle_obj') as parser:
            self.rejects(t,p,o)
            parser.assert_not_called()
    def test_oversize_frames_and_disabled_dispatch(self):
        p,o,f=self.state(); t=self.transcript(p,o,f)
        with patch.object(r,'MAX_TRANSCRIPT',10):self.rejects(t,p,o)
        with patch.object(r,'MAX_ROW',10):self.rejects(t,p,o)
        with self.assertRaisesRegex(ValueError,'^database_execution_disabled$'):r.dispatch()
