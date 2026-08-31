from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/spanish_comprehensive_live_acceptance_v1.py")
TELEMETRY_SCRIPT = Path("scripts/spanish_comprehensive_live_acceptance_v2.py")
TERMINAL_SCRIPT = Path("scripts/spanish_comprehensive_live_acceptance_v3.py")
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
    assert 'PROOF_CUSTOMER_ID = "nico_production_proof"' in text
    assert 'PROOF_PROJECT_ID = "spanish_comprehensive_production"' in text


def test_spanish_canary_waits_for_hydrated_locale_contract_before_interaction() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'data-assessment-hydrated="true"' in text
    assert 'data-assessment-client-copy-verified="true"' in text
    assert "_wait_for_spanish_hydration(page, args.navigation_timeout_ms)" in text
    assert "document.documentElement.dataset.nicoAssessmentDocumentLanguage === 'es-MX'" in text
    assert "page.wait_for_function(" in text

    hydration = text.index("_wait_for_spanish_hydration(page, args.navigation_timeout_ms)")
    language_assertion = text.index('assert page.evaluate("() => document.documentElement.lang") == "es-MX"')
    repository_fill = text.index("page.get_by_label(SPANISH_REPO_LABEL).fill(args.repository)")
    assert hydration < language_assertion < repository_fill


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


def test_spanish_production_workflow_is_an_exact_main_release_gate() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    telemetry = TELEMETRY_SCRIPT.read_text(encoding="utf-8")
    terminal = TERMINAL_SCRIPT.read_text(encoding="utf-8")
    compile(telemetry, str(TELEMETRY_SCRIPT), "exec")
    compile(terminal, str(TERMINAL_SCRIPT), "exec")

    assert "name: Spanish Comprehensive Production Proof" in text
    assert "branches:\n      - main" in text
    assert "workflow_dispatch:" in text
    assert "statuses: write" in text
    assert "group: nico-spanish-comprehensive-production" in text
    assert "cancel-in-progress: false" in text
    assert "cancel-in-progress: true" not in text
    assert "NICO Spanish Comprehensive Production Proof" in text
    assert "Wait for exact frontend and backend deployments" in text
    assert "Verify exact frontend release identity" in text
    assert "scripts/spanish_comprehensive_live_acceptance_v3.py" in text
    assert "spanish-comprehensive-live-proof.progress.json" in text
    assert "SPANISH_PROOF_PROGRESS" in telemetry
    assert 'SPANISH_TERMINAL_PHASE = "Se requiere revisión experta"' in terminal
    assert 'SPANISH_TERMINAL_REVIEW = "Revisión interna requerida"' in terminal
    assert 'SPANISH_TERMINAL_REPORT = "Completa"' in terminal
    assert 'payload["report_language_requested"] == "es-MX"' in text
    assert 'payload["production_proof_scope_verified"] is True' in text
    assert 'payload["terminal"]["phase"] == "Se requiere revisión experta"' in text
    assert 'payload["terminal"]["review"] == "Revisión interna requerida"' in text
    assert 'payload["terminal"]["report"] == "Completa"' in text
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
    assert "timeout-minutes: 300" in text
    assert "timeout-minutes: 100" in text
    assert "--timeout-seconds 5400" in text
    assert "continue-on-error: true" in text
    assert "if: always()" in text
    assert "if: failure()" in text
    assert "sudo tee /etc/apt/apt-mirrors.txt" in text


def test_spanish_canary_runs_supplied_and_module_exclusion_fixtures() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    terminal = TERMINAL_SCRIPT.read_text(encoding="utf-8")

    assert workflow.count(
        "python scripts/spanish_comprehensive_live_acceptance_v3.py"
    ) == 2
    assert "Run explicit exclusion-state Comprehensive proof" in workflow
    assert "NICO_SPANISH_PROOF_ENGAGEMENT_FIXTURE: excluded" in workflow
    assert "spanish-comprehensive-exclusion-live-proof.json" in workflow
    assert 'exclusion["module_exclusion_verified"] is True' in workflow
    assert 'exclusion["excluded_engagement_fields_verified_in_canonical_truth"] is True' in workflow
    assert 'exclusion["excluded_engagement_states_verified_in_both_pdfs"] is True' in workflow
    assert 'ENGAGEMENT_PROOF_FIXTURE_ENV = "NICO_SPANISH_PROOF_ENGAGEMENT_FIXTURE"' in terminal
    assert 'name="Excluir del alcance"' in terminal
    assert '"width": 1440' in terminal
    assert '"excluded_from_scope"' in terminal


def test_spanish_canary_cleans_interrupted_reserved_proof_runs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "ProductionProofInterrupted" in text
    assert "signal.SIGTERM" in text
    assert "signal.SIGINT" in text
    assert "production-proof-cancel" in text
    assert "if run_id and not proof_completed" in text
    assert "_cancel_proof_run(page, origin, run_id)" in text


def test_spanish_canary_does_not_approve_or_deliver_client_artifacts() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    telemetry = TELEMETRY_SCRIPT.read_text(encoding="utf-8")
    terminal = TERMINAL_SCRIPT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    combined = script + "\n" + telemetry + "\n" + terminal + "\n" + workflow

    assert "/approve" not in combined
    assert "client_delivery_allowed = True" not in combined
    assert '"client_delivery_allowed": True' not in combined
    assert "human_review_required = False" not in combined
    assert '"human_review_required": False' not in combined
