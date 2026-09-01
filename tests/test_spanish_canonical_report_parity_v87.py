from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


_REVIEW_SECTION_IDS = (
    "functional_qa",
    "platform_parity",
    "historical_trends_and_change_failure",
    "requirements_traceability",
    "stakeholder_and_business_alignment",
    "risk_reduction_and_executive_briefing",
    "six_month_roadmap",
    "staffing_sequencing_and_cost",
)


def _shape(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    return type(value).__name__


def test_spanish_review_copy_is_derived_from_the_english_section_contract() -> None:
    from nico.comprehensive_client_review_companion_v5 import _base_section_details

    for section_id in _REVIEW_SECTION_IDS:
        english = _base_section_details(section_id, spanish=False)
        spanish = _base_section_details(section_id, spanish=True)
        assert _shape(spanish) == _shape(english)
        for field in ("can_conclude", "cannot_conclude", "required_input"):
            assert len(spanish[field]) == len(english[field])

    assert (
        "Ningún fallo terminal de ejecución de analizadores se trata como aceptación funcional."
        in _base_section_details("functional_qa", spanish=True)["can_conclude"]
    )
    assert (
        "La madurez de la configuración inmutable de CI permanece separada de los resultados históricos."
        in _base_section_details(
            "historical_trends_and_change_failure",
            spanish=True,
        )["can_conclude"]
    )


def test_spanish_decision_summary_is_localized_before_pdf_layout() -> None:
    from nico import comprehensive_report_package as report_package
    from nico.comprehensive_decision_summary_truth_v1 import (
        install_comprehensive_decision_summary_truth_v1,
    )

    install_comprehensive_decision_summary_truth_v1()
    summary = report_package._decision_summary(
        {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "report_language": "es-MX",
        },
        {
            "report_language": "es-MX",
            "limited_review_section_count": 7,
            "maturity_signal": {"level": "Sólido", "score": 89},
        },
        [],
    )

    assert summary.startswith(
        "NICO generó un borrador automatizado de Evaluación Técnica Integral"
    )
    assert "7 secciones de revisión del cliente" in summary
    assert "autorización de entrega al cliente" in summary
    assert "NICO generated an automated" not in summary

    limited_summary = report_package._decision_summary(
        {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "report_language": "es-MX",
        },
        {
            "report_language": "es-MX",
            "maturity_signal": {"level": "Sólido", "score": 89},
        },
        [{"title": "QA funcional", "status": "failed"}],
    )
    assert (
        "1 etapa automatizada tiene una limitación terminal de ejecución: QA funcional."
        in limited_summary
    )
    assert "Ninguna etapa automatizada" not in limited_summary


def test_spanish_public_provider_stage_badge_is_fully_localized() -> None:
    from nico.comprehensive_spanish_canonical_report_v87 import (
        _translate_presentation,
    )

    assert _translate_presentation("Provider: GitHub.") == "Proveedor: GitHub."
    assert _translate_presentation(
        "PROCESSING COMPLETE · EVIDENCE LIMITED"
    ) == "PROCESAMIENTO COMPLETO · EVIDENCIA LIMITADA"
    assert _translate_presentation(
        "PROCESSING COMPLETE · AUTHORITATIVE REQUIREMENTS NOT SUPPLIED"
    ) == (
        "PROCESAMIENTO COMPLETO · REQUISITOS AUTORITATIVOS NO PROPORCIONADOS"
    )
    assert _translate_presentation("- Provider: GitHub.") == "- Proveedor: GitHub."
    assert _translate_presentation(
        "Estado: PROCESSING COMPLETE · EVIDENCE LIMITED"
    ) == "Estado: PROCESAMIENTO COMPLETO · EVIDENCIA LIMITADA"


def test_spanish_canonical_localization_preserves_machine_truth_and_translates_native_copy() -> None:
    import pytest

    from nico.comprehensive_spanish_canonical_report_v87 import (
        _localize_tree,
        _render_inputs,
        _translate_presentation,
        render_spanish_markdown,
        render_spanish_pdf,
    )

    machine_truth = {
        "status": "blocked",
        "state": "unavailable",
        "execution_status": "failed",
        "presented_status": "review_required",
        "path": "apps/web/app/operations/page.tsx",
        "source_excerpt": 'if status == "FAILED":',
        "summary": (
            "Exact-commit executable source signals were analyzed without "
            "promoting comments, strings, detector definitions, examples, or tests."
        ),
    }
    localized = _localize_tree(machine_truth)
    for key in ("status", "state", "execution_status", "presented_status", "path", "source_excerpt"):
        assert localized[key] == machine_truth[key]
    assert localized["summary"].startswith(
        "Se analizaron las señales ejecutables del código fuente del commit exacto"
    )

    native_copy = (
        "No lockfile evidence was found in the captured snapshot.",
        "One or more dependency analyzers were unavailable.",
        "Workflow files at assessed commit: 40.",
        "Historical workflow, job, and deployment outcomes are retained as an unscored operational trend.",
        "The delivery-capacity score is 60% architecture maintainability and 40% immutable workflow automation.",
        "Commit, pull-request, merge, job, and deployment counts are retained as trend context and have no score effect.",
        "3 material scanner finding(s) require immediate human disposition.",
        "3 review_required scanner candidate(s) were retained by count, but their raw payloads were unavailable to the canonical finding register.",
    )
    for source in native_copy:
        translated = _translate_presentation(source)
        assert translated != source
        assert not any(
            marker in translated
            for marker in (
                "lockfile evidence",
                "dependency analyzers were unavailable",
                "Workflow files at assessed commit",
                "are retained as an unscored",
                "delivery-capacity score",
                "have no score effect",
                "scanner finding(s)",
                "scanner candidate(s)",
            )
        )

    assert _translate_presentation("Not supplied") == "No proporcionado"

    with pytest.raises(ValueError, match="missing Spanish presentation translation for summary"):
        _localize_tree(
            {
                "summary": (
                    "The newly introduced workflow summary remains pending human review."
                )
            }
        )

    raw_scanner_message = (
        "The application does not verify the token before the request is authorized."
    )
    _, localized_assessment, _, _ = _render_inputs(
        {
            "identity": {},
            "assessment": {
                "canonical_scanner_finding_register": {
                    "findings": [{"evidence": raw_scanner_message}]
                }
            },
            "stage_summaries": [],
        }
    )
    assert (
        localized_assessment["canonical_scanner_finding_register"]["findings"][0]["evidence"]
        == raw_scanner_message
    )

    collision_canonical = {
        "identity": {
            "repository": "Org/Pending",
            "run_id": "GREEN",
            "commit_sha": "abc123",
            "evidence_ledger_id": "YELLOW",
            "customer_id": "BLOCKED",
            "project_id": "UNAVAILABLE",
            "report_language": "es-MX",
        },
        "assessment": {
            "sections": [
                {
                    "id": "code_audit",
                    "label": "Code Audit",
                    "status": "green",
                    "presented_status": "green",
                    "score": 100,
                    "presented_score": 100,
                    "summary": "Exact-commit sampled code signals and repository structure were reviewed.",
                    "evidence": [],
                    "findings": [],
                    "unavailable": [],
                }
            ],
            "maturity_signal": {},
        },
        "stage_summaries": [],
    }
    collision_markdown = render_spanish_markdown(collision_canonical)
    collision_pdf, _ = render_spanish_pdf(collision_canonical)
    from pypdf import PdfReader
    import io

    collision_pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(collision_pdf)).pages
    )
    for literal in (
        "Org/Pending",
        "GREEN",
        "YELLOW",
        "BLOCKED",
        "UNAVAILABLE",
    ):
        assert literal in collision_markdown
    for literal in (
        "Org/Pending",
        "GREEN",
        "BLOCKED",
        "UNAVAILABLE",
    ):
        assert literal in collision_pdf_text
    assert "VERDE" in collision_markdown
    assert "VERDE" in collision_pdf_text


