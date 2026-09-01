from __future__ import annotations

import io

import pytest
from reportlab.pdfgen import canvas

from nico.comprehensive_current_report_truth_parity_v1 import (
    assert_spanish_client_copy_is_localized,
    install_comprehensive_current_report_truth_parity_v1,
    normalize_ci_presentation_lines,
    strict_spanish_presentation_v1,
)
from nico.comprehensive_four_phase_model_v1 import (
    build_four_phase_program,
    four_phase_markdown,
)


def _canonical(*, language: str = "en", explicit_review_ready: bool = False) -> dict:
    value = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_current_report_truth",
            "report_language": language,
        },
        "report_language": language,
        "assessment_state": "review_required",
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "completed_applicable_analyzers": 9,
        "incomplete_applicable_analyzers": 0,
        "assessment": {
            "canonical_scanner_finding_register": {
                "technical_triage": {
                    "technical_triage_coverage_pct": 100.0,
                    "human_review_work_units": 138,
                    "candidates_requiring_individual_human_attention": 132,
                    "grouped_review_eligible_candidates": 70,
                    "grouped_human_review_clusters": 6,
                }
            }
        },
    }
    if explicit_review_ready:
        value["review_package_ready"] = True
    return value


def _pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, invariant=1)
    y = 760
    for line in lines:
        page.drawString(40, y, line)
        y -= 18
    page.showPage()
    page.save()
    return buffer.getvalue()


def test_phase2_is_ready_for_review_before_late_lifecycle_flag_is_attached() -> None:
    program = build_four_phase_program(_canonical(explicit_review_ready=False))

    assert program["phases"][1]["status"] == "ready_pending_human_decision"
    assert program["human_review_required"] is True
    assert program["human_approval_completed"] is False
    assert program["client_delivery_allowed"] is False

    english = four_phase_markdown(_canonical(), spanish=False)
    assert "READY FOR REVIEW - HUMAN DISPOSITIONS PENDING" in english
    assert "| 2 | Human Review by Exception | NOT READY |" not in english

    spanish = four_phase_markdown(_canonical(language="es-MX"), spanish=True)
    assert "LISTA PARA REVISIÓN - DISPOSICIONES HUMANAS PENDIENTES" in spanish
    assert "| 2 | Revisión humana por excepción | NO LISTA |" not in spanish


def test_phase2_remains_not_ready_when_technical_triage_is_incomplete() -> None:
    canonical = _canonical()
    canonical["assessment"]["canonical_scanner_finding_register"]["technical_triage"][
        "technical_triage_coverage_pct"
    ] = 99.0

    program = build_four_phase_program(canonical)

    assert program["phases"][1]["status"] == "not_ready"
    assert program["client_delivery_allowed"] is False


def test_current_report_installer_repairs_case_insensitive_toc_title_matching() -> None:
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    install_comprehensive_current_report_truth_parity_v1()

    resolved = cleanup._outline_title(
        "NICO Comprehensive · comprun_test · AUTOMATED DRAFT\n"
        "Code audit\n"
        "STRONG · 96/100"
    )
    assert resolved == "Code audit"


def test_embedded_spanish_client_copy_is_localized_without_changing_source_tokens() -> None:
    from nico.comprehensive_spanish_presentation_parity_v2 import _safe_es

    install_comprehensive_current_report_truth_parity_v1()

    samples = {
        "top_technical_priorities[1].reason: Sustainable delivery capacity is derived from immutable architecture maintainability and workflow automation; mutable activity volume is unscored context.": "La capacidad de entrega sostenible",
        "top_technical_priorities[2].reason: Exact-commit executable source signals were analyzed without promoting comments, strings, detector definitions, examples, or tests.": "Se analizaron las señales ejecutables",
        "top_technical_priorities[3].reason: Authoritative manifests and contextual dependency evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability.": "Los manifiestos autoritativos",
        "executive_briefing.medium_term_actions[0]: Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.": "Reforzar los límites de arquitectura",
        "recommended_roles[0].role_category: Cybersecurity specialist": "Especialista en ciberseguridad",
        "maturity_level: Exceptional": "maturity_level: Excepcional",
        "Job success rate: 100%.": "Tasa de éxito de trabajos: 100%.",
        "Material confirmado findings: 0.": "Hallazgos materiales confirmados: 0.",
        "Non-success deployment classification: Not available.": "Clasificación de despliegues no exitosos: No disponible.",
    }
    for source, expected in samples.items():
        translated = _safe_es(source)
        assert expected in translated

    source_atom = "nico/comprehensive_decision_grade_model_v5.py"
    assert _safe_es(source_atom) == source_atom


