from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "apps/web/app/assessment/assessmentTransport.ts"
COPY = ROOT / "apps/web/app/assessment/assessmentCopy.ts"


def test_machine_detail_codes_are_not_rendered_as_client_prose() -> None:
    transport = TRANSPORT.read_text(encoding="utf-8")

    assert "function safeClientErrorMessage" in transport
    assert "return stringCode ? copy.backendError : data.detail;" in transport
    assert 'if (String(detail.code || "").trim())' in transport
    assert "return copy.backendError;" in transport
    assert "code: String(" in transport
    assert "stringCode ||" in transport


def test_bounded_error_copy_exists_in_english_and_spanish() -> None:
    copy = COPY.read_text(encoding="utf-8")

    assert 'backendError: "The assessment service is temporarily unavailable."' in copy
    assert 'backendError: "El servicio de evaluación no está disponible temporalmente."' in copy