def test_spanish_scanner_limitations_localize_the_production_truth_contract() -> None:
    import pytest

    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    from nico.comprehensive_spanish_current_copy_worker_v98 import (
        install_comprehensive_spanish_current_copy_worker_v98,
    )

    # Bind the current production worker explicitly so this assertion cannot
    # depend on which localization compatibility module pytest imported first.
    install_comprehensive_spanish_current_copy_worker_v98()

    source = {
        "summary": (
            "Technical maturity remains based on exact-commit technical controls. "
            "Evidence-Adjusted readiness is 93/100 versus technical maturity 93/100. "
            "NICO retains 639 review-required candidates and 0 confirmed material "
            "findings as explicit review context. Candidate volume, clustering and "
            "reviewer workload do not change numeric security or readiness scores."
        ),
        "evidence": [
            (
                "Candidate volume and reviewer workload are operational review metrics "
                "and have no numeric technical-maturity or Evidence-Adjusted score effect."
            ),
            (
                "pip-audit: status=unavailable; exact_commit_match=True; "
                "verified_complete=False; findings=0; artifact_hash=unavailable"
            ),
            (
                "semgrep: status=completed; current_run=True; exact_commit_match=True; "
                "verified_complete=True; findings=2; artifact_hash=abc123"
            ),
            (
                "scanner_execution_records[0].failure_reason: pip-audit is not "
                "installed in the worker image."
            ),
            "Workflow outcome classes: No classified workflow outcomes retained.",
            "Historical genuine-failure rate: None",
        ],
        "findings": [
            "Actionable hotspot verified/report.py:10 · verified · complexity 40."
        ],
        "unavailable": [
            (
                "pip-audit exact-SHA evidence remains completed: "
                "completion requirements were not met"
            ),
            (
                "semgrep exact-SHA evidence remains failed: status=failed; "
                "current_run_not_proven; execution_not_observed_for_this_report; "
                "exact_commit_match_not_proven; scanner_verification_not_proven; "
                "complete_artifact_capture_not_proven; artifact_hash_missing; "
                "full_git_history_not_verified"
            ),
        ]
    }

    localized = _localize_tree(source)

    assert localized["summary"] == (
        "La madurez técnica sigue basándose en controles técnicos del commit exacto. "
        "La preparación ajustada por evidencia es 93/100 frente a una madurez técnica "
        "de 93/100. NICO conserva 639 candidatos que requieren revisión y 0 hallazgos "
        "materiales confirmados como contexto explícito de revisión. El volumen de "
        "candidatos, la agrupación y la carga de trabajo de revisión no modifican las "
        "puntuaciones numéricas de seguridad ni de preparación."
    )
    assert localized["evidence"] == [
        (
            "El volumen de candidatos y la carga de trabajo del revisor son métricas "
            "operativas de revisión y no tienen efecto numérico sobre la madurez "
            "técnica ni sobre la puntuación de Ajuste por evidencia."
        ),
        (
            "pip-audit: estado=no disponible; coincidencia_commit_exacto=sí; "
            "verificación_completa=no; hallazgos=0; hash_artefacto=no disponible"
        ),
        (
            "semgrep: estado=completada; ejecución_actual=sí; "
            "coincidencia_commit_exacto=sí; verificación_completa=sí; hallazgos=2; "
            "hash_artefacto=abc123"
        ),
        (
            "scanner_execution_records[0].failure_reason: pip-audit no "
            "está instalado en la imagen del entorno de ejecución."
        ),
        (
            "Clases de resultados de los flujos de trabajo: no se conservaron "
            "resultados clasificados."
        ),
        "Tasa histórica de fallos reales: no disponible",
    ]
    assert localized["findings"] == [
        "Punto crítico accionable verified/report.py:10 · verified · complejidad 40."
    ]
    assert localized["unavailable"] == [
        (
            "La evidencia de pip-audit para el SHA exacto permanece completada: "
            "no se cumplieron los requisitos de finalización"
        ),
        (
            "La evidencia de semgrep para el SHA exacto permanece fallida: "
            "estado=fallida; no se demostró que perteneciera a la ejecución actual; "
            "no se observó la ejecución para este informe; no se demostró la "
            "coincidencia con el commit exacto; no se demostró la verificación del "
            "analizador; no se demostró la captura completa del artefacto; falta el "
            "hash del artefacto; no se verificó el historial Git completo"
        ),
    ]
    assert "pip-audit" in localized["unavailable"][0]
    assert "semgrep" in localized["unavailable"][1]

    technical_failures = _localize_tree(
        {
            "unavailable": [
                (
                    "bandit exact-SHA evidence remains failed: Bandit CSV output "
                    "could not be parsed: ValueError"
                ),
                (
                    "gitleaks exact-SHA evidence remains failed: Gitleaks report "
                    "could not be parsed as JSON."
                ),
                "semgrep exact-SHA evidence remains failed: Tool timed out.",
                (
                    "semgrep exact-SHA evidence remains failed: "
                    "status=failed due to timeout"
                ),
                "semgrep exact-SHA evidence remains failed: status=fatal",
            ]
        }
    )["unavailable"]
    assert all("detalle técnico original:" in value for value in technical_failures)
    assert "Bandit CSV output could not be parsed: ValueError" in technical_failures[0]
    assert "Gitleaks report could not be parsed as JSON." in technical_failures[1]
    assert "Tool timed out." in technical_failures[2]
    assert "detalle técnico original:" in technical_failures[3]
    assert "status=failed due to timeout" in technical_failures[3]
    assert "detalle técnico original:" in technical_failures[4]
    assert "status=fatal" in technical_failures[4]

    with pytest.raises(ValueError, match="missing Spanish scanner status translation"):
        _localize_tree(
            {
                "unavailable": [
                    "semgrep exact-SHA evidence remains new_status: technical detail"
                ]
            }
        )


