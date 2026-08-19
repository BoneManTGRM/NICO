from __future__ import annotations

import io

from pypdf import PdfReader

from nico import comprehensive_ci_pdf_control_safety_v89 as v89
from nico import comprehensive_native_providers as providers
from nico import comprehensive_rendered_ci_boundary_producer_v79 as producer
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_exit_criteria_v88 as v88
from nico import comprehensive_spanish_presentation_parity_v1 as presentation


_ROLLBACK_EN = (
    "Revert the isolated remediation change if targeted or full verification fails; "
    "retain the failed evidence and keep client delivery blocked."
)
_ROLLBACK_ES = (
    "Revierta el cambio aislado de remediación si falla la verificación dirigida o "
    "completa; conserve la evidencia del fallo y mantenga bloqueada la entrega al cliente."
)
_SCORE_SUMMARY_EN_SOFT_WRAPPED = (
    "Technical maturity remains based on exact-commit technical controls.\n"
    "Evidence-Adjusted readiness is 93/100 versus technical maturity 93/100. "
    "NICO retains 639 review-required candidates and 0 confirmed material\n"
    "findings as explicit review context. Candidate volume, clustering and reviewer "
    "workload do not change numeric security or readiness scores."
)
_SCORE_SUMMARY_ES = (
    "La madurez técnica sigue basándose en controles técnicos del commit exacto. "
    "La preparación ajustada por evidencia es 93/100 frente a una madurez técnica de "
    "93/100. NICO conserva 639 candidatos que requieren revisión y 0 hallazgos "
    "materiales confirmados como contexto explícito de revisión. El volumen de "
    "candidatos, la agrupación y la carga de trabajo de revisión no modifican las "
    "puntuaciones numéricas de seguridad ni de preparación."
)


def _canonical(language: str) -> dict[str, object]:
    return {
        "report_language": language,
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "52c3d21db537ca9a5937dffd71b844901d8f5241",
            "run_id": "comprun_detached_rebind_fixture",
            "generated_at": "2026-08-19T00:00:00Z",
            "evidence_ledger_id": "ledger_detached_rebind_fixture",
            "report_language": language,
        },
        "assessment": {
            "report_language": language,
            "service_id": "comprehensive",
            "sections": [],
        },
        "ci_operational_context": {
            "successful_workflow_runs": 80,
            "failed_workflow_runs": 10,
            "unknown_workflow_runs": 10,
            "workflow_runs_observed": 100,
            "jobs_observed": 37,
            "deployments_observed": 10,
            "successful_deployments": 5,
            "non_successful_deployments": 4,
        },
    }


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def test_v88_reassertion_never_recaptures_late_delegating_wrappers(monkeypatch) -> None:
    installation = v88.install_comprehensive_spanish_exit_criteria_v88()
    assert installation["base_delegates_immutable"] is True
    assert installation["late_wrapper_rebind_cycle_blocked"] is True

    base_direct = v88._ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION
    base_field = v88._ORIGINAL_CANONICAL_TRANSLATE_FIELD
    base_safe = v88._ORIGINAL_PRESENTATION_SAFE_ES
    base_report = v88._ORIGINAL_NATIVE_BUILD_REPORT
    assert base_direct is not None
    assert base_field is not None
    assert base_safe is not None
    assert base_report is not None

    # Model compatibility wrappers that resolve the public aliases dynamically. If a
    # reinstaller captures any of these as its new "original" delegate and then restores
    # v88 on that same alias, the next detached report render recursively calls itself.
    def late_direct(value: object) -> str:
        return canonical._translate_presentation(value)

    def late_field(value: str, key: str) -> str:
        return canonical._translate_presentation_field(value, key)

    def late_safe(value: object) -> str:
        return presentation._safe_es(value)

    def late_report(context: dict[str, object], final: bool) -> dict[str, object]:
        return providers._build_report(context, final)

    monkeypatch.setattr(canonical, "_translate_presentation", late_direct)
    monkeypatch.setattr(canonical, "_translate_presentation_field", late_field)
    monkeypatch.setattr(presentation, "_safe_es", late_safe)
    monkeypatch.setattr(providers, "_build_report", late_report)

    rebound = v88.install_comprehensive_spanish_exit_criteria_v88()

    assert rebound["bound"] is True
    assert rebound["report_runtime_boundary_bound"] is True
    assert v88._ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION is base_direct
    assert v88._ORIGINAL_CANONICAL_TRANSLATE_FIELD is base_field
    assert v88._ORIGINAL_PRESENTATION_SAFE_ES is base_safe
    assert v88._ORIGINAL_NATIVE_BUILD_REPORT is base_report
    assert canonical._translate_presentation is v88._translate_presentation_v88
    assert canonical._translate_presentation_field is v88._translate_canonical_field_v88
    assert presentation._safe_es is v88._presentation_safe_es_v88
    assert providers._build_report is v88._native_build_report_v88

    # Execute the repaired public surfaces. These calls recurse indefinitely under the
    # old recapture behavior, which is the production failure this regression covers.
    assert canonical._translate_presentation(_SCORE_SUMMARY_EN_SOFT_WRAPPED) == _SCORE_SUMMARY_ES
    assert canonical._translate_presentation_field(_ROLLBACK_EN, "rollback") == _ROLLBACK_ES
    assert presentation._safe_es(_ROLLBACK_EN) == _ROLLBACK_ES


def test_v89_reassertion_never_recaptures_late_boundary_wrapper(monkeypatch) -> None:
    installation = v89.install_comprehensive_ci_pdf_control_safety_v89()
    assert installation["base_delegate_immutable"] is True
    assert installation["late_wrapper_rebind_cycle_blocked"] is True

    base_boundary = v89._ORIGINAL_BOUNDARY_PDF_PAGE
    assert base_boundary is not None

    def late_boundary(*args: object, **kwargs: object) -> bytes:
        return producer._boundary_pdf_page(*args, **kwargs)

    monkeypatch.setattr(producer, "_boundary_pdf_page", late_boundary)

    rebound = v89.install_comprehensive_ci_pdf_control_safety_v89()

    assert rebound["bound"] is True
    assert v89._ORIGINAL_BOUNDARY_PDF_PAGE is base_boundary
    assert producer._boundary_pdf_page is v89._boundary_pdf_page_v89

    repaired = producer._boundary_pdf_page(_canonical("es-MX"), spanish=True)
    assert repaired.startswith(b"%PDF")
    assert "\x7f" not in _pdf_text(repaired)
