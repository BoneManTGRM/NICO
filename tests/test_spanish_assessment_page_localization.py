from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALIZATION = ROOT / "apps/web/app/assessment/AssessmentSpanishLocalization.ts"
RUNTIME = ROOT / "apps/web/app/assessment/AssessmentRuntimeTruthRepair.tsx"
SPANISH_ROUTE = ROOT / "apps/web/app/es/assessment/page.tsx"


def test_spanish_route_uses_mexican_spanish_locale() -> None:
    source = SPANISH_ROUTE.read_text(encoding="utf-8")
    assert 'locale="es-MX"' in source
    assert "Evaluaciones NICO" in source


def test_dynamic_section_labels_and_assurance_states_are_localized() -> None:
    source = LOCALIZATION.read_text(encoding="utf-8")
    required = {
        "Auditoría de código",
        "Dependencias y ecosistema de bibliotecas",
        "Revisión de exposición de secretos",
        "Análisis estático",
        "Arquitectura y deuda técnica",
        "Velocidad y complejidad",
        "Evidencia de los analizadores",
        "Aceptación del cliente y revisión humana",
        "Revisión limitada",
        "Revisión humana pendiente",
        "Sin puntuación",
        "Excepcional",
        "Fuerte",
        "Moderado",
        "Crítico",
    }
    for label in required:
        assert label in source


def test_report_sentences_visible_in_prior_spanish_run_have_translations() -> None:
    source = LOCALIZATION.read_text(encoding="utf-8")
    english_signatures = {
        "Source-file footprint is large",
        "Total source LOC is high",
        "At least one function has very high cyclomatic complexity",
        "Function-level complexity risk is concentrated",
        "Complexity and high churn overlap",
        "Ownership concentration is elevated",
        "Complexity engine analyzed",
        "Estimated call graph edges",
        "Scanner-worker static tools reported",
        "Accepted clean execution evidence unavailable for",
        "Canonical scanner disposition",
        "Truth reconciliation",
        "Final report acceptance is not scored",
    }
    for signature in english_signatures:
        assert signature in source


def test_raw_step_evidence_is_localized_without_mutating_backend_records() -> None:
    source = LOCALIZATION.read_text(encoding="utf-8")
    assert 'pre.json-block' in source
    assert 'JSON_KEY_SPANISH' in source
    assert '"status", "estado"' in source
    assert '"findings", "hallazgos"' in source
    assert '"commit_sha", "sha_del_commit"' in source
    assert "JSON.parse" in source
    assert "node.textContent = localized" in source


def test_runtime_applies_localization_once_without_observing_live_react_nodes() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    assert 'from "./AssessmentSpanishLocalization"' in source
    assert "localizeSpanishAssessmentDom(document);" in source
    assert "MutationObserver(reconcile)" not in source
    assert "One bounded localization pass" in source


def test_spanish_assessment_requests_advertise_the_requested_locale() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    assert 'target.includes("/api/nico/assessment")' in source
    assert 'headers.set("Accept-Language", "es-MX,es;q=0.9")' in source
    assert 'headers.set("X-NICO-Locale", "es-MX")' in source
    assert "restoreFetch();" in source