def test_spanish_localizes_authoritative_ci_history_categories_and_empty_history() -> None:
    from nico.ci_history_classification_v1 import classify_workflow_history
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    from nico.phase5_report_truth_v2 import (
        install_phase5_report_truth_v2,
        reconcile_phase5_report_truth,
    )

    install_phase5_report_truth_v2()

    def assessment() -> dict[str, Any]:
        return {
            "maturity_signal": {"score": 85, "presented_score": 85},
            "canonical_evidence_adjusted_score": 85,
            "sections": [
                {
                    "id": section_id,
                    "label": section_id,
                    "score": 85,
                    "evidence": [],
                    "findings": [],
                    "unavailable": [],
                }
                for section_id in (
                    "dependency_health",
                    "secrets_review",
                    "static_analysis",
                    "ci_cd",
                    "architecture_debt",
                )
            ],
            "findings_register": [],
            "human_review_required": True,
            "client_ready": False,
        }

    classified_runs = [
        {"id": 1, "name": "CI", "status": "queued", "conclusion": "", "event": "push"},
        {"id": 2, "name": "CI", "status": "completed", "conclusion": "neutral", "event": "push"},
        {"id": 3, "name": "CI superseded", "status": "completed", "conclusion": "cancelled", "event": "push"},
        {"id": 4, "name": "CI manual", "status": "completed", "conclusion": "cancelled", "event": "push"},
        {"id": 5, "name": "CI", "status": "completed", "conclusion": "cancelled", "event": "push"},
        {"id": 6, "name": "CI", "status": "completed", "conclusion": "success", "event": "push"},
        {"id": 7, "name": "CI", "status": "completed", "conclusion": "failure", "event": "push"},
        {"id": 8, "name": "CI", "status": "completed", "conclusion": "stale", "event": "push"},
        {"id": 9, "name": "CI", "status": "completed", "conclusion": "", "event": "push"},
    ]

    expected = (
        (
            [],
            [
                "Clases de resultados de los flujos de trabajo: no se conservaron resultados clasificados.",
                "Tasa histórica de fallos reales: no disponible",
            ],
        ),
        (
            classified_runs,
            [
                "Clases de resultados de los flujos de trabajo: activas no históricas=1; "
                "cancelaciones esperadas o sin clasificar=1; fallos reales=1; fallos de "
                "infraestructura=1; cancelaciones manuales=1; neutrales u omitidas=1; "
                "exitosas=1; cancelaciones sustituidas=1; desconocidas que requieren "
                "revisión=1.",
                "Tasa histórica de fallos reales: 0.5",
            ],
        ),
    )
    for runs, expected_evidence in expected:
        summary = classify_workflow_history(runs)
        result = reconcile_phase5_report_truth(
            assessment(),
            {"repository_and_delivery_evidence": {"ci": summary}},
        )
        ci_section = next(
            section for section in result["sections"] if section["id"] == "ci_cd"
        )
        classification_evidence = [
            value
            for value in ci_section["evidence"]
            if value.startswith(
                ("Workflow outcome classes:", "Historical genuine-failure rate:")
            )
        ]
        assert _localize_tree({"evidence": classification_evidence})["evidence"] == expected_evidence


