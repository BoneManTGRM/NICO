from fastapi.testclient import TestClient
from nico.api.main import app


def test_health():
    c=TestClient(app)
    data = c.get('/health').json()
    assert data['status']=='ok'
    assert data['system']=='NICO'
    assert data['cors_origins'].count('https://app.nicoaudit.com') == 1


def test_hosted_assessment_requires_authorization():
    c=TestClient(app)
    response = c.post('/assessment/github', json={'repository': 'BoneManTGRM/NICO', 'authorized': False})
    assert response.status_code == 400
    assert response.json()['detail']['status'] == 'blocked'


def test_full_assessment_requires_authorization():
    c=TestClient(app)
    response = c.post('/assessment/full-run', json={'repository': 'BoneManTGRM/NICO', 'authorization_confirmed': False})
    assert response.status_code == 400
    detail = response.json()['detail']
    assert detail['status'] == 'blocked'
    assert detail['code'] == 'authorization confirmation is required'
    assert detail['progress'][0]['step'] == 'authorization'
    assert detail['run_id'].startswith('fullrun_')
    assert detail['persistence']['recorded'] is True


def test_full_assessment_endpoint_returns_planned_progress_shape():
    c=TestClient(app)
    response = c.post('/assessment/full-run', json={'target': 'https://github.com/BoneManTGRM/NICO', 'authorization_confirmed': True, 'authorized_by': 'tester', 'customer_id': 'cust-a', 'project_id': 'proj-a', 'run_scanners': False})
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'planned'
    assert data['report_path'] == 'full_run'
    assert data['reports']['report_path'] == 'full_run'
    assert data['repository'] == 'BoneManTGRM/NICO'
    assert data['customer_id'] == 'cust-a'
    assert data['project_id'] == 'proj-a'
    assert data['human_review_required'] is True
    assert data['client_ready'] is False
    assert data['persistence']['recorded'] is True
    assert data['persistence']['record_id'] == data['run_id']
    assert data['persistence']['updated_at']
    assert [item['step'] for item in data['progress']] == ['authorization', 'repo_evidence', 'scanner_worker', 'evidence_attachment', 'scoring', 'reports', 'approval_request']
    by_step = {item['step']: item for item in data['progress']}
    assert by_step['authorization']['status'] == 'complete'
    assert by_step['repo_evidence']['status'] == 'complete'
    assert by_step['repo_evidence']['evidence']['customer_id'] == 'cust-a'
    assert by_step['scanner_worker']['status'] == 'skipped'
    assert by_step['evidence_attachment']['status'] == 'skipped'
    assert by_step['scoring']['status'] == 'planned'
    assert by_step['reports']['status'] == 'planned'
    assert by_step['approval_request']['status'] == 'planned'
    assert data['reports']['pdf_error'] == ''
    assert data['approval']['status'] == 'not_requested'


def test_full_assessment_status_refresh_does_not_request_final_review():
    c=TestClient(app)
    response = c.post('/assessment/full-run/fullrun_ui/status', json={'repository': 'BoneManTGRM/NICO', 'authorization_confirmed': True, 'authorized': True, 'run_scanners': False})
    assert response.status_code == 200
    data = response.json()
    assert data['status_refresh'] is True
    assert data['report_path'] == 'full_run'
    assert data['reports']['report_path'] == 'full_run'
    assert data['run_id'] == 'fullrun_ui'
    assert data['repository'] == 'BoneManTGRM/NICO'
    assert data['approval']['status'] == 'not_requested'
    assert data['persistence']['recorded'] is True
    by_step = {item['step']: item for item in data['progress']}
    assert by_step['scanner_worker']['status'] == 'skipped'
    assert by_step['reports']['status'] == 'skipped'
    assert by_step['approval_request']['status'] == 'skipped'


def test_full_assessment_status_refresh_restores_saved_scope_with_empty_body():
    c=TestClient(app)
    started = c.post('/assessment/full-run', json={'repository': 'BoneManTGRM/NICO', 'authorization_confirmed': True, 'authorized': True, 'authorized_by': 'tester', 'customer_id': 'cust-restore', 'project_id': 'proj-restore', 'run_scanners': False})
    assert started.status_code == 200
    initial = started.json()

    response = c.post(f"/assessment/full-run/{initial['run_id']}/status", json={})
    assert response.status_code == 200
    data = response.json()

    assert data['run_id'] == initial['run_id']
    assert data['repository'] == 'BoneManTGRM/NICO'
    assert data['customer_id'] == 'cust-restore'
    assert data['project_id'] == 'proj-restore'
    assert data['persistence']['recorded'] is True
    assert data['persistence']['restored'] is True
    assert data['approval']['status'] == 'not_requested'
