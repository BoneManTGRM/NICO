import unittest
from no_child_design import RELEASE, REQUIRED, dispatch, offline_plan, verify_fixture_bootstrap

class NoChildTests(unittest.TestCase):
    def good(self):
        return dict(release=RELEASE,user='fixture_reader',database='fixture_restore',
                    peer='fixture_postgres',claims={k:True for k in REQUIRED})
    def test_fixed_only_local_secretless_parameters_and_disabled(self):
        p=offline_plan(**self.good()); db=p['libpq_fixture_parameters']
        self.assertEqual(db['host'],'/var/run/postgresql')
        self.assertEqual(db['require_auth'],'none')
        self.assertEqual(db['passfile'],'/dev/null')
        self.assertEqual(db['gssencmode'],'disable')
        self.assertFalse(p['expand_dbname'])
        self.assertFalse(p['live_execution_enabled'])
        self.assertFalse({'password','service','hostaddr','sslkey'} & db.keys())
        self.assertIn('READ ONLY',p['fixed_bootstrap_statements'][0])
        self.assertEqual(p['fixed_bootstrap_statements'][-1],'ROLLBACK')
        with self.assertRaisesRegex(ValueError,'^database_execution_disabled$'):dispatch()
    def test_missing_claims_and_truthiness_refused(self):
        for key in REQUIRED:
            for val in (False,1,None):
                d=self.good();d['claims'][key]=val
                with self.assertRaisesRegex(ValueError,'^isolation_preflight_required$'):offline_plan(**d)
    def test_no_conninfo_semicolon_hostname_or_expansion_via_identity(self):
        for field in ('user','database','peer'):
            for value in ('postgresql://example','host=example','bad;sql','a.example','x/y','x y','a'*64):
                d=self.good();d[field]=value
                with self.assertRaisesRegex(ValueError,'^socket_identity_invalid$'):offline_plan(**d)
    def test_release_mismatch_refused(self):
        d=self.good();d['release']='0'*40
        with self.assertRaisesRegex(ValueError,'^source_release_mismatch$'):offline_plan(**d)
    def test_bootstrap_shape_typed_status_timeouts_and_local_required(self):
        example=('on','15s','1s','30s','pg_catalog',True)
        options=dict(session_status='ok',transaction_status='in_read_transaction')
        result=verify_fixture_bootstrap(example,**options)
        self.assertFalse(result['restore_evidence_eligible'])
        for idx,value in enumerate(('off','0','0','0','public',1)):
            wrong=example[:idx]+(value,)+example[idx+1:]
            with self.assertRaisesRegex(ValueError,'^fixture_session_state_invalid$'):
                verify_fixture_bootstrap(wrong,**options)
        with self.assertRaisesRegex(ValueError,'^fixture_session_state_invalid$'):
            verify_fixture_bootstrap(example,session_status='ok',transaction_status='idle')