def test_spanish_localizes_reachable_unavailable_evidence_contracts() -> None:
    import pytest

    from nico.comprehensive_spanish_canonical_report_v87 import (
        _localize_tree,
        _translate_presentation_field,
    )
    from nico.full_assessment_ci_evidence import _safe_note as ci_safe_note
    from nico.full_assessment_complexity_evidence import collect_complexity_evidence
    from nico.full_assessment_complexity_repository import (
        _safe_note as complexity_safe_note,
    )
    from nico.full_assessment_repository_evidence import _safe_api_note

    base_collect_complexity_evidence = getattr(
        collect_complexity_evidence,
        "__wrapped__",
        collect_complexity_evidence,
    )
    js_note = next(
        note
        for note in base_collect_complexity_evidence(
            {"src/verified.ts": "export function verified() { return true; }"}
        )["unavailable_data_notes"]
        if note.startswith("JavaScript and TypeScript complexity uses")
    )
    repository_notes = [
        _safe_api_note(label, error)
        for label in (
            "Repository metadata",
            "Repository file-profile evidence",
            "Workflow file evidence",
            "Commit history",
            "Pull-request history",
            "Workflow-run history",
        )
        for error in ("404 missing", "403 forbidden", "429 rate limit", "500 server")
    ]
    ci_notes = [
        ci_safe_note(label, error)
        for label in (
            "Workflow jobs for run 42",
            "GitHub deployment evidence",
            "Deployment status for 77",
        )
        for error in ("404 missing", "403 forbidden", "429 rate limit", "500 server")
    ]
    source = {
        "unavailable": [
            js_note,
            (
                "TypeScript compiler AST evidence was unavailable for this run; "
                "JavaScript and TypeScript values use bounded lexical fallback and "
                "remain review-limited."
            ),
            "1 source parser limitation(s) were retained in the architecture evidence.",
            "No eligible first-party source files were present in the exact-SHA source profile.",
            (
                "Scanner evidence is not client-ready until every required scanner "
                "completes and every redacted raw artifact is retained."
            ),
            "No workflow files were present in the captured repository snapshot.",
            (
                "Captured-commit collection reached its bounded runtime; remaining "
                "files are unavailable for this run."
            ),
            (
                "2 captured-commit profile item(s) were unavailable; complexity "
                "coverage is limited to readable sampled files."
            ),
            (
                "1 repository profile item(s) were unavailable; complexity coverage "
                "is limited to readable sampled files."
            ),
            (
                "1 Python source file(s) could not be parsed and were excluded from "
                "complexity metrics."
            ),
            "No eligible source files were present in the authorized repository text-file sample.",
            "Workflow jobs for run 42 were returned without a jobs list.",
            "GitHub deployment evidence was returned without a deployment list.",
            (
                "OSV lookup skipped because no exact normalized dependency versions "
                "were available from the inspected manifests."
            ),
            "OSV lookup did not complete within the bounded dependency-review window.",
            (
                "OSV lookup returned HTTP 429; dependency vulnerability status is "
                "incomplete."
            ),
            "OSV lookup returned a non-JSON response.",
            "OSV lookup unavailable: HTTPSConnectionPool read timed out",
            (
                "Exact-SHA source archive profiling was unavailable: TimeoutError. "
                "Existing bounded file evidence remains visible."
            ),
            (
                "Exact-SHA source archive was unavailable because the snapshot commit "
                "was missing."
            ),
            (
                "bandit exact-SHA evidence remains unavailable: bandit is not "
                "installed in the worker image."
            ),
            *repository_notes,
            *ci_notes,
            *(complexity_safe_note(error) for error in (
                "404 missing",
                "403 forbidden",
                "429 rate limit",
                "500 server",
            )),
        ],
        "evidence": [
            (
                "OSV returned 2 vulnerability record(s) for "
                "PyPI:verified-package@1.2.3: GHSA-1, CVE-2."
            ),
            (
                "OSV returned 1 vulnerability record(s) for "
                "npm:@scope/verified@2.0.0: GHSA-3."
            ),
            "OSV returned no vulnerability records for 1 pinned dependency query/queries.",
            "Workflow jobs for run 123 were unavailable through the GitHub API.",
            (
                "repository_evidence.unavailable_data_notes[0]: No workflow files "
                "were present in the captured repository snapshot."
            ),
            (
                "technical_analysis.complexity.unavailable_data_notes[2]: 1 Python "
                "source file(s) could not be parsed and were excluded from complexity metrics."
            ),
            (
                "snapshot.guardrail: All repository file evidence and scanner execution "
                "for this run must use this exact commit SHA or be marked unavailable."
            ),
        ],
    }

    localized = _localize_tree(source)
    rendered = "\n".join((*localized["unavailable"], *localized["evidence"]))

    for english in (
        " was unavailable ",
        "Workflow jobs for run",
        "OSV lookup ",
        "OSV returned ",
        "could not be parsed",
        "No workflow files were present",
    ):
        assert english not in rendered
    assert "PyPI:verified-package@1.2.3" in rendered
    assert "GHSA-1, CVE-2" in rendered
    assert "repository_evidence.unavailable_data_notes[0]" in rendered
    assert "technical_analysis.complexity.unavailable_data_notes[2]" in rendered
    assert "snapshot.guardrail" in rendered
    assert "All repository file evidence and scanner execution" not in rendered
    assert "Se conservó 1 limitación del analizador" in rendered
    assert "1 elemento del perfil del repositorio no estaba disponible" in rendered

    identity_collisions = (
        (
            "OSV returned 1 vulnerability record(s) for "
            "npm:is-not@1.0.0: GHSA-identity.",
            "evidence",
            "npm:is-not@1.0.0",
        ),
        (
            "Decompose the highest-complexity modules first, beginning with "
            "should-not, and add characterization tests plus CI complexity thresholds.",
            "recommendation",
            "should-not",
        ),
        (
            "Actionable hotspot src/should-not.py:10 · should-not · complexity 40.",
            "findings",
            "src/should-not.py:10 · should-not",
        ),
        (
            "Captured-commit file should-not was unavailable through the GitHub API.",
            "unavailable",
            "should-not",
        ),
    )
    for original, key, protected_literal in identity_collisions:
        translated = _translate_presentation_field(original, key)
        assert translated != original
        assert protected_literal in translated

    assert _translate_presentation_field(
        (
            "Source-reviewed analyzer dispositions: 1 bounded nonblocking record(s); "
            "full rationale retained in canonical JSON."
        ),
        "evidence",
    ).startswith(
        "Disposiciones de analizadores revisadas en el código fuente: 1 registro "
        "acotado no bloqueante"
    )

    for malformed in (
        "Workflow outcome classes: success=2. Additional context",
        "Historical genuine-failure rate: pending review",
        "Captured-commit root listing unavailable.",
        "1 captured-commit profile item(s) unavailable.",
        "1 Python source file(s) unavailable.",
        "Exact-SHA source archive profiling unavailable.",
        "repository_evidence.unavailable_data_notes[0] unavailable.",
        "snapshot.guardrail unavailable.",
        "Actionable hotspot src/foo.py:10",
        "Actionable production/report hotspots: 2.",
    ):
        with pytest.raises(ValueError, match="unrecognized Spanish presentation contract"):
            _translate_presentation_field(malformed, "evidence")


def test_spanish_localizes_generated_premium_executive_risk_copy() -> None:
    from nico.comprehensive_executive_risk_truth_v7 import (
        reconcile_executive_risk_truth,
    )
    from nico.comprehensive_premium_synthesis_v6 import polish_assessment
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree

    categories = (
        "architecture",
        "evidence",
        "static",
        "dependency",
        "secret",
        "ci_cd",
        "code",
    )
    findings = [
        {
            "finding_id": f"FINDING-{index}",
            "category": category,
            "title": f"{category} source finding",
            "location": (
                "apps/web/app/verified.tsx:10"
                if category == "architecture"
                else f"apps/web/app/{category}.tsx:10"
            ),
            "priority": "P1",
            "confidence": "high",
            "evidence": "verified=true; severity=high",
            "impact": "Source impact retained in canonical truth.",
            "recommendation": "Source recommendation retained in canonical truth.",
        }
        for index, category in enumerate(categories)
    ]
    assessment = reconcile_executive_risk_truth(
        polish_assessment(
            {
                "sections": [{"id": "static_analysis", "score_value": 87}],
                "findings_register": findings,
                "maturity_signal": {},
            }
        )
    )

    localized = _localize_tree(assessment)
    risks = localized["executive_risk_register"]
    titles = {item["title"] for item in risks}

    assert "Complejidad concentrada en el frontend" in titles
    assert "El aseguramiento del análisis estático sigue limitado por revisión" in titles
    architecture = next(
        item
        for item in risks
        if item["title"] == "Complejidad concentrada en el frontend"
    )
    assert architecture["impact"].startswith(
        "Los módulos grandes y con muchas ramificaciones"
    )
    assert architecture["recommendation"].startswith(
        "Descomponer primero los módulos de mayor complejidad"
    )
    assert "verified" in architecture["recommendation"]
    assert "verificada" not in architecture["recommendation"]


