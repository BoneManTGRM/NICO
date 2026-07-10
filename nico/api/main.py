import os
from pathlib import Path
from typing import Any
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
from nico.cli import scan_test_lab, scan_drift_demo, run_scan, Store, generate_reports, verify_latest
from nico.hosted_assessment import run_github_assessment
from nico.hosted_scanner_artifacts import extract_scanner_worker_artifact, run_github_assessment_with_scanner_artifacts
from nico.assessment_quality import polish_express_result
from nico.final_report_consistency import finalize_express_result_consistency
from nico.assessment_attachment import attach_existing_worker_evidence
from nico.report_accuracy import apply_report_accuracy
from nico.scanner_evidence import enrich_payload_with_scanner_evidence
from nico.express_review_target import attach_express_review_target
from nico.evidence_artifact_bundle import attach_evidence_artifact_bundle
from nico.client_acceptance import attach_client_acceptance_gate, client_acceptance_status, request_client_acceptance, transition_client_acceptance
from nico.service_catalog_api import register_service_catalog_routes
from nico.workflow_preflight_api import register_workflow_preflight_routes
from nico.release_readiness_api import register_release_readiness_routes
from nico.hosted_smoke_test_api import register_hosted_smoke_test_routes
from nico.report_readiness_gate_api import register_report_readiness_gate_routes
from nico.report_readiness_attachment_api import register_report_readiness_attachment_routes
from nico.service_workflows import COVERAGE_TARGETS, build_mid_assessment, build_retainer_ops
from nico.max_target_status import build_max_target_status
from nico.scanner_worker import get_scan, start_scan
from nico.storage import STORE
from nico.evidence import list_evidence, upload_evidence
from nico.approval_queue import create_approval, draft_pr_request, list_approvals, transition_approval
from nico.reports import build_report_package, export_report, get_report
from nico.final_review_workflow import final_review_status, request_final_review, transition_final_review
from nico.client_job_mode import create_client_job_package, export_client_job_package, export_client_job_payload, get_client_job_package, list_client_job_exports
from nico.github_app import github_app_plan, installation_record
from nico.customer_access import access_summary
from nico.repair_intelligence import create_repair_approval, repair_quality_policy, suggest_repair
from nico.runtime_config import preview_runtime_config, runtime_config, runtime_config_history, update_runtime_config
from nico.report_templates import get_report_template, list_report_templates, update_report_template
from nico.projects import create_customer, create_project, get_customer, get_project, list_customers, list_projects, project_approvals, project_evidence, project_latest, project_reports, project_runs, project_trends
from nico.diagnostics import diagnostics, feature_diagnostics, latest_runs_diagnostics, storage_diagnostics
from nico.admin_security import require_admin_write, safe_public_admin_status

_LAST_HOSTED_ASSESSMENT = {}
_LAST_MID_ASSESSMENT = {}
_LAST_RETAINER_OPS = {}
_EXCEPTION_DETAIL_KEYS = {'error', 'exception', 'exc', 'traceback', 'stacktrace', 'stack_trace', 'stack', 'debug', 'stderr', 'reason'}


def cors_origins():
    configured = os.getenv('NICO_CORS_ORIGINS', '')
    origins = [origin.strip() for origin in configured.split(',') if origin.strip()]
    default_origins = ['http://localhost:3000','https://app.nicoaudit.com','https://nicoaudit.vercel.app']
    return origins or default_origins


