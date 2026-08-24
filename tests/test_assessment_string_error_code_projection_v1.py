from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "apps/web/app/assessment/assessmentTransport.ts"
REQUESTS = ROOT / "apps/web/app/assessment/assessmentRunRequests.ts"


def test_string_backend_detail_preserves_safe_machine_code_for_localized_ui() -> None:
    transport = TRANSPORT.read_text(encoding="utf-8")

    assert "SAFE_STRING_DETAIL_CODE" in transport
    assert 'value.split(":", 1)[0]' in transport
    assert "stringDetailCode(data.detail)" in transport
    assert "detail.code ||" in transport
    assert "stringCode ||" in transport
    assert '"assessment_request_failed"' in transport


def test_repository_snapshot_string_failure_reaches_localized_intake_message() -> None:
    requests = REQUESTS.read_text(encoding="utf-8")

    assert '"repository_snapshot_unavailable"' in requests
    assert "PROVIDER_SNAPSHOT_CODES.has(code)" in requests
    assert "NICO no pudo capturar la revisión inmutable del repositorio seleccionado." in requests
