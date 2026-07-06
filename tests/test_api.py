from fastapi.testclient import TestClient
from nico.api.main import app


def test_health():
    c=TestClient(app)
    data = c.get('/health').json()
    assert data['status']=='ok'
    assert data['system']=='NICO'
    assert 'https://app.nicoaudit.com' in data['cors_origins']


def test_hosted_assessment_requires_authorization():
    c=TestClient(app)
    response = c.post('/assessment/github', json={'repository': 'BoneManTGRM/NICO', 'authorized': False})
    assert response.status_code == 400
    assert response.json()['detail']['status'] == 'blocked'
