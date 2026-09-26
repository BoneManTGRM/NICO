"""Data-only validation of immutable GitHub qualification artifacts; no native code runs."""
from pathlib import Path
import base64, hashlib, json, sys
BASE=Path(__file__).resolve().parents[1]
REPO=BASE/'NICO'
sys.path.insert(0,str(REPO))
from nico.assessment_cpp_full_project import _database, _json
from nico.assessment_cpp_project_snapshot import validate_project_snapshot
from nico.assessment_cpp_project_compiler import project_compiler_request, validate_project_compiler
from nico.assessment_cpp_static_environment import environment_request, validate_environment
from nico.assessment_cpp_project_static import project_static_request, validate_project_static
from nico.assessment_cpp_clang_fallback import clang_fallback_request, validate_clang_fallback, merge_static_analysis
from nico.assessment_cpp_runtime_scope import validate_retained_runtime
from nico.assessment_worker_receipts import canonical_bytes
root=BASE/'recovered/native-36272142582/cpp-baseline-qualification'
r=json.loads((root/'receipt.json').read_bytes());p=r['probe'];targets=r['source']['targets']
def artifact(prefix):
 paths=list((root/'artifacts').glob(prefix+'-*.json'))
 assert len(paths)==1
 raw=paths[0].read_bytes();sha=hashlib.sha256(raw).hexdigest()
 assert paths[0].name.endswith('-'+sha+'.json')
 return raw
rawdb=base64.b64decode(p['compilation_database'],validate=True)
assert hashlib.sha256(rawdb).hexdigest()==p['compilation_database_sha256']
contexts=_database(rawdb,None,'/work/build',nested=True,source_targets=targets)
snapshot=validate_project_snapshot(_json(artifact('project-generated-context')),contexts)
creq=project_compiler_request(rawdb,targets,snapshot,extended_budget=True)
craw=artifact('project-compiler-evidence');compiler=validate_project_compiler(craw,creq)
# Static analysis runs in the release-owned image recorded by this probe.
ereq=environment_request(creq,craw,p['project_static_stage']['image_config_digest'])
env=validate_environment(artifact('project-static-environment'),ereq)
sreq=project_static_request(rawdb,targets,snapshot,craw,extended_compiler_budget=True,environment=env)
primary=validate_project_static(artifact('project-static-evidence'),sreq)
freq=clang_fallback_request(sreq,primary,extended_budget=True,contention_aware=True)
fallback=validate_clang_fallback(artifact('project-static-clang-fallback'),freq,sreq)
analysis=merge_static_analysis(primary,fallback)
scope=json.loads((REPO/'tests/fixtures/cpp/bitcoin-runtime-scope.json').read_bytes())
runtime=validate_retained_runtime(artifact('project-runtime-evidence'),targets,p['project_options'],scope)
assert runtime['summary']==p['runtime_summary']
for key in ['required_contexts','attempted_contexts','analyzed_contexts','findings','limitations','modeled_inputs']:
 actual=analysis.get(key) or []
 assert len(actual)==p['project_static'][key+'_count'], key
 assert hashlib.sha256(canonical_bytes(actual)).hexdigest()==p['project_static'][key+'_sha256'], key
# Bind every extracted byte to the immutable original archive before acceptance.
import zipfile
zip_path=Path('/workspace/scratch/e740d54a52d0/attachments/13709446-1cdb-4800-8ace-4f6889e20574/native-36272142582.zip')
assert hashlib.sha256(zip_path.read_bytes()).hexdigest() == 'd79dd0536821971869309baf3f521769657f1cf41994544638c8bdce043d0af9'
archive_hashes={}
with zipfile.ZipFile(zip_path) as archive:
    for member in archive.infolist():
        if member.is_dir(): continue
        name=member.filename
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        raw=archive.read(member)
        extracted=root.parent/name
        assert extracted.read_bytes()==raw, name
        archive_hashes[name]=hashlib.sha256(raw).hexdigest()