def test_spanish_localizes_production_premium_roadmap_contract() -> None:
    from nico.comprehensive_spanish_canonical_report_v87 import (
        _looks_like_untranslated_english,
        _translate_presentation_field,
    )

    cases = {
        "impact": (
            "Assurance is constrained; no client defect is inferred.",
        ),
        "objective": (
            "Close evidence-integrity and release-reliability gaps before expanding client use.",
            "Eliminate worker resource failures, complete required analyzers, and retain exact finding locations without secret leakage.",
            "Reduce concentrated technical debt and make requirements traceable to acceptance evidence.",
            "Reduce concentrated complexity and duplicate logic while preserving behavior through characterization tests.",
            "Prove the complete operating model through telemetry, recovery evidence, and authorized external pilots.",
            "Validate user journeys, incident recovery, performance, and report usefulness on an authorized external repository.",
        ),
        "title": (
            "Classify and reduce CI/CD non-success history",
            "Decompose the highest-complexity hotspots",
        ),
        "acceptance_criteria": (
            "Bandit, Semgrep, Gitleaks, and TruffleHog complete twice against one exact SHA",
            "Every candidate has category, tool, severity, and safe location",
            "All retained non-success runs are cause-classified",
            "Recurring failure classes have owners and fixes",
            "Two consecutive acceptance windows meet the approved success threshold",
            "Top hotspots are split into bounded modules",
            "Target complexity and nesting thresholds pass",
            "Every committed requirement has an owner and acceptance test",
            "Express and Comprehensive complete on the pilot repository",
            "Backup/restore and restart recovery evidence is retained",
            "Reviewer approves or rejects the immutable package",
        ),
        "description": (
            "No client-specific labor rates, revenue, incident cost, or contract-penalty inputs were supplied.",
        ),
    }

    for key, values in cases.items():
        for source in values:
            translated = _translate_presentation_field(source, key)
            assert translated != source
            assert not _looks_like_untranslated_english(translated)


def test_terminal_spanish_report_localizes_current_scanner_ci_and_complexity_truth() -> None:
    from nico import phase6_canonical_truth_v2 as phase6_canonical
    from nico import phase6_final_remediation_v1 as phase6_final
    from nico.ci_history_classification_v1 import classify_workflow_history
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
    from nico.comprehensive_spanish_canonical_report_v87 import _render_inputs
    from nico.phase5_report_truth_v2 import (
        install_phase5_report_truth_v2,
        reconcile_phase5_report_truth,
    )

    commit_sha = "a" * 40
    tools = (
        "pip-audit",
        "npm-audit",
        "osv-scanner",
        "bandit",
        "semgrep",
        "eslint",
        "typescript",
        "gitleaks",
        "trufflehog",
    )
    scanner_results = [
        {
            "tool": tool,
            "status": "completed",
            "target_commit_sha": commit_sha,
            "verified_for_this_report": True,
            "output_capture_complete": True,
            "raw_artifact_capture_complete": True,
            "raw_artifact_retention_complete": True,
            "returncode_valid": True,
            "timed_out": False,
            "output_truncated": False,
            "current_run": True,
            "execution_observed_for_this_report": True,
            "scans_git_history": tool in {"gitleaks", "trufflehog"},
            "full_history_verified": tool in {"gitleaks", "trufflehog"},
            "artifact_hash": "b" * 64,
            "findings": [],
        }
        for tool in tools
    ]
    finding_summary = {
        "by_tool": {
            tool: {
                "raw": 0,
                "material": 0,
                "review_required": 0,
                "approved_or_nonblocking": 0,
                "excluded_test_only": 0,
            }
            for tool in tools
        }
    }
    raw_scanner_artifact = {
        "scan_id": "scan",
        "scanner_results": scanner_results,
        "finding_summary": finding_summary,
    }
    install_phase5_report_truth_v2()
    ci_history = classify_workflow_history(
        [
            {"id": 1, "name": "CI", "status": "completed", "conclusion": "success"},
            {"id": 2, "name": "CI", "status": "completed", "conclusion": "failure"},
            {
                "id": 3,
                "name": "CI superseded",
                "status": "completed",
                "conclusion": "cancelled",
            },
        ]
    )
    stage_results = {
        "immutable_repository_snapshot": {"commit_sha": commit_sha},
        "repository_and_delivery_evidence": {
            "repository_evidence": {
                "workflow_evidence": {"classified_history": ci_history}
            },
        },
        "dependency_security_static_analysis": {
            "status": "complete",
            "commit_sha": commit_sha,
            "scan_id": "scan",
            "summary": (
                "Dependency, static-analysis, secret, TypeScript, and history-aware "
                "scanner output was verified against the immutable commit."
            ),
            "scanner": {
                "scan_id": "scan",
                "status": "complete",
                "snapshot_match": True,
                "actual_commit_sha": commit_sha,
                "tools_requested": list(tools),
                "tools_run": list(tools),
                "unavailable_tools": [],
                "failed_tools": [],
                "timed_out_tools": [],
                "finding_summary": finding_summary,
            },
            "evidence": {
                "scan_id": "scan",
                "snapshot_match": True,
                "actual_commit_sha": commit_sha,
                "tools_run": list(tools),
                "raw": 0,
                "material": 0,
                "review": 0,
                "excluded": 0,
            },
            "unavailable_data_notes": [],
            "scanner_execution_records": compact_scanner_records(
                raw_scanner_artifact,
                commit_sha=commit_sha,
            ),
            "scanner_artifact_retention": {
                "record_count": len(tools),
                "verified_record_count": len(tools),
                "compact_records_only": True,
            },
        },
        "ci_cd_architecture_complexity_velocity": {
            "commit_sha": commit_sha,
            "all_required_checks_green": False,
            "complexity": {
                "high_complexity_functions": 2,
                "functions_measured": 2,
                "complexity_score": 60,
                "hotspots": [
                    {
                        "path": "nico/report.py",
                        "line": 10,
                        "name": "build_report",
                        "cyclomatic_complexity": 44,
                    },
                    {
                        "path": "tests/test_report.py",
                        "line": 5,
                        "name": "test_report",
                        "cyclomatic_complexity": 55,
                    },
                ],
            },
        },
    }
    assessment = {
        "commit_sha": commit_sha,
        "sections": [
            {
                "id": section_id,
                "label": section_id,
                "score": 80,
                "presented_score": 80,
                "score_value": 80,
                "evidence": [],
                "findings": [],
                "unavailable": [],
            }
            for section_id in (
                "dependency_health",
                "secrets_review",
                "static_analysis",
                "ci_cd",
                "architecture_debt",
            )
        ],
        "findings_register": [],
        "maturity_signal": {"score": 80, "presented_score": 80},
    }

    assessment = reconcile_phase5_report_truth(assessment, stage_results)
    assessment = phase6_final.reconcile_assessment(assessment, stage_results)
    assessment = phase6_canonical.reconcile_assessment_v2(
        assessment,
        stage_results,
    )
    _, localized, _, _ = _render_inputs(
        {
            "identity": {"report_language": "es-MX"},
            "assessment": assessment,
            "stage_summaries": [],
        }
    )

    sections = {item["id"]: item for item in localized["sections"]}
    assert "pip-audit" in localized["evidence_health_summary"]["completed_scanners"]
    assert not any(
        "pip-audit exact-SHA" in item or "completion requirements" in item
        for item in sections["dependency_health"]["unavailable"]
    )
    assert "Las cancelaciones se excluyen de la tasa de fallos reales." in (
        sections["ci_cd"]["evidence"]
    )
    assert any(
        item.startswith(
            "Estado de las verificaciones requeridas del commit evaluado: no verde"
        )
        for item in sections["ci_cd"]["evidence"]
    )
    assert any(
        item.startswith("Punto crítico accionable nico/report.py:10")
        for item in sections["architecture_debt"]["findings"]
    )


