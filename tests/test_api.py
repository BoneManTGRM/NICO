from fastapi.testclient import TestClient

from nico.api.main import app


def test_health():
    client = TestClient(app)
    assert client.get('/health').json()['status'] == 'ok'


def test_scanner_availability():
    client = TestClient(app)
    response = client.get('/scanner-availability')
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_report_endpoints():
    client = TestClient(app)
    client.post('/scan/test-lab')
    assert client.get('/reports/owner').status_code == 200
    assert client.get('/reports/developer').status_code == 200
    assert client.get('/reports/reparodynamic').status_code == 200
    assert client.get('/reports/compliance').status_code == 200
