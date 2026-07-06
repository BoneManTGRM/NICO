import os
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from nico.cli import scan_test_lab, scan_drift_demo, run_scan, Store, generate_reports, verify_latest
from nico.hosted_assessment import run_github_assessment
from nico.service_workflows import COVERAGE_TARGETS, build_mid_assessment, build_retainer_ops
from nico.scanner_worker import get_scan, start_scan
from nico.storage import STORE
from nico.evidence import list_evidence, upload_evidence
from nico.approval_queue import create_approval, draft_pr_request, list_approvals, transition_approval
from nico.reports import build_report_package, export_report, get_report
from nico.github_app import github_app_plan, installation_record
from nico.customer_access import access_summary


_LAST_HOSTED_ASSESSMENT = {}
_LAST_MID_ASSESSMENT = {}
_LAST_RETAINER_OPS = {}


def cors_origins():
    configured = os.getenv('NICO_CORS_ORIGINS', '')
    origins = [origin.strip() for origin in configured.split(',') if origin.strip()]
    default_origins = ['http://localhost:3000','https://app.nicoaudit.com','https://nicoaudit.vercel.app']
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
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'
    authorized_by: str = 'unspecified'

class MidAssessmentRequest(BaseModel):
    authorized: bool = False
    client_name: str = ''
    project_name: str = ''
    qa_evidence: str = ''
    parity_notes: str = ''
    stakeholder_notes: str = ''
    roadmap_notes: str = ''
    known_risks: str = ''
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'

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
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'

class WorkerScanRequest(BaseModel):
    repository: str
    authorized: bool = False
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'
    authorized_by: str = 'unspecified'
    authorization_scope: str = 'repository assessment only'
    draft_pr_creation_allowed: bool = False
    tools: list[str] = []

class ApprovalRequest(BaseModel):
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'
    requested_action: str = 'draft_pr'
    evidence: list[str] = []
    affected_files_or_systems: list[str] = []
    risk_level: str = 'unknown'
    test_plan: str = ''
    rollback_plan: str = ''
    requester: str = 'nico'

class ApprovalTransitionRequest(BaseModel):
    actor: str = 'human_reviewer'
    note: str = ''

class DraftPrRequest(BaseModel):
    approval_id: str
    repository: str
    branch_name: str = ''
    title: str = ''
    body: str = ''

class ReportRequest(BaseModel):
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'
    run_id: str = ''
    client_name: str = ''
    project_name: str = ''
    repository: str = ''
    source_scope: str = ''
    authorization_statement: str = ''
    maturity_signal: dict = {}
    evidence_readiness: dict = {}
    findings: list = []
    sections: list = []
    unavailable_data_notes: list = []
    next_steps: list = []

class ReportExportRequest(BaseModel):
    format: str = 'json'

class GitHubInstallationRequest(BaseModel):
    installation_id: str = ''
    customer_id: str = 'default_customer'
    selected_repositories: list[str] = []
    permissions: dict = {}


app=FastAPI(title='NICO API',version='0.5.0',description='Local-first and hosted defensive technical assessment API')
app.add_middleware(CORSMiddleware,allow_origins=cors_origins(),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])


@app.get('/health')
def health():
    return {
        'status':'ok',
        'system':'NICO',
        'mode':'local-first-hosted-ready',
        'coverage_targets': COVERAGE_TARGETS,
        'storage': STORE.status(),
        'customer_access': access_summary({'role':'owner'}),
        'workflows': {'express': bool(_LAST_HOSTED_ASSESSMENT),'mid': bool(_LAST_MID_ASSESSMENT),'retainer': bool(_LAST_RETAINER_OPS)},
        'cors_origins': cors_origins(),
    }

@app.get('/targets')
def targets():
    return {
        'status': 'ok',
        'coverage_targets': COVERAGE_TARGETS,
        'storage': STORE.status(),
        'truth_rules': ['Evidence-bound scoring only','Missing evidence is marked unavailable','Client delivery requires human review','Production-impacting actions require human approval'],
        'workflow_endpoints': ['POST /assessment/github','POST /assessment/mid','POST /retainer/ops','POST /worker/scan','POST /evidence/upload','GET /approvals'],
    }

@app.get('/storage/schema')
def storage_schema(): return {'status':'ok','schema':STORE.schema(),'storage':STORE.status()}

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
    if result.get('status') == 'blocked': raise HTTPException(400, result)
    _LAST_HOSTED_ASSESSMENT = result
    STORE.put('assessment_runs', result.get('generated_at','latest_express').replace(':','_'), {'workflow':'express','customer_id':req.customer_id,'project_id':req.project_id,'status':result.get('status'),'payload':result})
    return result