def scrub_exception_details(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in _EXCEPTION_DETAIL_KEYS and isinstance(item, str):
                scrubbed[key] = 'internal detail redacted'
            else:
                scrubbed[key] = scrub_exception_details(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_exception_details(item) for item in value]
    return value


def safe_storage_status_payload() -> dict[str, Any]:
    try:
        status = STORE.status()
    except Exception:  # pragma: no cover - defensive API boundary
        return {'status': 'unavailable', 'mode': 'storage_status_unavailable'}
    return {
        'status': status.get('status') or 'ok',
        'adapter': status.get('adapter') or 'unknown',
        'persistence_available': bool(status.get('persistence_available')),
        'database_url_configured': bool(status.get('database_url_configured')),
    }


def safe_storage_schema_payload() -> dict[str, Any]:
    try:
        schema = STORE.schema()
        migration = STORE.migration_plan()
    except Exception:  # pragma: no cover - defensive API boundary
        return {'status': 'unavailable', 'schema_available': False, 'migration_plan_available': False}
    return {
        'status': 'ok',
        'schema_available': bool(schema),
        'schema_keys': sorted(str(key) for key in schema.keys()) if isinstance(schema, dict) else [],
        'storage': safe_storage_status_payload(),
        'migration_plan_available': bool(migration),
    }


def safe_migration_plan_payload() -> dict[str, Any]:
    try:
        plan = STORE.migration_plan()
    except Exception:  # pragma: no cover - defensive API boundary
        return {'status': 'unavailable', 'migration_plan_available': False}
    return {'status': 'ok', 'migration_plan_available': bool(plan), 'storage': safe_storage_status_payload()}


def safe_runtime_config_payload() -> dict[str, Any]:
    try:
        config = runtime_config()
    except Exception:  # pragma: no cover - defensive API boundary
        return {'source': 'unavailable', 'version': 'unavailable'}
    return {'source': config.get('source'), 'version': config.get('version'), 'feature_flags': config.get('feature_flags', {})}


def safe_diagnostics_payload() -> dict[str, Any]:
    config = safe_runtime_config_payload()
    return {
        'status': 'ok',
        'app': 'NICO',
        'runtime_config': {'source': config.get('source'), 'version': config.get('version')},
        'storage': safe_storage_status_payload(),
        'admin': safe_public_admin_status(),
        'redaction': 'Internal exception, stack, stderr, traceback, and provider-error details are not returned by this endpoint.',
    }


def safe_feature_diagnostics_payload() -> dict[str, Any]:
    config = safe_runtime_config_payload()
    return {
        'status': 'ok',
        'runtime_config_source': config.get('source'),
        'feature_flags': config.get('feature_flags', {}),
        'scanner_execution_enabled': os.getenv('NICO_ENABLE_SCANNER_EXECUTION', 'true').lower() == 'true',
        'project_commands_allowed': os.getenv('NICO_ALLOW_PROJECT_COMMANDS', 'false').lower() == 'true',
        'admin': safe_public_admin_status(),
    }


def safe_latest_runs_payload() -> dict[str, Any]:
    try:
        assessment_count = len(STORE.list('assessment_runs'))
        scanner_count = len(STORE.list('scanner_runs'))
        report_count = len(STORE.list('reports'))
        approval_count = len(list_approvals())
    except Exception:  # pragma: no cover - defensive API boundary
        return {'status': 'unavailable', 'counts_available': False}
    return {
        'status': 'ok',
        'counts_available': True,
        'counts': {
            'assessment_runs': assessment_count,
            'scanner_runs': scanner_count,
            'approvals': approval_count,
            'reports': report_count,
        },
    }


def safe_operation_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {'status': 'ok', 'result_type': type(result).__name__}
    return {
        'status': result.get('status') or 'ok',
        'scan_id': result.get('scan_id') or result.get('id') or result.get('run_id'),
        'repository': result.get('repository'),
        'customer_id': result.get('customer_id'),
        'project_id': result.get('project_id'),
        'queued': result.get('queued'),
    }


def hosted_assessment_storage_record(req: GithubAssessmentRequest) -> tuple[str, dict[str, Any]]:
    record_id = f"express_{req.customer_id or 'default_customer'}_{req.project_id or 'default_project'}"
    payload = {
        'status': 'complete',
        'repository': req.repository,
        'customer_id': req.customer_id,
        'project_id': req.project_id,
    }
    return record_id, {'workflow':'express','customer_id':req.customer_id,'project_id':req.project_id,'status':'complete','payload':payload}


def safe_blocked_exception(result: dict[str, Any]) -> HTTPException:
    code = str(result.get('code') or result.get('reason') or 'blocked')[:80]
    return HTTPException(
        status_code=400,
        detail={
            'status': 'blocked',
            'code': code,
            'message': 'Request blocked by NICO safety, authorization, or review policy.',
        },
    )


class LocalScanRequest(BaseModel): path: str
class PolicyLevelRequest(BaseModel): level: int
class CustomerRequest(BaseModel): customer_id: str = ''; name: str = ''
class ProjectRequest(BaseModel): project_id: str = ''; customer_id: str = 'default_customer'; name: str = ''; repository: str = ''
class RuntimeConfigRequest(BaseModel):
    config: dict[str, Any] = {}
    updated_by: str = 'admin'
    change_reason: str = ''
class ReportTemplateRequest(BaseModel): template: dict[str, Any] = {}
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
    scanner_worker_artifact: dict[str, Any] = {}
    scanner_artifact: dict[str, Any] = {}
    worker_artifact: dict[str, Any] = {}
    scanner_worker: dict[str, Any] = {}

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

class ApprovalTransitionRequest(BaseModel): actor: str = 'human_reviewer'; note: str = ''
class DraftPrRequest(BaseModel): approval_id: str; repository: str; branch_name: str = ''; title: str = ''; body: str = ''

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

class FinalReviewRequest(BaseModel):
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'
    run_id: str = ''
    report_id: str = ''
    evidence: list[str] = []
    requester: str = 'nico'
    risk_level: str = ''
    test_plan: str = ''
    rollback_plan: str = ''

class FinalReviewTransitionRequest(BaseModel): actor: str = 'human_reviewer'; note: str = ''

class ClientAcceptanceRequest(BaseModel):
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'
    run_id: str = ''
    report_id: str = ''
    repository: str = ''
    evidence: list[str] = []
    requester: str = 'nico'
    risk_level: str = ''
    test_plan: str = ''
    rollback_plan: str = ''

class ClientJobPackageRequest(BaseModel):
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'
    job_id: str = ''
    client_name: str = ''
    project_name: str = ''
    repository: str = ''
    source_scope: str = ''
    authorization_statement: str = ''
    quote_text: str = ''
    product_evidence_text: str = ''
    assessment: dict = {}

class ClientJobExportRequest(ClientJobPackageRequest):
    format: str = 'json'

class ReportExportRequest(BaseModel): format: str = 'json'
class MaxTargetStatusRequest(BaseModel): payload: dict[str, Any] = {}
class GitHubInstallationRequest(BaseModel): installation_id: str = ''; customer_id: str = 'default_customer'; selected_repositories: list[str] = []; permissions: dict = {}
class RepairSuggestionRequest(BaseModel):
    issue: str
    evidence: list[str] = []
    affected_files: list[str] = []
    risk_level: str = ''
    test_plan: str = ''
    rollback_plan: str = ''
    customer_id: str = 'default_customer'
    project_id: str = 'default_project'

app=FastAPI(title='NICO API',version='0.8.0',description='Local-first and hosted defensive technical assessment API')
app.add_middleware(CORSMiddleware,allow_origins=cors_origins(),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
register_service_catalog_routes(app)
register_workflow_preflight_routes(app)
register_release_readiness_routes(app)
register_hosted_smoke_test_routes(app)
register_report_readiness_gate_routes(app)
register_report_readiness_attachment_routes(app)


@app.exception_handler(Exception)
async def safe_unhandled_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            'status': 'error',
            'code': 'internal_error',
            'message': 'Request failed. Review server logs or diagnostic evidence with authorized access.',
        },
    )


