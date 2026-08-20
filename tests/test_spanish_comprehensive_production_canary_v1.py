from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/spanish_comprehensive_live_acceptance_v1.py")
WORKFLOW = Path(".github/workflows/spanish-comprehensive-production-proof.yml")


def test_spanish_canary_starts_a_real_es_mx_comprehensive_run() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    compile(text, str(SCRIPT), "exec")

    assert 'SPANISH_ROUTE = "/es/assessment"' in text
    assert 'locale="es-MX"' in text
    assert 'SPANISH_REPO_LABEL = "Propietario/nombre del repositorio o URL de GitHub"' in text
    assert 'SPANISH_TERMINAL_PHASE = "Revisión interna requerida"' in text
    assert 'item.get("path") != "/api/nico/assessment/comprehensive-intake"' in text
    assert 'payload.get("report_language")' in text
    assert 'languages == ["es-MX"]' in text
    assert 'recovery._start_count(requests) == 1' in text


def test_spanish_canary_proves_final_pdf_language_and_safety_boundaries() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '"Evaluación Técnica Integral"' in text
    assert '"Resumen ejecutivo"' in text
    assert '"Cuadro de puntuación técnica"' in text
    assert '"NICO Comprehensive Technical Assessment"' in text
    assert '"missing Spanish presentation translation"' in text
    assert '"v2_production_publication_failed"' in text
    assert 'assert payload.get("human_review_required") is True' in text
    assert 'assert payload.get("client_delivery_allowed") is False' in text
    assert 'assert reports.get("pdf_available") is True' in text
    assert 'assert reports.get("markdown_available") is True' in text
    assert 'pdf_bytes.startswith(b"%PDF")' in text
    assert 'pdf.headers.get("x-nico-run-id") == run_id' in text


def test_spanish_production_workflow_is_a_persistent_main_release_gate() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Spanish Comprehensive Production Proof" in text
    assert "branches:\n      - main" in text
    assert "workflow_dispatch:" in text
    assert "statuses: write" in text
    assert "cancel-in-progress: false" in text
    assert "NICO Spanish Comprehensive Production Proof" in text
    assert "Wait for exact frontend and backend deployments" in text
    assert "Verify exact frontend release identity" in text
    assert "scripts/spanish_comprehensive_live_acceptance_v1.py" in text
    assert 'payload["report_language_requested"] == "es-MX"' in text
    assert 'payload["terminal"]["phase"] == "Revisión interna requerida"' in text
    assert 'payload["spanish_pdf_presentation_verified"] is True' in text
    assert 'payload["human_review_required"] is True' in text
    assert 'payload["client_delivery_allowed"] is False' in text
    assert "Publish successful Spanish proof status" in text
    assert "Publish failed Spanish proof status" in text
    assert '-H "Accept: application/vnd.github+json"' in text


def test_spanish_canary_has_time_to_publish_terminal_status_after_proof_timeout() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # The proof step must terminate materially before the job-level watchdog so the
    # always/failure finalizers can upload evidence and replace the pending commit state.
    assert "timeout-minutes: 180" in text
    assert "timeout-minutes: 100" in text
    assert "--timeout-seconds 5400" in text
    assert "continue-on-error: true" in text
    assert "if: always()" in text
    assert "if: failure()" in text
    assert "sudo tee /etc/apt/apt-mirrors.txt" in text


def test_spanish_canary_does_not_approve_or_deliver_client_artifacts() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    combined = script + "\n" + workflow

    assert "/approve" not in combined
    assert "client_delivery_allowed = True" not in combined
    assert '"client_delivery_allowed": True' not in combined
    assert "human_review_required = False" not in combined
    assert '"human_review_required": False' not in combined
