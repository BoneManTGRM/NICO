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


def test_full_assessment_endpoint_returns_planned_progress_shape():
    c=TestClient(app)
    response = c.post('/assessment/full-run', json={'target': 'https://github.com/BoneManTGRM/NICO', 'authorization_confirmed': True, 'authorized_by': 'tester', 'customer_id': 'cust-a', 'project_id': 'proj-a'})
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'planned'
    assert data['repository'] == 'BoneManTGRM/NICO'
    assert data['customer_id'] == 'cust-a'
    assert data['project_id'] == 'proj-a'
    assert data['human_review_required'] is True
    assert data['client_ready'] is False
    assert [item['step'] for item in data['progress']] == ['authorization', 'repo_evidence', 'scanner_worker', 'evidence_attachment', 'scoring', 'reports', 'approval_request']
    assert data['progress'][0]['status'] == 'complete'
    assert all(item['status'] == 'planned' for item in data['progress'][1:])
    assert data['reports']['pdf_error'] == ''
    assert data['approval']['status'] == 'not_requested'