@app.post('/assessment/mid')
def hosted_mid_assessment(req: MidAssessmentRequest):
    global _LAST_MID_ASSESSMENT
    result = build_mid_assessment(req.model_dump())
    if result.get('status') == 'blocked': raise HTTPException(400, result)
    _LAST_MID_ASSESSMENT = result
    STORE.put('assessment_runs', result.get('generated_at','latest_mid').replace(':','_'), {'workflow':'mid','customer_id':req.customer_id,'project_id':req.project_id,'status':result.get('status'),'payload':result})
    return result

@app.post('/retainer/ops')
def hosted_retainer_ops(req: RetainerOpsRequest):
    global _LAST_RETAINER_OPS
    result = build_retainer_ops(req.model_dump())
    if result.get('status') == 'blocked': raise HTTPException(400, result)
    _LAST_RETAINER_OPS = result
    STORE.put('assessment_runs', result.get('generated_at','latest_retainer').replace(':','_'), {'workflow':'retainer','customer_id':req.customer_id,'project_id':req.project_id,'status':result.get('status'),'payload':result})
    return result

@app.post('/worker/scan')
def worker_scan(req: WorkerScanRequest):
    result = start_scan(req.model_dump())
    if result.get('status') == 'blocked': raise HTTPException(400, result)
    return result

@app.get('/worker/scan/{scan_id}')
def worker_scan_status(scan_id: str): return get_scan(scan_id)

@app.post('/evidence/upload')
async def evidence_upload(file: UploadFile = File(...), customer_id: str = Form('default_customer'), project_id: str = Form('default_project'), run_id: str = Form('')):
    result = await upload_evidence(file, customer_id=customer_id, project_id=project_id, run_id=run_id)
    if result.get('status') == 'blocked': raise HTTPException(400, result)
    return result

@app.get('/evidence/{project_id}')
def evidence_for_project(project_id: str, customer_id: str = ''): return list_evidence(project_id, customer_id=customer_id or None)

@app.post('/reports/package')
def create_report_package(req: ReportRequest): return build_report_package(req.model_dump())
@app.get('/reports/{run_id}')
def report_by_run(run_id: str): return get_report(run_id)
@app.post('/reports/{run_id}/export')
def report_export(run_id: str, req: ReportExportRequest): return export_report(run_id, req.format)

@app.get('/approvals')
def approvals(customer_id: str = '', project_id: str = ''): return list_approvals(customer_id=customer_id or None, project_id=project_id or None)
@app.post('/approvals')
def approval_create(req: ApprovalRequest): return create_approval(req.model_dump())
@app.post('/approvals/{approval_id}/approve')
def approval_approve(approval_id: str, req: ApprovalTransitionRequest): return transition_approval(approval_id, 'approved', actor=req.actor, note=req.note)
@app.post('/approvals/{approval_id}/reject')
def approval_reject(approval_id: str, req: ApprovalTransitionRequest): return transition_approval(approval_id, 'rejected', actor=req.actor, note=req.note)
@app.post('/approvals/{approval_id}/needs-more-evidence')
def approval_more_evidence(approval_id: str, req: ApprovalTransitionRequest): return transition_approval(approval_id, 'needs_more_evidence', actor=req.actor, note=req.note)

@app.post('/github/draft-pr')
def github_draft_pr(req: DraftPrRequest): return draft_pr_request(req.model_dump())
@app.get('/github/app/plan')
def github_app_architecture(): return github_app_plan()
@app.post('/github/app/installations')
def github_app_installation(req: GitHubInstallationRequest): return installation_record(req.model_dump())

@app.get('/assessment/latest')
def hosted_latest_assessment(): return _LAST_HOSTED_ASSESSMENT or {'status':'empty','message':'No hosted assessment has been run in this backend process.'}
@app.get('/assessment/mid/latest')
def hosted_latest_mid_assessment(): return _LAST_MID_ASSESSMENT or {'status':'empty','message':'No Mid assessment has been run in this backend process.'}
@app.get('/retainer/ops/latest')
def hosted_latest_retainer_ops(): return _LAST_RETAINER_OPS or {'status':'empty','message':'No Retainer Ops workflow has been run in this backend process.'}

def start(): uvicorn.run('nico.api.main:app',host='127.0.0.1',port=8000,reload=False)
