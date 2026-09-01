from __future__ import annotations

from pathlib import Path

from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_terminal_comprehensive_section_summaries_have_bounded_es_mx_copy() -> None:
    localization = source(
        "apps/web/app/assessment/AssessmentSpanishLocalization.ts"
    )

    for english in (
        "exact-commit executable source signals were analyzed without promoting comments, strings, detector definitions, examples, or tests.",
        "authoritative manifests and contextual dependency evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability.",
        "history-aware secret evidence was separated into verified material findings, review-required candidates, explicit example placeholders, and non-production observations.",
        "bandit, semgrep, eslint, and typescript evidence were evaluated independently against the exact immutable commit.",
        "ci/cd configuration maturity is exact-sha technical evidence. observed workflow outcomes are reported separately as mutable operational health.",
        "snapshot-bound source footprint and measured complexity evidence were evaluated without score override.",
        "sustainable delivery capacity is derived from immutable architecture maintainability and workflow automation; mutable activity volume is unscored context.",
    ):
        assert f'["{english}",' in localization

    for spanish in (
        "Se analizaron señales ejecutables del código fuente del commit exacto",
        "Los manifiestos autoritativos y la evidencia contextual de dependencias",
        "La evidencia de secretos con historial",
        "La evidencia de Bandit, Semgrep, ESLint y TypeScript",
        "La madurez de la configuración de CI/CD",
        "La huella del código fuente vinculada a la instantánea",
        "La capacidad de entrega sostenible",
    ):
        assert spanish in localization


def test_dynamic_terminal_executive_summary_is_strictly_pattern_bound() -> None:
    localization = source(
        "apps/web/app/assessment/AssessmentSpanishLocalization.ts"
    )

    assert "const NATIVE_COMPREHENSIVE_EXECUTIVE = /^NICO completed" in localization
    assert "([0-9a-f]{40})" in localization
    assert "localizedNativeComprehensiveExecutive(source)" in localization
    assert "Todas las etapas automatizadas representadas en este paquete" in localization
    assert "no constituyen aprobación del cliente ni autorización de entrega" in localization


def test_composite_assurance_state_has_deliberate_es_mx_label() -> None:
    status = source("apps/web/app/assessment/assessmentStatus.ts")

    assert 'value.includes("provisional_strong")' in status
    assert 'value.includes("human_review_required")' in status
    assert "Fuerte provisional — Revisión humana obligatoria" in status
    assert "Provisional Strong — Human Review Required" in status


def test_material_finding_priority_constraint_is_fully_localized() -> None:
    translated = _translate_presentation(
        "4 verified material finding(s) require disposition."
    )

    assert translated == "4 hallazgos materiales verificados requieren disposición."
    assert "finding(s)" not in translated
    assert "require disposition" not in translated
