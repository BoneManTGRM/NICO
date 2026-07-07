from pathlib import Path


def test_max_target_status_routes_are_exposed():
    api = Path("nico/api/main.py").read_text(encoding="utf-8")

    assert "from nico.max_target_status import build_max_target_status" in api
    assert "@app.get('/max-target/status')" in api
    assert "@app.post('/max-target/status')" in api
    assert "GET /max-target/status" in api
    assert "POST /max-target/status" in api
