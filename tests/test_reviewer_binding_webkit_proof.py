from pathlib import Path
import importlib.util
import pytest
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('reviewer_webkit',ROOT/'scripts/reviewer_binding_webkit_proof.py')
proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)

@pytest.mark.parametrize('method,url,expected',[
 ('GET',proof.ORIGIN+proof.API,'synthetic'),
 ('POST',proof.ORIGIN+proof.API,'blocked'),
 ('DELETE',proof.ORIGIN+proof.API,'blocked'),
 ('GET','https://app.nicoaudit.com'+proof.API,'blocked'),
 ('GET',proof.ORIGIN+'/api/nico/assessment/start','blocked'),
 ('GET',proof.ORIGIN+proof.API+'?other=1','blocked'),
 ('GET',proof.ORIGIN+'/api/nico/assessment/comprehensive-run/real/review-work','blocked'),
 ('GET',proof.ORIGIN+'/_next/static/chunks/app.js','asset'),
 ('GET',proof.ORIGIN+'/operations/reviewer-queue?lang=en','asset'),
 ('POST',proof.ORIGIN+'/_next/static/chunks/app.js','blocked'),
 ('GET','http://127.0.0.1:3107.evil.invalid/operations/reviewer-queue','blocked'),
])
def test_read_only_local_allowlist(method,url,expected):
 assert proof.request_kind(method,url)==expected

@pytest.mark.parametrize('scenario',proof.SCENARIOS)
def test_synthetic_cases_keep_human_gates(scenario):
 p=proof.fixture('a'*40,scenario)
 assert p['candidate_count']==len(p['candidates'])==len(p['review_assistance']['queue'])
 assert p['human_review_required'] and not p['client_delivery_allowed'] and not p['ready_for_final_approval']
 source=p['review_assistance']['source_investigation']['packets'][0]
 if scenario=='qualified':assert source['lexical_binding']['version']=='nico.reviewer-lexical-binding.v1'
 if scenario=='unqualified':assert 'lexical_binding' not in source
 if scenario=='duplicate':assert len(p['candidates'])==2 and p['candidates'][0]==p['candidates'][1]
 if scenario=='stale':assert source['lexical_binding']['version']=='stale'


def test_workflow_reuses_existing_job_with_fixed_bounds_and_no_dispatch():
 import yaml
 data=yaml.safe_load((ROOT/'.github/workflows/ios-webkit-paint-proof.yml').read_text())
 job=data['jobs']['contract']
 assert job['runs-on']=='ubuntu-latest' and job['timeout-minutes']==25
 steps={s['name']:s for s in job['steps']}
 build=steps['Build real frontend for isolated reviewer layout']
 browser=steps['Verify synthetic reviewer lexical binding in hosted WebKit']
 artifact=steps['Retain synthetic reviewer layout evidence']
 assert build['timeout-minutes']==8 and browser['timeout-minutes']==4 and artifact['timeout-minutes']==2
 assert '${{ github.sha }}' in browser['run']
 assert artifact['with']['retention-days']==1
 assert 'secrets' not in str([build,browser,artifact])
 assert 'workflow_dispatch' not in (ROOT/'.github/workflows/ios-webkit-paint-proof.yml').read_text().split('jobs:')[0]


@pytest.mark.parametrize('status,rules,margin,ok',[(200,5,'0px',True),(404,5,'0px',False),(None,5,'0px',False),(200,0,'0px',False),(200,5,'8px',False)])
def test_failed_css_cannot_qualify(status,rules,margin,ok):
 url=proof.ORIGIN+'/_next/static/css/app.css'
 args=([{'href':url,'rules':rules}],{url:status},{'bodyMargin':margin,'boxSizing':'border-box'})
 if ok:proof.validate_styles(*args)
 else:
  with pytest.raises(AssertionError):proof.validate_styles(*args)


def test_final_artifact_cap_counts_logs_and_manifest(tmp_path,monkeypatch):
 raw=tmp_path/'raw';raw.mkdir();(raw/'server.log').write_bytes(b'x'*40)
 monkeypatch.setattr(proof,'TOTAL_ARTIFACT_BYTES',50)
 with pytest.raises(RuntimeError,match='total exceeds'):
  proof.finalize_artifacts(raw,tmp_path/'publish',{'complete':False,'reason':'synthetic failure'})
 assert not (tmp_path/'publish').exists()
 monkeypatch.setattr(proof,'TOTAL_ARTIFACT_BYTES',500)
 proof.finalize_artifacts(raw,tmp_path/'publish',{'complete':False})
 assert (tmp_path/'publish/server.log').read_bytes()==b'x'*40


