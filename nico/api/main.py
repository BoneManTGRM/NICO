import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from nico.cli import scan_test_lab, scan_drift_demo, run_scan, Store, generate_reports, verify_latest
from nico.hosted_assessment import run_github_assessment
from nico.service_workflows import COVERAGE_TARGETS, build_mid_assessment, build_retainer_ops


_LAST_HOSTED_ASSESSMENT = {}
_LAST_MID_ASSESSMENT = {}
_LAST_RETAINER_OPS = {}


def cors_origins():
    configured = os.getenv('NICO_CORS_ORIGINS', '')
    origins = [origin.strip() for origin in configured.split(',') if origin.strip()]
    default_origins = [
        'http://localhost:3000',
        'https://app.nicoaudit.com',
        'https://nicoaudit.vercel.app',
    ]
    return origins or default_origins


class LocalScanRequest(BaseModel): path: str
class PolicyLevelRequest(BaseModel): level: int
class GithubAssessmentRequest(BaseModel):
    repository: str
    authorized: bool = False
    client_name: str = ''
    project_name: str = ''
    assessment_mode: str = 'express'
    timeframe_days: int = 180


class MidAssessmentRequest(BaseModel):
    authorized: bool = False
    client_name: str = ''
    project_name: str = ''
    qa_evidence: str = ''
    parity_notes: str = ''
    stakeholder_notes: str = ''
    roadmap_notes: str = ''
    known_risks: str = ''


class RetainerOpsRequest(BaseModel):
    authorized: bool = False
    client_name: str = ''
    project_name: str = ''
    commit_summary: str = ''
    pr_summary: str = ''
    issue_summary: str = ''
    blockers: str = ''
    release_notes: str = ''
    roadmap_notes: str = ''


app=FastAPI(title='NICO API',version='0.4.0',description='Local-first and hosted defensive technical assessment API')
app.add_middleware(CORSMiddleware,allow_origins=cors_origins(),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])


@app.get('/health')
def health():
    return {
        'status':'ok',
        'system':'NICO',
        'mode':'local-first-hosted-ready',
        'coverage_targets': COVERAGE_TARGETS,
        'workflows': {
            'express': bool(_LAST_HOSTED_ASSESSMENT),
            'mid': bool(_LAST_MID_ASSESSMENT),
            'retainer': bool(_LAST_RETAINER_OPS),
        },
        'cors_origins': cors_origins(),
    }


@app.get('/targets')
def targets():
    return {
        'status': 'ok',
        'coverage_targets': COVERAGE_TARGETS,
        'truth_rules': [
            'Evidence-bound scoring only',
            'Missing evidence is marked unavailable',
            'Client delivery requires human review',
            'Production-impacting actions require human approval',
        ],
        'workflow_endpoints': [
            'POST /assessment/github',
            'POST /assessment/mid',
            'POST /retainer/ops',
        ],
    }


@app.post('/scan/test-lab')
def api_scan_test_lab(): return scan_test_lab()
@app.post('/scan/drift-demo')
def api_scan_drift_demo(): return scan_drift_demo()
@app.post('/scan/local')
def api_scan_local(req:LocalScanRequest):
    if not req.path: raise HTTPException(400,'path required')
    return run_scan(req.path)
@app.get('/scans/latest')
def latest_scan(): return Store().latest_scan()
@app.get('/findings')
def findings(): return Store().payloads('findings')
@app.get('/findings/{finding_id}')
def finding(finding_id:str):
    for f in Store().payloads('findings'):
        if f.get('id')==finding_id: return f
    raise HTTPException(404,'finding not found')
@app.get('/drift')
def drift(): return Store().payloads('drift_events')
@app.get('/repairs')
def repairs(): return Store().payloads('repairs')
@app.get('/repairs/{repair_id}')
def repair(repair_id:str):
    for r in Store().payloads('repairs'):
        if r.get('id')==repair_id: return r
    raise HTTPException(404,'repair not found')
@app.get('/verification/latest')
def verification_latest(): return verify_latest()
@app.post('/verification/latest')
def verification_post(): return verify_latest()
@app.get('/memory')
def memory(): return Store().payloads('memory')
@app.get('/reports')
def reports(): return Store().rows('reports')
@app.get('/reports/latest')
def report_latest():
    rows=Store().rows('reports'); return rows[0] if rows else {}
@app.post('/reports/generate')
def report_generate(): return generate_reports()
@app.get('/policy')
def policy(): return Store().policy()
@app.post('/policy/autonomy-level')
def set_policy(req:PolicyLevelRequest):
    s=Store(); p=s.policy(); p['autonomy_level']=max(0,min(5,int(req.level))); s.save_policy(p); s.audit('policy.autonomy_level',{'level':p['autonomy_level']}); return p
@app.get('/audit-log')
def audit_log(): return Store().rows('audit_log')


@app.post('/assessment/github')
def hosted_github_assessment(req: GithubAssessmentRequest):
    global _LAST_HOSTED_ASSESSMENT
    result = run_github_assessment(req.model_dump())
    if result.get('status') == 'blocked':
        raise HTTPException(400, result)
    _LAST_HOSTED_ASSESSMENT = result
    return result


@app.post('/assessment/mid')
def hosted_mid_assessment(req: MidAssessmentRequest):
    global _LAST_MID_ASSESSMENT
    result = build_mid_assessment(req.model_dump())
    if result.get('status') == 'blocked':
        raise HTTPException(400, result)
    _LAST_MID_ASSESSMENT = result
    return result


@app.post('/retainer/ops')
def hosted_retainer_ops(req: RetainerOpsRequest):
    global _LAST_RETAINER_OPS
    result = build_retainer_ops(req.model_dump())
    if result.get('status') == 'blocked':
        raise HTTPException(400, result)
    _LAST_RETAINER_OPS = result
    return result


@app.get('/assessment/latest')
def hosted_latest_assessment():
    return _LAST_HOSTED_ASSESSMENT or {'status':'empty','message':'No hosted assessment has been run in this backend process.'}


@app.get('/assessment/mid/latest')
def hosted_latest_mid_assessment():
    return _LAST_MID_ASSESSMENT or {'status':'empty','message':'No Mid assessment has been run in this backend process.'}


@app.get('/retainer/ops/latest')
def hosted_latest_retainer_ops():
    return _LAST_RETAINER_OPS or {'status':'empty','message':'No Retainer Ops workflow has been run in this backend process.'}


def start(): uvicorn.run('nico.api.main:app',host='127.0.0.1',port=8000,reload=False)
