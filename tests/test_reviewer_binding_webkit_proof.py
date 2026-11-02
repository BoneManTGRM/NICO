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