def test_same_canonical_package_has_exact_spanish_publication_parity() -> None:
    """Exercise both locales through the terminal production report stack."""

    repository_root = Path(__file__).resolve().parents[1]
    script = r'''
import base64
import copy
import hashlib
import html
import io
import re

from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth

from tests.test_comprehensive_report_package_v2 import _package as rich_package
from tests.test_phase9_comprehensive_report_integration_v1 import _result as phase9_result
from tests.test_v2_premium_report_renderer import _package as small_package
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package
from nico.comprehensive_spanish_client_surface_localization_v86 import (
    install_comprehensive_spanish_client_surface_localization_v86,
)


install_comprehensive_spanish_client_surface_localization_v86()

SMALL_ENGLISH_GOLDEN = {
    "markdown": ("2ca2efd359843c7a2c311a1036a6892fcc35c6c3f6e392d20238e89a66f5c6c0", 18849),
    "html": ("43d3a5097c673763501cc06bfa22921cbb963b59d77f4bb8cd92e0773c440343", 22724),
    # The authoritative separately rendered CI/CD boundary replaces the base
    # copy, so one semantic section now produces one physical body page.
    "pdf_base64": ("1141c8e8bb1e3eb76559597fe713e3f57021af614af9e54ba95612d336bb0bed", 175308),
    "pdf_sha256": "998a374973190f7c6c26562b32c8eea03522ed65ffe151f6a9031149344f31c2",
    "page_count": 21,
}
RICH_ENGLISH_GOLDEN = {
    "markdown": ("e170d72b9672962c562d5a31b9da62cb4d612a376d55c91588a0324bf1d01906", 20572),
    "html": ("ff966912bf11ddf474f5004d646c799e31fc5fb9f35a25b809954dccb41d1a26", 24753),
    "pdf_base64": ("e863419a86760cf8577246fd6472d53e10cce77c1509698847f9ac65129b1476", 254176),
    "pdf_sha256": "5ae3517d9f4810366fbfcf364ba94ef535caf24838c8b6c50c8bf5d36c302808",
    "page_count": 39,
}
PHASE9_ENGLISH_GOLDEN = {
    "markdown": ("51a2018ab77f58a5393987170771796db6ae6cfa6dbbf2a57d2ee672de15c7b7", 19585),
    "html": ("e09e9867f511b055a1e80b25902b3891f04279f0e5f2c656029e7d634fb050bc", 23784),
    "pdf_base64": ("26de7b7bea5a0361536f6460b58010702588f16ebc3d99c9592ba3b483b99037", 171856),
    "pdf_sha256": "7917dc79add4eb0fdcf76a2d987093a208b82ccb6a02b4b7a1c97921d40a2803",
    "page_count": 20,
}

SPANISH_OUTLINE = {
    "Four-Phase Assessment Program": "Programa de evaluación en cuatro fases",
    "Automated Technical Triage": "Triaje técnico automatizado",
    "Human Review by Exception": "Revisión humana por excepción",
    "Broader Professional Assessment": "Evaluación profesional ampliada",
    "Approval and Client Delivery": "Aprobación y entrega al cliente",
    "Table of Contents": "Índice",
    "Comprehensive Technical Assessment": "Evaluación Técnica Integral",
    "Executive Decision Brief": "Resumen ejecutivo para decisiones",
    "Priority Constraints and Decision Risks": "Restricciones prioritarias y riesgos de decisión",
    "Canonical Technical Scorecard": "Cuadro de puntuación técnica",
    "Code Audit": "Auditoría de código",
    "Dependency / Library Ecosystem": "Ecosistema de dependencias y bibliotecas",
    "Secrets Exposure Review": "Revisión de exposición de secretos",
    "Static Analysis": "Análisis estático",
    "CI/CD Analysis": "Análisis de CI/CD",
    "Architecture & Technical Debt": "Arquitectura y deuda técnica",
    "Velocity / Complexity": "Velocidad y complejidad",
    "Repository and Delivery Evidence": "Evidencia del repositorio y de entrega",
    "Evidence Reconciliation and Scoring": "Conciliación y puntuación de evidencia",
    "Architecture and Data Flow": "Arquitectura y flujo de datos",
    "Developer Delivery Process": "Proceso de entrega de desarrollo",
    "Historical Trends and Change Failure": "Tendencias históricas y fallos de cambio",
    "Authorization and Scope": "Autorización y alcance",
    "Dependency, Security, and Static Analysis": "Dependencias, seguridad y análisis estático",
    "CI/CD, Architecture, Complexity, and Velocity": "CI/CD, arquitectura, complejidad y velocidad",
    "Risk Reduction and Executive Briefing": "Reducción de riesgo y resumen ejecutivo",
    "CI/CD Operational Readiness and Historical Health": "Preparación operativa y salud histórica de CI/CD",
    "Compact Finding and Remediation Register": "Registro compacto de hallazgos y remediación",
    "Complete Exact-Source Index": "Índice completo de fuentes exactas",
    "Client Evidence Summary": "Resumen de evidencia del cliente",
    "Human Review and Acceptance Gate": "Puerta de revisión humana y aceptación",
    "Client Artifact Manifest": "Manifiesto de artefactos del cliente",
    "Human Review and Exact-Artifact Approval Record": "Registro de revisión humana y aprobación de artefactos exactos",
}


PHASE_OUTLINE_TITLES = {
    "Four-Phase Assessment Program",
    "Automated Technical Triage",
    "Human Review by Exception",
    "Broader Professional Assessment",
    "Approval and Client Delivery",
}


def render(package):
    result = rebuild_client_artifacts(copy.deepcopy(package))
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    pages = [page.extract_text() or "" for page in reader.pages]
    return result, reader, pages


def render_phase9(package):
    result = finalize_report_package(copy.deepcopy(package))["report_package"]
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    pages = [page.extract_text() or "" for page in reader.pages]
    return result, reader, pages


def rich_input(language):
    canonical = copy.deepcopy(rich_package()["report_package"]["json"])
    generated_at = "2026-08-04T16:15:00Z"
    canonical.update(
        {
            "report_language": language,
            "locale": language,
            "generated_at": generated_at,
            "generation_timestamp": generated_at,
        }
    )
    canonical["identity"].update(
        {"report_language": language, "generated_at": generated_at}
    )
    canonical["assessment"]["report_language"] = language
    return {"json": canonical}


def phase9_input(language):
    package = copy.deepcopy(phase9_result())
    canonical = package["report_package"]["json"]
    canonical.update({"report_language": language, "locale": language})
    canonical["identity"].update(
        {"report_language": language, "locale": language}
    )
    canonical["assessment"].update(
        {"report_language": language, "locale": language}
    )
    return package


def fingerprint(result):
    output = {}
    for field in ("markdown", "html", "pdf_base64"):
        value = result[field]
        output[field] = (hashlib.sha256(value.encode("utf-8")).hexdigest(), len(value))
    output["pdf_sha256"] = result["pdf_sha256"]
    output["page_count"] = result["pdf_page_count"]
    return output


def markdown_signature(markdown):
    output = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--"):
            continue
        heading = re.match(r"^(#{1,6})\s", line)
        if heading:
            output.append(f"h{len(heading.group(1))}")
        elif line.startswith("- [ ]"):
            output.append("check")
        elif line.startswith("- "):
            output.append("li")
        elif re.fullmatch(r"\|.*\|", line):
            output.append("table")
        else:
            output.append("p")
    return output


def html_signature(rendered):
    return re.findall(r"<(/?[A-Za-z][\w-]*)\b", rendered)


def outline_projection(reader):
    output = []

    def visit(items):
        for item in items or []:
            if isinstance(item, list):
                visit(item)
                continue
            output.append(
                (
                    getattr(item, "title", str(item)),
                    reader.get_destination_page_number(item) + 1,
                )
            )

    visit(reader.outline)
    return output


def assert_pdf_text_within_media_box(reader):
    violations = []
    for page_number, page in enumerate(reader.pages, start=1):
        left = float(page.mediabox.left)
        right = float(page.mediabox.right)

        def visit(text, cm, tm, font, font_size):
            value = str(text or "").rstrip("\n")
            if not value:
                return
            font_name = str((font or {}).get("/BaseFont") or "/Helvetica")
            font_name = font_name.split("+")[-1].lstrip("/") or "Helvetica"
            try:
                width = stringWidth(value, font_name, font_size)
            except Exception:
                width = stringWidth(value, "Helvetica", font_size)
            origin = cm[4] + (tm[4] * cm[0]) + (tm[5] * cm[2])
            horizontal_scale = abs((tm[0] * cm[0]) + (tm[1] * cm[2])) or 1.0
            edge = origin + (width * horizontal_scale)
            if origin < left - 0.5 or edge > right + 0.5:
                violations.append((page_number, origin, edge, value))

        page.extract_text(visitor_text=visit)
    assert not violations, violations[:10]


def truth_projection(result):
    canonical = result["json"]
    assessment = canonical.get("assessment") or {}
    return {
        "identity": {
            key: value
            for key, value in (canonical.get("identity") or {}).items()
            if key not in {"report_language", "locale"}
        },
        "scores": (
            assessment.get("technical_score"),
            assessment.get("canonical_evidence_adjusted_score"),
            (assessment.get("maturity_signal") or {}).get("score"),
        ),
        "controls": [
            (
                item.get("id"),
                item.get("score"),
                item.get("presented_score"),
                item.get("status"),
                len(item.get("evidence") or []),
                len(item.get("findings") or []),
            )
            for item in assessment.get("sections") or []
        ],
        "stages": [
            (item.get("stage_id"), item.get("status"))
            for item in canonical.get("stage_summaries") or []
        ],
        "findings": [
            (item.get("finding_id"), item.get("priority"), item.get("location"))
            for item in canonical.get("canonical_findings") or []
        ],
        "artifact_types": [
            item.get("artifact_type")
            for item in (result.get("artifact_manifest") or {}).get("artifacts") or []
        ],
        "review": (
            result.get("human_review_required"),
            result.get("client_delivery_allowed"),
            result.get("report_finality"),
        ),
    }


def assert_exact_manifest(result):
    fields = {
        "findings_csv": "findings_csv",
        "evidence_csv": "evidence_csv",
        "candidate_register_json": "candidate_register_json",
        "remediation_backlog_json": "remediation_backlog_json",
        "markdown_report": "markdown",
        "html_report": "html",
        "canonical_json": "canonical_json",
    }
    entries = (result.get("artifact_manifest") or {}).get("artifacts") or []
    assert len(entries) == 8
    for entry in entries:
        artifact_type = entry["artifact_type"]
        if artifact_type == "comprehensive_pdf":
            retained = base64.b64decode(result["pdf_base64"])
        else:
            retained = result[fields[artifact_type]].encode("utf-8")
        assert hashlib.sha256(retained).hexdigest() == entry["sha256"]
        assert len(retained) == entry["size_bytes"]


def assert_structural_parity(english, spanish):
    en_result, en_reader, en_pages = english
    es_result, es_reader, es_pages = spanish
    assert len(es_pages) == len(en_pages)
    assert markdown_signature(es_result["markdown"]) == markdown_signature(en_result["markdown"])
    assert html_signature(es_result["html"]) == html_signature(en_result["html"])
    assert truth_projection(es_result) == truth_projection(en_result)

    en_outline = outline_projection(en_reader)
    es_outline = outline_projection(es_reader)
    assert [page for _, page in es_outline] == [page for _, page in en_outline]
    assert [title for title, _ in es_outline] == [
        SPANISH_OUTLINE[title] for title, _ in en_outline
    ]
    assert_pdf_text_within_media_box(es_reader)

    en_toc = en_pages[1]
    es_toc = es_pages[1]
    spanish_phase_titles = {
        SPANISH_OUTLINE[title] for title in PHASE_OUTLINE_TITLES
    }
    for title, page in en_outline[1:]:
        if title not in PHASE_OUTLINE_TITLES:
            assert f"{title}\n{page}" in en_toc
    for title, page in es_outline[1:]:
        if title not in spanish_phase_titles:
            assert f"{title}\n{page}" in es_toc
    for title in PHASE_OUTLINE_TITLES:
        assert title.casefold() in en_toc.casefold()
        assert SPANISH_OUTLINE[title].casefold() in es_toc.casefold()

    for index, (en_page, es_page) in enumerate(
        zip(en_reader.pages, es_reader.pages),
        start=1,
    ):
        assert list(en_page.mediabox) == list(es_page.mediabox)
        assert (en_page.rotation or 0) == (es_page.rotation or 0)
        assert en_pages[index - 1].count(
            f"Document page {index} of {len(en_pages)}"
        ) == 1
        assert es_pages[index - 1].count(
            f"Página del documento {index} de {len(es_pages)}"
        ) == 1
        assert len(" ".join(es_pages[index - 1].split())) >= 120


small_english_before = render(small_package("en"))
small_spanish = render(small_package("es-MX"))
small_english_after = render(small_package("en"))

assert fingerprint(small_english_before[0]) == SMALL_ENGLISH_GOLDEN
assert fingerprint(small_english_after[0]) == SMALL_ENGLISH_GOLDEN
assert small_english_before[0]["markdown"] == small_english_after[0]["markdown"]
assert small_english_before[0]["html"] == small_english_after[0]["html"]
assert small_english_before[0]["pdf_base64"] == small_english_after[0]["pdf_base64"]
assert "spanish_uses_english_canonical_section_contract" not in small_english_before[0]["premium_report_renderer"]
assert small_spanish[0]["premium_report_renderer"]["spanish_uses_english_canonical_section_contract"] is True
assert_structural_parity(small_english_before, small_spanish)

rich_english = render(rich_input("en"))
rich_spanish = render(rich_input("es-MX"))
assert fingerprint(rich_english[0]) == RICH_ENGLISH_GOLDEN
assert_structural_parity(rich_english, rich_spanish)
assert len(rich_english[2]) == len(rich_spanish[2]) == 39
assert len(outline_projection(rich_english[1])) == len(outline_projection(rich_spanish[1])) == 33
assert len(re.findall(r"(?m)^#{1,3}\s", rich_english[0]["markdown"])) == 88
assert len(re.findall(r"(?m)^#{1,3}\s", rich_spanish[0]["markdown"])) == 88

phase9_english = render_phase9(phase9_input("en"))
phase9_spanish = render_phase9(phase9_input("es-MX"))
assert fingerprint(phase9_english[0]) == PHASE9_ENGLISH_GOLDEN
assert_structural_parity(phase9_english, phase9_spanish)
for finding_id in (
    "NICO-FINDING-E5CA1CA5C494",
    "NICO-FINDING-94D84D011F4D",
    "ARCH-1",
):
    assert finding_id in phase9_english[0]["markdown"]
    assert finding_id in phase9_spanish[0]["markdown"]
assert "componentes hij..." not in phase9_spanish[0]["markdown"]
assert len(phase9_english[2]) == len(phase9_spanish[2]) == 20
assert len(outline_projection(phase9_english[1])) == len(outline_projection(phase9_spanish[1])) == 19
assert len(re.findall(r"(?m)^#{1,3}\s", phase9_english[0]["markdown"])) == 79
assert len(re.findall(r"(?m)^#{1,3}\s", phase9_spanish[0]["markdown"])) == 79

for result in (small_spanish[0], rich_spanish[0], phase9_spanish[0]):
    assert_exact_manifest(result)
    assert "lang='es-MX'" in result["html"] or 'lang="es-MX"' in result["html"]
    visible_markdown = re.sub(r"<!--.*?-->", "", result["markdown"], flags=re.S)
    visible_html = html.unescape(
        re.sub(r"<!--.*?-->", "", result["html"], flags=re.S)
    )
    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(
            io.BytesIO(base64.b64decode(result["pdf_base64"]))
        ).pages
    )
    for forbidden in (
        "Executive Decision Brief",
        "Priority Constraints and Decision Risks",
        "Canonical Technical Scorecard",
        "Architecture & Technical Debt",
        "Evidence Foundation",
        "Roadmap, Resourcing, and Decision",
        "NICO generated an automated",
        "Decision-oriented summary",
        "Exact immutable evidence item",
        "Review-limited finding",
        "One bounded evidence limitation",
        "Retained finding for",
        "Human context limitation for",
        "Substantive summary for",
        "Stakeholder interviews were not supplied",
        "No retained structured stage summary",
        "Human context or additional evidence",
        "The canonical finding was retained",
        "Evidence Evaluated",
        "Evidence Bound",
        "Evidence-Adjusted",
        "Unavailable or limited evidence",
        "AUTOMATED DRAFT",
        "Not scored",
        "Not supplied",
        "Requires human technical disposition",
        "Operations route complexity is reduced",
        "scanner execution(s) remain incomplete",
        "Exact-commit executable source signals were analyzed",
        "Historical workflow, job, and deployment outcomes are retained",
        "The delivery-capacity score is",
        "Commit, pull-request, merge, job, and deployment counts are retained",
        "STRONG",
        "## Registro detallado de hallazgos",
    ):
        assert forbidden not in visible_markdown
        assert forbidden not in visible_html
        assert forbidden not in pdf_text
    assert visible_markdown.count("Analizadores aplicables incompletos:") == 1
    assert visible_html.count("Analizadores aplicables incompletos:") == 1
    assert pdf_text.count("Analizadores aplicables incompletos:") == 1
    assert "Ã" not in pdf_text
    assert "\x00" not in pdf_text

small_result, _, small_pages = small_spanish
small_pdf_text = "\n".join(small_pages)
for token in (
    "BoneManTGRM/NICO",
    "7777777777777777777777777777777777777777",
    "comprun_premium",
    "ledger-premium",
    "apps/web/app/page.tsx:100",
    "RISK-P1-001",
    "bandit",
    "completed_with_findings",
    "WP-001",
):
    assert token in small_result["markdown"]
    assert token in small_result["html"]
    assert token in small_pdf_text

for heading in (
    "Resumen ejecutivo para decisiones",
    "Cuadro de puntuación técnica",
    "Fundamento de evidencia",
    "Hoja de ruta, recursos y decisión",
    "Registro compacto de hallazgos y remediación",
    "Puerta de revisión humana y aceptación",
):
    assert heading in small_result["markdown"]
    assert heading in small_result["html"]
    assert heading in small_pdf_text

assert "ENTREGA AL CLIENTE BLOQUEADA — ENTREGA AL CLIENTE NO AUTORIZADA" in small_result["markdown"]
assert "&lt;!-- CLIENT DELIVERY NOT AUTHORIZED --&gt;" not in small_result["html"]
assert small_result["markdown"].count("## Registro compacto de hallazgos y remediación") == 1
assert small_result["markdown"].count("## Índice completo de fuentes exactas") == 1
assert small_result["markdown"].count("## Puerta de revisión humana y aceptación") == 1
'''

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        capture_output=True,
        text=True,
        # This single parity probe fully composes and inspects six PDFs. Allow
        # headroom on shared/CI workers without reducing any artifact assertion.
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, (
        "same-package English/Spanish report parity failed\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