assert r['producer_source_sha']=='a65f40441f597fce702bdbce37332651780fa3c7'
assert compiler == {key:value for key,value in p['project_compiler'].items() if key!='artifact'}
from nico.assessment_cpp_collection import validate_baseline_collection, validate_project_collection
from nico.assessment_cpp_project_snapshot import _stable_bytes, PROJECT_GENERATED_STREAM_LIMIT
baseline_raw=(REPO/'tests/fixtures/cpp/bitcoin-baseline-execution.json').read_bytes()
manifest_raw=(REPO/'tests/fixtures/cpp/bitcoin-configuration-benchmark.json').read_bytes()
scope_raw=(REPO/'tests/fixtures/cpp/bitcoin-runtime-scope.json').read_bytes()
for raw,key in [(baseline_raw,'execution_contract_sha256'),(manifest_raw,'benchmark_sha256'),(scope_raw,'runtime_scope_sha256')]:
    assert hashlib.sha256(raw).hexdigest()==r[key]
read_artifact=lambda ref: _stable_bytes(root.absolute(),ref['path'],PROJECT_GENERATED_STREAM_LIMIT)
baseline=validate_baseline_collection(p,_json(baseline_raw),read_artifact)
receipt_before=(root/'receipt.json').read_bytes()
try:
    validate_project_collection(r,read_artifact,manifest_raw=manifest_raw,baseline_raw=baseline_raw,
        scope_raw=scope_raw,producer_source_sha=r['producer_source_sha'],image=p['image_config_digest'])
except ValueError as exc:
    decision={'collection_complete':False,'error':str(exc)}
else:
    raise AssertionError('Incomplete ASan timeout was unexpectedly accepted')
assert decision['error']=='worker_runtime_collection_incomplete'
assert (root/'receipt.json').read_bytes()==receipt_before
assert json.loads(receipt_before)==r
summary={
 'schema':'nico.native-data-revalidation.v2','run_id':36272142582,
 'collection_decision':decision,
 'baseline':{k:len(v) for k,v in baseline.items()},
 'archive_member_sha256':archive_hashes,
 'original_receipt_sha256':hashlib.sha256(receipt_before).hexdigest(),
 'original_receipt_unchanged':True,
 'reconstructed_runtime_summary_identical':True,
 'validation_module_sha256':{name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in ('nico/assessment_cpp_collection.py','nico/assessment_cpp_collection_transport.py','nico/assessment_cpp_runtime_collection.py','scripts/qualify_cpp_project_configuration.py')},
 'source':{k:r['source'][k] for k in ['repository','commit_sha','tree_sha']},
 'source_file_sha256':targets['src/streams.cpp'],
 'artifact_sha256':hashlib.sha256(Path('/workspace/scratch/e740d54a52d0/attachments/13709446-1cdb-4800-8ace-4f6889e20574/native-36272142582.zip').read_bytes()).hexdigest(),
 'compiler':{k:len(compiler[k]) for k in ['required_contexts','checked_contexts']},
 'static':{k:(len(analysis[k]) if isinstance(analysis[k],list) else analysis[k]) for k in ['required_contexts','analyzed_contexts','complete']},
 'functional':{k:len(v) if isinstance(v,list) else v for k,v in runtime['summary']['functional'].items()},
 'sanitizers':[{k:len(v) if isinstance(v,list) else v for k,v in s.items()} for s in runtime['summary']['sanitizers']],
 'runtime_error':runtime['summary']['error'],'runtime_complete':runtime['summary']['complete'],
 'first_failure_operation':runtime['summary'].get('first_failure_operation'),
 'failure_operation':runtime['summary'].get('failure_operation'),
 'fuzz':runtime['summary']['fuzz'],
 'static_observations':len(analysis['findings']),
 'observations_are_not_confirmed_vulnerabilities':True,
 'analyzer_header_coverage_verified':p['project_static']['analyzer_header_coverage_verified'],
 'new_native_execution':False,'production_qualified':False,
 'validation_base_source':'dc2521cb',
 'producer_source_sha':r['producer_source_sha'],
 'validation_local_change':'CLI artifact root made absolute without resolving symlinks' ,
}
(BASE/'validation/native-36272142582-revalidation.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