def test_environment_drops_credentials_and_rejects_dotenv(tmp_path,monkeypatch):
 from reviewer_proof_environment import environment
 (tmp_path/'apps/web').mkdir(parents=True)
 monkeypatch.setenv('GITHUB_TOKEN','synthetic-secret');monkeypatch.setenv('NICO_API_URL','https://production.invalid')
 env=environment(tmp_path,'server')
 assert 'GITHUB_TOKEN' not in env and 'NICO_API_URL' not in env
 assert env['NICO_REVIEWER_PROOF_NETWORK']=='server'
 (tmp_path/'apps/web/.env.local').write_text('synthetic')
 with pytest.raises(RuntimeError,match='dotenv'):environment(tmp_path,'server')


@pytest.mark.parametrize('failure_step',[None,0,1])
def test_npm_configs_empty_distinct_alive_and_cleaned(tmp_path,monkeypatch,failure_step):
 import subprocess
 import reviewer_proof_environment as build_env
 (tmp_path/'apps/web').mkdir(parents=True)
 monkeypatch.setenv('NPM_CONFIG_USERCONFIG','/synthetic/ambient-user')
 monkeypatch.setenv('NPM_CONFIG_GLOBALCONFIG','/synthetic/ambient-global')
 monkeypatch.setenv('NPM_TOKEN','synthetic-secret')
 calls=[];paths=[]
 def run(command,**kwargs):
  env=kwargs['env'];current=[Path(env[k]) for k in ('NPM_CONFIG_USERCONFIG','NPM_CONFIG_GLOBALCONFIG')]
  assert current[0]!=current[1] and all(p.read_bytes()==b'' for p in current)
  assert 'NPM_TOKEN' not in env
  assert kwargs['check'] is True and kwargs['timeout']==240
  assert kwargs['cwd']==tmp_path/'apps/web'
  if calls:
   assert current==paths
   assert env['NICO_REVIEWER_PROOF_NETWORK']=='build' and '--require=' in env['NODE_OPTIONS']
   assert command==['node','node_modules/next/dist/bin/next','build']
  else:
   paths.extend(current)
   assert 'NODE_OPTIONS' not in env and 'NICO_REVIEWER_PROOF_NETWORK' not in env
   assert command==['npm','ci','--ignore-scripts','--no-audit','--no-fund']
  calls.append(command)
  if len(calls)-1==failure_step:raise subprocess.CalledProcessError(1,command)
 monkeypatch.setattr(build_env.subprocess,'run',run)
 if failure_step is None:build_env.build(tmp_path)
 else:
  with pytest.raises(subprocess.CalledProcessError):build_env.build(tmp_path)
 assert len(calls)==(2 if failure_step is None else failure_step+1)
 assert paths and all(not p.exists() and not p.parent.exists() for p in paths)


def test_installed_npm_configuration_regression_without_install(monkeypatch):
 import subprocess
 import reviewer_proof_environment as build_env
 real_run=subprocess.run
 # The process guard rejects outbound sockets; only npm --version executes.
 guarded=build_env.environment(ROOT,'server')
 broken={**guarded,'NPM_CONFIG_USERCONFIG':'/dev/null','NPM_CONFIG_GLOBALCONFIG':'/dev/null'}
 result=real_run(['npm','--version'],cwd=ROOT/'apps/web',env=broken,capture_output=True,text=True,timeout=20)
 assert result.returncode!=0 and 'double-loading config' in result.stderr
 observed=[]
 def probe(command,**kwargs):
  env={**kwargs['env'],'NODE_OPTIONS':guarded['NODE_OPTIONS'],'NICO_REVIEWER_PROOF_NETWORK':'server'}
  result=real_run(['npm','--version'],cwd=kwargs['cwd'],env=env,capture_output=True,text=True,timeout=20)
  assert result.returncode==0,result.stderr
  assert result.stdout.strip()
  observed.append(command)
 monkeypatch.setattr(build_env.subprocess,'run',probe)
 build_env.build(ROOT)
 assert len(observed)==2
