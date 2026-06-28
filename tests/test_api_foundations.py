from fastapi.testclient import TestClient

from nico.api.main import app


def test_foundation_api_routes():
    client = TestClient(app)
    assert client.get("/swarm/policy").status_code == 200
    assert client.post("/agent-security/scan-demo").status_code == 200
    assert client.get("/vault/demo").status_code == 200
    assert client.get("/connector/policy").status_code == 200
    assert client.post("/sandbox/scanner-demo").status_code == 200
    assert client.get("/audit/latest").status_code == 200
    assert client.get("/approvals/pending").status_code == 200
    assert client.get("/tenant/demo").status_code == 200
    assert client.get("/cyber-twin/demo").status_code == 200
    assert client.get("/bench/demo").status_code == 200


def test_foundation_api_static_safety_shape():
    client = TestClient(app)
    response = client.get("/connector/policy")
    payload = response.json()
    assert payload["mode"] == "local_only_demo_no_external_calls"
    assert payload["policy"]["enabled"] is False
