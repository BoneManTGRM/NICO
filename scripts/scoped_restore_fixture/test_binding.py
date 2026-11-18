from copy import deepcopy
from datetime import datetime, timezone
import subprocess
import sys
import unittest
from uuid import UUID

from binding import ATTESTATIONS, IDENTIFIERS, RELEASE, validate_binding, derive_synthetic_transport_binding

NOW=datetime(2026,11,18,10,0,tzinfo=timezone.utc)
def identity(start):
    return {k:str(UUID(int=i)) for i,k in enumerate(IDENTIFIERS,start)}
def base():
    p={'release': RELEASE,'production':identity(1),'target':identity(11),
       'backup_reference_sha256':'a'*64,'restored_backup_reference_sha256':'a'*64,
       'backup_completed_utc':'2026-11-18T06:00:00Z','pitr_target_utc':'2026-11-18T06:01:00Z',
       'restore_completed_utc':'2026-11-18T09:00:00Z','verified_utc':'2026-11-18T09:58:00Z',
       'receipts':{k:'b'*64 for k in ATTESTATIONS},
       'approved_read_scope':{'customer_id':'synthetic','project_id':'synthetic','receipt_sha256':'c'*64}}
    return p,deepcopy(p['target'])

class BindingTest(unittest.TestCase):
    def test_valid_is_never_executable_or_provider_attested(self):
        p,o=base()
        r=validate_binding(p,o,now=NOW,max_age_hours=36)
        self.assertFalse(r['database_execution_enabled'])
        self.assertFalse(r['provider_attestations_verified_by_program'])
    def test_cli_refuses_execution(self):
        r=subprocess.run([sys.executable,'-B','binding.py','attacker-injected'],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('target_unbound_database_execution_disabled',r.stdout)
        self.assertNotIn('attacker',r.stdout+r.stderr)
    def test_collision_in_all_target_passive_identity_fields(self):
        for name in ('service','deployment','volume'):
            with self.subTest(name=name):
                p,o=base(); o[name]=p['target'][name]=p['production'][name]
                with self.assertRaisesRegex(ValueError,'production_boundary_collision'):
                    validate_binding(p,o,now=NOW,max_age_hours=36)
    def test_same_environment_is_not_a_release_identity_but_isolation_still_required(self):
        p,o=base()
        for k in ('project','environment'):
            p['target'][k]=o[k]=p['production'][k]
        self.assertFalse(validate_binding(p,o,now=NOW,max_age_hours=36)['database_execution_enabled'])
        del p['receipts']['network_isolation']
        with self.assertRaisesRegex(ValueError,'attestation_missing'):
            validate_binding(p,o,now=NOW,max_age_hours=36)
    def test_missing_receipt_keys_never_default(self):
        for key in ATTESTATIONS:
            with self.subTest(key=key):
                p,o=base(); del p['receipts'][key]
                with self.assertRaisesRegex(ValueError,'attestation_missing'):
                    validate_binding(p,o,now=NOW,max_age_hours=36)
    def test_missing_and_conflicting_runtime_identity(self):
        for key in IDENTIFIERS:
            for action in ['delete','replace']:
                with self.subTest(key=key,action=action):
                    p,o=base()
                    if action=='delete': del o[key]
                    else: o[key]=str(UUID(int=30))
                    with self.assertRaisesRegex(ValueError,'identity_missing|runtime_target_mismatch'):
                        validate_binding(p,o,now=NOW,max_age_hours=36)
    def test_due_to_timing_and_lineage_no_stale_reuse(self):
        for key,value,error in [
            ('backup_completed_utc','2026-11-15T06:00:00Z','backup_stale'),
            ('pitr_target_utc','2026-11-18T05:59:00Z','chronology_invalid'),
            ('restore_completed_utc','2026-11-18T11:00:00Z','chronology_invalid'),
            ('verified_utc','2026-11-18T09:01:00Z','target_verification_stale'),
            ('restored_backup_reference_sha256','c'*64,'restore_lineage_mismatch'),
            ('backup_reference_sha256','secret-attempt','backup_reference_invalid'),
            ('release','0'*40,'release_mismatch'),
        ]:
            with self.subTest(key=key):
                p,o=base(); p[key]=value
                with self.assertRaisesRegex(ValueError,error):
                    validate_binding(p,o,now=NOW,max_age_hours=36)
    def test_binding_digest_can_only_follow_full_structural_validation(self):
        p,o=base()
        one=derive_synthetic_transport_binding(p,o,now=NOW,max_age_hours=36)
        self.assertEqual(len(one),64)
        p['receipts'][ATTESTATIONS[0]]='f'*64
        self.assertNotEqual(one,derive_synthetic_transport_binding(p,o,now=NOW,max_age_hours=36))
        o['service']=str(UUID(int=50))
        with self.assertRaisesRegex(ValueError,'runtime_target_mismatch'):
            derive_synthetic_transport_binding(p,o,now=NOW,max_age_hours=36)
    def test_scope_required_exact_and_review_receipt_bound(self):
        p,o=base()
        without=deepcopy(p); del without['approved_read_scope']
        with self.assertRaisesRegex(ValueError,'binding_shape_invalid'):
            validate_binding(without,o,now=NOW,max_age_hours=36)
        for bad in ('','*','%','any','ALL',"x' OR '1'='1",'x\n',True,'x'*129):
            with self.subTest(bad=bad):
                q=deepcopy(p);q['approved_read_scope']['project_id']=bad
                with self.assertRaisesRegex(ValueError,'read_scope_invalid'):
                    validate_binding(q,o,now=NOW,max_age_hours=36)
        original=derive_synthetic_transport_binding(p,o,now=NOW,max_age_hours=36)
        for key,value in (('customer_id','other'),('project_id','other'),('receipt_sha256','d'*64)):
            q=deepcopy(p);q['approved_read_scope'][key]=value
            self.assertNotEqual(derive_synthetic_transport_binding(q,o,now=NOW,max_age_hours=36),original)
        p['approved_read_scope']['receipt_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'read_scope_receipt_invalid'):
            validate_binding(p,o,now=NOW,max_age_hours=36)

    def test_unbound_and_unverified_policy(self):
        p,o=base()
        for policy in (None,0,True,169):
            with self.subTest(policy=policy):
                with self.assertRaisesRegex(ValueError,'current_policy_unverified'):
                    validate_binding(p,o,now=NOW,max_age_hours=policy)
        with self.assertRaisesRegex(ValueError,'binding_unbound'):
            validate_binding(None,o,now=NOW,max_age_hours=36)
