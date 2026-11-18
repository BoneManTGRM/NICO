import base64,copy,hashlib,json,unittest,zlib
import verify as v

CODEC, RECORD, STORE, HUMAN = v.load_code_offline()

def row():
 h={'artifact_schema':HUMAN['VERSION'],'modules':{}}
 for name in HUMAN['MODULES']:
  m={'module_id':name};m['module_sha256']=HUMAN['_canonical_hash'](m);h['modules'][name]=m
 h['human_evidence_sha256']=HUMAN['_canonical_hash'](h)
 r={'artifact_schema':RECORD['VERSION'],'service_id':'comprehensive',
    'identity':{k:'synthetic' for k in ['run_id','repository','commit_sha','evidence_ledger_id','customer_id','project_id','assessment_depth','report_language']},
    'human_evidence':h,'status':'ready','revision':1,'human_review_required':True,
    'client_delivery_allowed':False,'completed_stages':[],'progress_percent':0,'terminal':False}
 r['integrity_sha256']=RECORD['_record_hash'](r)
 return {'payload':r,'run_id':'synthetic','revision':1,'integrity_sha256':r['integrity_sha256'],
         'event_count':0,'chain_sha256':STORE['_review_history_sha256']([]),
         'customer_id':'synthetic','project_id':'synthetic'}

class Checks(unittest.TestCase):
 def test_plain_valid_and_immutable(self):
  r=row();before=copy.deepcopy(r);self.assertEqual(v.validate_row(r,expected_scope=('synthetic','synthetic'))[0],'synthetic');self.assertEqual(r,before)
 def test_compressed_valid(self):
  r=row();raw=json.dumps(r['payload'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
  r['payload']={CODEC.ENVELOPE_KEY:{'schema':CODEC.STORAGE_SCHEMA,'encoding':'zlib+base64','size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'data':base64.b64encode(zlib.compress(raw)).decode()}}
  self.assertEqual(v.validate_row(r,expected_scope=('synthetic','synthetic'))[0],'synthetic')
  r['payload'][CODEC.ENVELOPE_KEY]['sha256']='0'*64
  with self.assertRaises(ValueError):v.validate_row(r,expected_scope=('synthetic','synthetic'))
 def test_corrupt_integrity(self):
  r=row();r['payload']['revision']=2
  with self.assertRaises(ValueError):v.validate_row(r,expected_scope=('synthetic','synthetic'))
 def test_corrupt_commitment(self):
  r=row();r['chain_sha256']='0'*64
  with self.assertRaises(ValueError):v.validate_row(r,expected_scope=('synthetic','synthetic'))
 def test_reviewed_fails_closed(self):
  for field,value in [('status','approved'),('client_delivery_allowed',True),('review_decision',{}),('accepted_edition',{}),('review_history',[{}])]:
   r=row();r['payload'][field]=value
   with self.assertRaisesRegex(ValueError,'outside_verifier_scope'):v.validate_row(r,expected_scope=('synthetic','synthetic'))
 def test_human_hash_invalid_even_if_outer_rehashed(self):
  r=row();r['payload']['human_evidence']['modules']={};r['payload']['integrity_sha256']=RECORD['_record_hash'](r['payload']);r['integrity_sha256']=r['payload']['integrity_sha256']
  with self.assertRaises(ValueError):v.validate_row(r,expected_scope=('synthetic','synthetic'))
 def test_readiness_gate_preserved(self):
  r=row();r['payload']['human_review_required']=False;r['payload']['integrity_sha256']=RECORD['_record_hash'](r['payload']);r['integrity_sha256']=r['payload']['integrity_sha256']
  with self.assertRaises(ValueError):v.validate_row(r,expected_scope=('synthetic','synthetic'))
 def test_expansion_bound(self):
  r=row();r['payload']={CODEC.ENVELOPE_KEY:{'size_bytes':v.MAX_EXPANDED+1}}
  with self.assertRaisesRegex(ValueError,'expanded_size_limit'):v.validate_row(r,expected_scope=('synthetic','synthetic'))
 def test_snapshot_success_and_missing_schema(self):
  e=json.loads((v.ROOT/'expected-schema.json').read_text());s={'read_only':'on','schema':[{'table':t,'column':c} for t,cs in e['tables'].items() for c in cs], 'migrations':[{'version':e['version'],'contract_sha256':e['contract_sha256']}],'rows':[row()]}
  self.assertEqual(v.verify_synthetic_snapshot(s,expected_scope=('synthetic','synthetic'))['sample_count'],1)
  s['schema']=[]
  with self.assertRaisesRegex(ValueError,'required_schema_missing'):v.verify_synthetic_snapshot(s,expected_scope=('synthetic','synthetic'))
 def test_nonreadonly_fails(self):
  with self.assertRaisesRegex(ValueError,'transaction_not_readonly'):v.verify_synthetic_snapshot({'read_only':'off'},expected_scope=('synthetic','synthetic'))

class ConnectionBoundary(unittest.TestCase):
 def test_identifiers_and_fixed_socket(self):
  for parent in ({'POSTGRES_USER':'postgres','POSTGRES_DB':'nico_restore_1'}, {'PGUSER':'nico_1','PGDATABASE':'_restore'}):
   cmd,env=v.local_psql_command(parent)
   self.assertEqual(cmd[0],'/usr/bin/psql')
   self.assertEqual(cmd[cmd.index('-h')+1],'/var/run/postgresql')
   self.assertEqual(cmd[cmd.index('-p')+1],'5432')
   self.assertIn('-w',cmd)
 def test_uri_conninfo_and_nonidentifiers_rejected(self):
  bad=('postgresql://example/db','postgres://example/db','host=example dbname=nico',
       'service=other','nico user=other','nico\n','-other','a/b','a.b','a-b','a'*64,'é','nico\x00')
  for key in ('POSTGRES_DB','POSTGRES_USER','PGDATABASE','PGUSER'):
   for value in bad:
    parent={'PGUSER':'postgres','PGDATABASE':'nico'};parent[key]=value
    with self.subTest(key=key,value=value):
     with self.assertRaisesRegex(ValueError,'local_database_identity_invalid'):v.local_psql_command(parent)
 def test_ambient_libpq_and_loader_overrides_not_forwarded(self):
  parent={'POSTGRES_USER':'postgres','POSTGRES_DB':'nico',
   'PGHOST':'remote','PGHOSTADDR':'1.2.3.4','PGPORT':'6543','PGSERVICE':'other',
   'PGSERVICEFILE':'/other','PGSYSCONFDIR':'/other','PGOPTIONS':'-c default_transaction_read_only=off',
   'PGPASSFILE':'/other','PGPASSWORD':'not-a-real-secret','DATABASE_URL':'postgres://example',
   'HOME':'/other','LD_PRELOAD':'/other','PATH':'/other'}
  cmd,env=v.local_psql_command(parent)
  self.assertEqual(set(env),{'PATH','LANG','PGCONNECT_TIMEOUT','PGOPTIONS','PGPASSFILE'})
  self.assertEqual(env['PGOPTIONS'],'-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=1000')
  self.assertEqual(env['PGPASSFILE'],'/nonexistent/nico-restore-no-password-file')
  self.assertEqual(env['PATH'],'/usr/bin:/bin')
 def test_missing_identity_rejected(self):
  with self.assertRaisesRegex(ValueError,'local_database_identity_missing'):v.local_psql_command({})

if __name__=='__main__':unittest.main()