def test_spanish_final_surface_gate_rejects_reintroduced_english_copy() -> None:
    canonical = _canonical(language="es-MX")
    clean_pdf = _pdf("Registro de candidatos que requieren revisión")
    assert_spanish_client_copy_is_localized(
        canonical,
        "Resumen ejecutivo",
        "<p>Resumen ejecutivo</p>",
        clean_pdf,
    )

    leaked_pdf = _pdf("Review-Required Candidate Register")
    with pytest.raises(ValueError, match="English presentation copy"):
        assert_spanish_client_copy_is_localized(
            canonical,
            "Resumen ejecutivo",
            "<p>Resumen ejecutivo</p>",
            leaked_pdf,
        )

    deployment_leak = _pdf("Non-success deployment classification: Not available.")
    with pytest.raises(ValueError, match="English presentation copy"):
        assert_spanish_client_copy_is_localized(
            canonical,
            "Resumen ejecutivo",
            "<p>Resumen ejecutivo</p>",
            deployment_leak,
        )


def test_github_pagination_limitation_has_exact_spanish_contract() -> None:
    install_comprehensive_current_report_truth_parity_v1()

    assert strict_spanish_presentation_v1(
        "GitHub operational collections are bounded to one provider page; "
        "complete Link-header pagination proof was not retained.",
        "unavailable",
    ) == (
        "Las recopilaciones operativas de GitHub están limitadas a una página del "
        "proveedor; no se conservó evidencia completa de paginación mediante el "
        "encabezado Link."
    )

    assert strict_spanish_presentation_v1(
        "Required source evidence was acquired from credential-free exact-SHA Git "
        "because GitHub API tree collection was unavailable.",
        "unavailable",
    ) == (
        "La evidencia fuente requerida se adquirió mediante Git del SHA exacto sin "
        "credenciales porque la recopilación del árbol mediante la API de GitHub no "
        "estaba disponible."
    )

    assert strict_spanish_presentation_v1(
        "Required source evidence was acquired from credential-free exact-SHA Git "
        "to preserve the anonymous public access binding without depending on GitHub "
        "API object-read quota.",
        "unavailable",
    ) == (
        "La evidencia fuente requerida se adquirió mediante Git del SHA exacto sin "
        "credenciales para conservar la vinculación de acceso público anónimo sin "
        "depender de la cuota de lectura de objetos de la API de GitHub."
    )


def test_gitlab_scanner_unavailability_has_exact_spanish_contract() -> None:
    install_comprehensive_current_report_truth_parity_v1()

    samples = {
        "pip-audit: requirements.txt was not found.": (
            "pip-audit: no se encontró requirements.txt."
        ),
        "npm-audit: No package-lock.json with an adjacent package.json was found.": (
            "npm-audit: no se encontró package-lock.json junto a un package.json."
        ),
        "osv-scanner: scanner JSON output could not be parsed: line 1 column 1; "
        "scanner JSON output could not be parsed: line 1 column 1": (
            "osv-scanner: no fue posible analizar la salida JSON del analizador: línea 1, columna 1; "
            "no fue posible analizar la salida JSON del analizador: línea 1, columna 1"
        ),
        "eslint: No supported JavaScript or TypeScript source files were found in apps/web/app.": (
            "eslint: no se encontraron archivos de código fuente JavaScript o TypeScript compatibles en apps/web/app."
        ),
        "typescript: typescript did not retain a complete exact-SHA scanner record.": (
            "typescript: TypeScript no conservó un registro completo del analizador para el SHA exacto."
        ),
    }

    for source, expected in samples.items():
        assert strict_spanish_presentation_v1(source, "unavailable") == expected


def test_spanish_final_surface_gate_allows_exact_user_and_technical_fragments() -> None:
    canonical = _canonical(language="es-MX")
    literal = (
        "Dato aportado por el cliente · Alcance autorizado: tool=Bandit; "
        "package=requests; installed=2.31.0; fixed=2.32.0; "
        "location=nico/admin_security.py; disposition=review_required"
    )

    assert_spanish_client_copy_is_localized(
        canonical,
        f"## Resumen de evidencia del cliente\n\n- {literal}",
        f"<p>{literal}</p>",
        _pdf(literal),
    )


def test_empty_legacy_native_control_vector_is_not_presented_as_zero_over_zero() -> None:
    result = normalize_ci_presentation_lines(
        [
            "A. CI/CD configuration maturity: 100/100; exact-SHA match=True; "
            "explicit permissions=True; immutable controls=0/0."
        ]
    )

    assert "0/0" not in result[0]
    assert "native-control vector=not applicable" in result[0]
    assert "provider-neutral objective coverage is reported separately" in result[0]


def test_installer_preserves_scoring_and_human_approval_boundaries() -> None:
    state = install_comprehensive_current_report_truth_parity_v1()

    assert state["case_insensitive_toc_matching"] is True
    assert state["spanish_embedded_phrase_localization"] is True
    assert state["empty_native_ci_vector_not_rendered_as_zero_over_zero"] is True
    assert state["final_spanish_leak_gate"] is True
    assert state["scores_unchanged"] is True
    assert state["candidate_dispositions_unchanged"] is True
    assert state["human_review_required"] is True
    assert state["client_delivery_allowed"] is False