def _max_target_payload(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if _LAST_HOSTED_ASSESSMENT:
        payload.update(scrub_exception_details(_LAST_HOSTED_ASSESSMENT))
    if _LAST_MID_ASSESSMENT:
        payload['mid_assessment'] = scrub_exception_details(_LAST_MID_ASSESSMENT)
        payload.setdefault('qa_evidence', 'latest mid-assessment evidence available')
        payload.setdefault('parity_notes', 'latest mid-assessment parity notes available')
        payload.setdefault('stakeholder_notes', 'latest mid-assessment stakeholder notes available')
        payload.setdefault('roadmap_notes', 'latest mid-assessment roadmap notes available')
        payload.setdefault('known_risks', 'latest mid-assessment risk notes available')
    if _LAST_RETAINER_OPS:
        payload['retainer_ops'] = scrub_exception_details(_LAST_RETAINER_OPS)
        payload.setdefault('issue_summary', 'latest retainer issue summary available')
        payload.setdefault('release_notes', 'latest retainer release notes available')
        payload.setdefault('client_update', 'latest retainer client update available')
    if extra:
        payload.update(scrub_exception_details(extra))
    return payload


@app.get('/health')
def health():
    config = safe_runtime_config_payload()
    return {'status':'ok','system':'NICO','mode':'local-first-hosted-ready','coverage_targets': COVERAGE_TARGETS,'storage': safe_storage_status_payload(),'runtime_config': {'source': config.get('source'), 'version': config.get('version')},'admin': safe_public_admin_status(),'customer_access': access_summary({'role':'owner'}),'workflows': {'express': bool(_LAST_HOSTED_ASSESSMENT),'mid': bool(_LAST_MID_ASSESSMENT),'retainer': bool(_LAST_RETAINER_OPS)},'cors_origins': cors_origins()}

@app.get('/targets')
def targets():
    config = safe_runtime_config_payload()
    return {'status': 'ok','coverage_targets': COVERAGE_TARGETS,'storage': safe_storage_status_payload(),'runtime_config': {'source': config.get('source'), 'version': config.get('version')},'truth_rules': ['Evidence-bound scoring only','Missing evidence is marked unavailable','Client delivery requires human review','Production-impacting actions require human approval'],'workflow_endpoints': ['GET /service-catalog','GET /service-catalog/{workflow}','POST /service-catalog/intake-readiness','POST /workflow/preflight','POST /workflow/preflight/batch','POST /release/readiness','POST /hosted/smoke-test','POST /reports/readiness-gate','POST /reports/attach-readiness','POST /assessment/github','POST /assessment/mid','POST /retainer/ops','GET /max-target/status','POST /max-target/status','POST /worker/scan','POST /client-acceptance/request','GET /client-acceptance/{run_id}','POST /client-acceptance/{approval_id}/{status}','POST /client-job/package','POST /client-job/export','GET /client-job/{job_id}','GET /client-job/{job_id}/exports','POST /reports/{run_id}/final-review/request','POST /reports/final-review/{approval_id}/{status}','POST /evidence/upload','POST /repair/suggest','GET /approvals','GET /config/runtime','GET /customers','GET /projects','GET /diagnostics']}

@app.get('/max-target/status')
def max_target_status():
    payload = _max_target_payload()
    return {'status':'ok','source':'latest_in_memory_assessments','has_sources': {'express': bool(_LAST_HOSTED_ASSESSMENT),'mid': bool(_LAST_MID_ASSESSMENT),'retainer': bool(_LAST_RETAINER_OPS)},'max_target_status': scrub_exception_details(build_max_target_status(payload))}

@app.post('/max-target/status')
def max_target_status_from_payload(req: MaxTargetStatusRequest):
    payload = _max_target_payload(req.payload or {})
    return {'status':'ok','source':'latest_in_memory_plus_payload','max_target_status': scrub_exception_details(build_max_target_status(payload))}

@app.get('/usage/guide')
def usage_guide():
    path = Path(__file__).resolve().parents[2] / 'docs' / 'HOW_TO_USE_NICO.md'
    if not path.exists(): return {'status':'unavailable','message':'HOW_TO_USE_NICO.md is missing.'}
    return {'status':'ok','format':'markdown','content':path.read_text(encoding='utf-8')}

@app.get('/storage/status')
def storage_status(): return {'status':'ok','storage':safe_storage_status_payload()}
@app.get('/storage/schema')
def storage_schema(): return safe_storage_schema_payload()
@app.get('/storage/migration-plan')
def storage_migration_plan(): return safe_migration_plan_payload()
@app.post('/storage/apply-schema')
def storage_apply_schema(x_nico_admin_token: str = Header(default='')):
    allowed, blocked = require_admin_write(x_nico_admin_token)
    if not allowed: return safe_operation_result(blocked)
    return {'status':'unavailable','mode':'manual_migration_required','message':'Automatic schema application is disabled in this safe hosted build. Use the schema from GET /storage/schema manually.'}

@app.get('/config/runtime')
def config_runtime(): return {'status':'ok','config':safe_runtime_config_payload()}
@app.post('/config/runtime')
def config_runtime_update(req: RuntimeConfigRequest, x_nico_admin_token: str = Header(default='')):
    payload = dict(req.config or {})
    payload['updated_by'] = req.updated_by
    payload['change_reason'] = req.change_reason
    return scrub_exception_details(update_runtime_config(payload, admin_token=x_nico_admin_token))
@app.get('/config/runtime/history')
def config_runtime_history(): return scrub_exception_details(runtime_config_history())
@app.post('/config/runtime/preview')
def config_runtime_preview(req: RuntimeConfigRequest): return scrub_exception_details(preview_runtime_config(req.config or {}))
@app.post('/config/runtime/rollback')
def config_runtime_rollback(x_nico_admin_token: str = Header(default='')):
    allowed, blocked = require_admin_write(x_nico_admin_token)
    if not allowed: return safe_operation_result(blocked)
    return {'status':'unavailable','message':'Runtime config rollback history exists, but automated rollback is not enabled in this safe build.'}

@app.get('/report-templates')
def report_templates(): return scrub_exception_details(list_report_templates())
@app.get('/report-templates/{template_id}')
def report_template(template_id: str): return scrub_exception_details(get_report_template(template_id))
@app.post('/report-templates/{template_id}')
def report_template_update(template_id: str, req: ReportTemplateRequest, x_nico_admin_token: str = Header(default='')): return scrub_exception_details(update_report_template(template_id, req.template or {}, admin_token=x_nico_admin_token))

@app.get('/customers')
def customers(): return {'status':'ok','customers':scrub_exception_details(list_customers())}
@app.post('/customers')
def customer_create(req: CustomerRequest, x_nico_admin_token: str = Header(default='')): return scrub_exception_details(create_customer(req.model_dump(), admin_token=x_nico_admin_token))
@app.get('/customers/{customer_id}')
def customer_get(customer_id: str): return scrub_exception_details(get_customer(customer_id))
@app.get('/projects')
def projects(customer_id: str = ''): return {'status':'ok','projects':scrub_exception_details(list_projects(customer_id or None))}
@app.post('/projects')
def project_create(req: ProjectRequest, x_nico_admin_token: str = Header(default='')): return scrub_exception_details(create_project(req.model_dump(), admin_token=x_nico_admin_token))
@app.get('/projects/{project_id}')
def project_get(project_id: str): return scrub_exception_details(get_project(project_id))
@app.get('/projects/{project_id}/runs')
def project_runs_endpoint(project_id: str): return scrub_exception_details(project_runs(project_id))
@app.get('/projects/{project_id}/latest')
def project_latest_endpoint(project_id: str): return scrub_exception_details(project_latest(project_id))
@app.get('/projects/{project_id}/trends')
def project_trends_endpoint(project_id: str): return scrub_exception_details(project_trends(project_id))
@app.get('/projects/{project_id}/reports')
def project_reports_endpoint(project_id: str): return scrub_exception_details(project_reports(project_id))
@app.get('/projects/{project_id}/approvals')
def project_approvals_endpoint(project_id: str): return scrub_exception_details(project_approvals(project_id))
@app.get('/projects/{project_id}/evidence')
def project_evidence_endpoint(project_id: str): return scrub_exception_details(project_evidence(project_id))

@app.get('/diagnostics')
def diagnostics_endpoint(): return safe_diagnostics_payload()
@app.get('/diagnostics/frontend-config')
def diagnostics_frontend_config(): return {'status':'ok','runtime_config':safe_runtime_config_payload(),'admin':safe_public_admin_status()}
@app.get('/diagnostics/backend-config')
def diagnostics_backend_config(): return safe_diagnostics_payload()
@app.get('/diagnostics/storage')
def diagnostics_storage(): return {'status':'ok','storage':safe_storage_status_payload()}
@app.get('/diagnostics/features')
def diagnostics_features(): return safe_feature_diagnostics_payload()
@app.get('/diagnostics/latest-runs')
def diagnostics_latest_runs(): return safe_latest_runs_payload()

@app.post('/scan/test-lab')
def api_scan_test_lab(): return scrub_exception_details(scan_test_lab())
@app.post('/scan/drift-demo')
def api_scan_drift_demo(): return scrub_exception_details(scan_drift_demo())
@app.post('/scan/local')
def api_scan_local(req:LocalScanRequest):
    if not req.path: raise HTTPException(400,'path required')
    return scrub_exception_details(run_scan(req.path))
@app.get('/scans/latest')
def latest_scan(): return scrub_exception_details(Store().latest_scan())
@app.get('/findings')
def findings(): return scrub_exception_details(Store().payloads('findings'))
@app.get('/findings/{finding_id}')
def finding(finding_id:str):
    for f in Store().payloads('findings'):
        if f.get('id')==finding_id: return scrub_exception_details(f)
    raise HTTPException(404,'finding not found')
@app.get('/drift')
def drift(): return scrub_exception_details(Store().payloads('drift_events'))
@app.get('/repairs')
def repairs(): return scrub_exception_details(Store().payloads('repairs'))
@app.get('/verification/latest')
def verification_latest(): return scrub_exception_details(verify_latest())
@app.post('/verification/latest')
def verification_post(): return scrub_exception_details(verify_latest())
@app.get('/memory')
def memory(): return scrub_exception_details(Store().payloads('memory'))
@app.get('/reports')
def reports(): return scrub_exception_details(Store().rows('reports'))
@app.get('/reports/latest')
def report_latest():
    rows=Store().rows('reports'); return scrub_exception_details(rows[0]) if rows else {}
@app.post('/reports/generate')
def report_generate(): return scrub_exception_details(generate_reports())
@app.get('/policy')
def policy(): return scrub_exception_details(Store().policy())
@app.post('/policy/autonomy-level')
def set_policy(req:PolicyLevelRequest):
    s=Store(); p=s.policy(); p['autonomy_level']=max(0,min(5,int(req.level))); s.save_policy(p); s.audit('policy.autonomy_level',{'level':p['autonomy_level']}); return scrub_exception_details(p)
@app.get('/audit-log')
def audit_log(): return scrub_exception_details(Store().rows('audit_log'))

@app.get('/client-acceptance/{run_id}')
def client_acceptance_get(run_id: str, customer_id: str = 'default_customer', project_id: str = 'default_project'):
    return scrub_exception_details(client_acceptance_status(run_id, customer_id, project_id))
@app.post('/client-acceptance/request')
def client_acceptance_request(req: ClientAcceptanceRequest):
    result = request_client_acceptance(req.model_dump())
    if result.get('status') == 'blocked': raise safe_blocked_exception(result)
    return scrub_exception_details(result)
@app.post('/client-acceptance/{approval_id}/{status}')
def client_acceptance_transition_endpoint(approval_id: str, status: str, req: FinalReviewTransitionRequest):
    result = transition_client_acceptance(approval_id, status, actor=req.actor, note=req.note)
    if result.get('status') == 'blocked': raise safe_blocked_exception(result)
    return scrub_exception_details(result)

@app.post('/assessment/github')
def hosted_github_assessment(req: GithubAssessmentRequest):
    global _LAST_HOSTED_ASSESSMENT
    request_payload = req.model_dump()
    if extract_scanner_worker_artifact(request_payload):
        result = run_github_assessment_with_scanner_artifacts(request_payload)
    else:
        result = run_github_assessment(request_payload)
    if result.get('status') == 'blocked': raise safe_blocked_exception(result)
    result = attach_existing_worker_evidence(result, request_payload)
    result = enrich_payload_with_scanner_evidence(result)
    result = apply_report_accuracy(result)
    result = attach_express_review_target(result, request_payload)
    result = polish_express_result(result)
    result = finalize_express_result_consistency(result)
    result = attach_express_review_target(result, request_payload)
    result = attach_evidence_artifact_bundle(result)
    result = attach_client_acceptance_gate(result)
    result = scrub_exception_details(result)
    _LAST_HOSTED_ASSESSMENT = result
    record_id, storage_record = hosted_assessment_storage_record(req)
    STORE.put('assessment_runs', record_id, storage_record)
    return result

@app.post('/assessment/mid')
def hosted_mid_assessment(req: MidAssessmentRequest):
    global _LAST_MID_ASSESSMENT
    result = build_mid_assessment(req.model_dump())
    if result.get('status') == 'blocked': raise safe_blocked_exception(result)
    result = scrub_exception_details(result)
    _LAST_MID_ASSESSMENT = result
    STORE.put('assessment_runs', result.get('generated_at','latest_mid').replace(':','_'), {'workflow':'mid','customer_id':req.customer_id,'project_id':req.project_id,'status':result.get('status'),'payload':result})
    return result

@app.post('/retainer/ops')
def hosted_retainer_ops(req: RetainerOpsRequest):
    global _LAST_RETAINER_OPS
    result = build_retainer_ops(req.model_dump())
    if result.get('status') == 'blocked': raise safe_blocked_exception(result)
    result = scrub_exception_details(result)
    _LAST_RETAINER_OPS = result
    STORE.put('assessment_runs', result.get('generated_at','latest_retainer').replace(':','_'), {'workflow':'retainer','customer_id':req.customer_id,'project_id':req.project_id,'status':result.get('status'),'payload':result})
    return result

@app.post('/worker/scan')
def worker_scan(req: WorkerScanRequest):
    result = start_scan(req.model_dump())
    if result.get('status') == 'blocked': raise safe_blocked_exception(result)
    return safe_operation_result(result)
@app.get('/worker/scan/{scan_id}')
def worker_scan_status(scan_id: str): return safe_operation_result(get_scan(scan_id))

@app.post('/evidence/upload')
async def evidence_upload(file: UploadFile = File(...), customer_id: str = Form('default_customer'), project_id: str = Form('default_project'), run_id: str = Form('')):
    result = await upload_evidence(file, customer_id=customer_id, project_id=project_id, run_id=run_id)
    if result.get('status') == 'blocked': raise safe_blocked_exception(result)
    return safe_operation_result(result)
@app.get('/evidence/{project_id}')
def evidence_for_project(project_id: str, customer_id: str = ''): return scrub_exception_details(list_evidence(project_id, customer_id=customer_id or None))

@app.post('/client-job/package')
def client_job_package(req: ClientJobPackageRequest): return scrub_exception_details(create_client_job_package(req.model_dump()))
@app.post('/client-job/export')
def client_job_export(req: ClientJobExportRequest):
    payload = req.model_dump()
    if req.job_id:
        return scrub_exception_details(export_client_job_package(req.job_id, req.format))
    return scrub_exception_details(export_client_job_payload(payload, req.format))
@app.get('/client-job/{job_id}')
def client_job_get(job_id: str): return scrub_exception_details(get_client_job_package(job_id))
@app.get('/client-job/{job_id}/exports')
def client_job_exports(job_id: str): return scrub_exception_details(list_client_job_exports(job_id))

@app.post('/repair/suggest')
def repair_suggest(req: RepairSuggestionRequest): return scrub_exception_details(suggest_repair(req.model_dump()))
@app.post('/repair/approval')
def repair_approval(req: RepairSuggestionRequest): return scrub_exception_details(create_repair_approval(req.model_dump()))
@app.get('/repair/policy')
def repair_policy(): return scrub_exception_details(repair_quality_policy())

@app.post('/reports/package')
def create_report_package(req: ReportRequest): return scrub_exception_details(build_report_package(req.model_dump()))
@app.get('/reports/{run_id}')
def report_by_run(run_id: str): return scrub_exception_details(get_report(run_id))
@app.post('/reports/{run_id}/export')
def report_export(run_id: str, req: ReportExportRequest): return scrub_exception_details(export_report(run_id, req.format))
@app.get('/reports/{run_id}/final-review')
def report_final_review_status(run_id: str, customer_id: str = 'default_customer', project_id: str = 'default_project'):
    return scrub_exception_details(final_review_status(run_id, customer_id=customer_id, project_id=project_id))
@app.post('/reports/{run_id}/final-review/request')
def report_final_review_request(run_id: str, req: FinalReviewRequest):
    payload = req.model_dump(); payload['run_id'] = run_id
    return scrub_exception_details(request_final_review(payload))
@app.post('/reports/final-review/{approval_id}/{status}')
def report_final_review_transition(approval_id: str, status: str, req: FinalReviewTransitionRequest):
    return scrub_exception_details(transition_final_review(approval_id, status, actor=req.actor, note=req.note))

@app.post('/approval/create')
def approval_create(req: ApprovalRequest): return scrub_exception_details(create_approval(req.model_dump()))
@app.get('/approvals')
def approvals(customer_id: str = '', project_id: str = ''): return {'status':'ok','approvals':scrub_exception_details(list_approvals(customer_id or None, project_id or None))}
@app.post('/approvals/{approval_id}/{status}')
def approval_transition(approval_id: str, status: str, req: ApprovalTransitionRequest): return scrub_exception_details(transition_approval(approval_id, status, req.actor, req.note))
@app.post('/approvals/{approval_id}/draft-pr')
def approval_draft_pr(approval_id: str, req: DraftPrRequest):
    payload = req.model_dump(); payload['approval_id'] = approval_id
    return scrub_exception_details(draft_pr_request(payload))

@app.post('/github/installations')
def github_installation(req: GitHubInstallationRequest, x_nico_admin_token: str = Header(default='')): return scrub_exception_details(installation_record(req.model_dump(), admin_token=x_nico_admin_token))
@app.get('/github/app/plan')
def github_plan(): return scrub_exception_details(github_app_plan())

if __name__=='__main__': uvicorn.run(app,host='0.0.0.0',port=8000)
