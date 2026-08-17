from __future__ import annotations

import base64
import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import comprehensive_native_providers as providers
from nico.comprehensive_automated_draft_cross_format_v1 import (
    install_automated_draft_cross_format_contract,
)
from nico.comprehensive_cross_format_finality_v49 import (
    VERSION,
    _delivery_boundary_present,
    install_comprehensive_cross_format_finality_v49,
    synchronize_comprehensive_score_truth,
)


RUN_ID = "comprun_cross_format_v51"
REPOSITORY = "BoneManTGRM/NICO"
COMMIT_SHA = "a" * 40
TECHNICAL_SCORE = 85
EVIDENCE_ADJUSTED_SCORE = 74


def _install() -> tuple[dict, dict]:
    legacy = install_comprehensive_cross_format_finality_v49()
    automated_draft = install_automated_draft_cross_format_contract()
    return legacy, automated_draft


def _pdf(
    *,
    technical_score: int = TECHNICAL_SCORE,
    adjusted_score: int = EVIDENCE_ADJUSTED_SCORE,
) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.drawString(42, 720, "NICO Comprehensive Technical Assessment")
    page.drawString(
        42,
        700,
        "AUTOMATED DRAFT - PENDING HUMAN APPROVAL - CLIENT DELIVERY BLOCKED",
    )
    page.drawString(42, 680, f"Technical maturity {technical_score}/100")
    page.drawString(42, 660, f"Evidence-Adjusted {adjusted_score}/100")
    page.drawString(42, 640, f"Run ID: {RUN_ID}")
    page.drawString(42, 620, f"Repository: {REPOSITORY}")
    page.drawString(42, 600, f"Commit: {COMMIT_SHA}")
    page.save()
    return buffer.getvalue()


def _assessment(
    *,
    canonical_adjusted: int = EVIDENCE_ADJUSTED_SCORE,
    legacy_adjusted: int = EVIDENCE_ADJUSTED_SCORE,
) -> dict:
    return {
        "technical_score": TECHNICAL_SCORE,
        "canonical_evidence_adjusted_score": canonical_adjusted,
        "evidence_adjusted_score": legacy_adjusted,
        "maturity_signal": {
            "score": TECHNICAL_SCORE,
            "source_score": TECHNICAL_SCORE,
            "presented_score": TECHNICAL_SCORE,
            "technical_score": TECHNICAL_SCORE,
            "canonical_evidence_adjusted_score": canonical_adjusted,
            "evidence_adjusted_score": legacy_adjusted,
        },
    }


def _package(
    *,
    delivery_status: str = "blocked_pending_human_approval",
    markdown_adjusted: int = EVIDENCE_ADJUSTED_SCORE,
    html_adjusted: int = EVIDENCE_ADJUSTED_SCORE,
    pdf_adjusted: int = EVIDENCE_ADJUSTED_SCORE,
    canonical_adjusted: int = EVIDENCE_ADJUSTED_SCORE,
    legacy_adjusted: int = EVIDENCE_ADJUSTED_SCORE,
) -> dict:
    markdown = (
        "# NICO Comprehensive Technical Assessment\n\n"
        "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n\n"
        f"Technical maturity is Strong ({TECHNICAL_SCORE}/100).\n"
        f"Evidence-Adjusted readiness is {markdown_adjusted}/100.\n"
        f"Run ID: {RUN_ID}\n"
        f"Repository: {REPOSITORY}\n"
        f"Immutable commit SHA: {COMMIT_SHA}\n"
    )
    html = (
        "<html><body>"
        "<h1>NICO Comprehensive Technical Assessment</h1>"
        f"<p>Technical maturity {TECHNICAL_SCORE}/100</p>"
        f"<p>Evidence-Adjusted {html_adjusted}/100</p>"
        f"<pre>{markdown}</pre>"
        "</body></html>"
    )
    canonical = {
        "service_id": "comprehensive",
        "report_finality": "automated_draft",
        "approval_status": "pending_human_approval",
        "delivery_status": delivery_status,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "assessment": _assessment(
            canonical_adjusted=canonical_adjusted,
            legacy_adjusted=legacy_adjusted,
        ),
    }
    return {
        "service_id": "comprehensive",
        "report_finality": "automated_draft",
        "approval_status": "pending_human_approval",
        "delivery_status": delivery_status,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "markdown": markdown,
        "html": html,
        "json": canonical,
        "pdf_base64": base64.b64encode(
            _pdf(adjusted_score=pdf_adjusted)
        ).decode("ascii"),
        "canonical_truth_sha256": "b" * 64,
    }


def _context(*, package: dict | None = None, nested: bool = False) -> dict:
    report_package = package or _package()
    final_result = {
        "status": "complete",
        "report_package": report_package,
    }
    final_stage = {"result": final_result} if nested else final_result
    return {
        "run_id": RUN_ID,
        "repository": REPOSITORY,
        "commit_sha": COMMIT_SHA,
        "evidence_ledger_id": "ledger_cross_format_v51",
        "customer_id": "customer_cross_format_v51",
        "project_id": "project_cross_format_v51",
        "prior_stage_results": {
            "final_comprehensive_report_generation": final_stage,
        },
    }


def test_current_automated_draft_boundary_and_score_truth_pass() -> None:
    install, automated = _install()
    result = providers.cross_format_verification_provider(_context())

    assert install["bound"] is True
    assert install["canonical_score_parity_required"] is True
    assert automated["provider_bound"] is True
    assert automated["required_finality"] == "automated_draft"
    assert result["status"] == "complete"
    assert result["cross_format_contract_schema"] == VERSION
    assert result["failed_checks"] == []
    assert result["checks"]["report_finality_is_automated_draft"] is True
    assert result["checks"]["final_delivery_boundary_present_in_markdown"] is True
    assert result["checks"]["evidence_adjusted_aliases_consistent"] is True
    assert result["checks"]["markdown_evidence_adjusted_matches_canonical"] is True
    assert result["checks"]["html_evidence_adjusted_matches_canonical"] is True
    assert result["checks"]["pdf_evidence_adjusted_matches_canonical"] is True
    assert result["score_truth"]["technical_score"] == TECHNICAL_SCORE
    assert (
        result["score_truth"]["evidence_adjusted_score"]
        == EVIDENCE_ADJUSTED_SCORE
    )
    assert result["report_package_source"] == "stage.report_package"
    assert "CLIENT DELIVERY NOT AUTHORIZED" not in _package()["markdown"]
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_spanish_delivery_boundary_is_equivalent_to_english_boundary() -> None:
    assert _delivery_boundary_present(
        "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · "
        "ENTREGA AL CLIENTE BLOQUEADA"
    ) is True


def test_execution_wrapper_envelope_does_not_hide_the_generated_report_package() -> None:
    _install()
    result = providers.cross_format_verification_provider(_context(nested=True))

    assert result["status"] == "complete"
    assert result["failed_checks"] == []
    assert result["report_package_source"] == "stage.result.report_package"
    assert result["checks"]["pdf_available"] is True


def test_finality_metadata_can_be_read_from_canonical_truth() -> None:
    package = _package()
    canonical = package["json"]
    for key in (
        "service_id",
        "report_finality",
        "approval_status",
        "delivery_status",
        "human_review_required",
        "client_delivery_allowed",
    ):
        package.pop(key)
    _install()
    result = providers.cross_format_verification_provider(
        _context(package=package, nested=True)
    )

    assert canonical["delivery_status"] == "blocked_pending_human_approval"
    assert result["status"] == "complete"
    assert result["failed_checks"] == []
    assert result["checks"]["report_finality_is_automated_draft"] is True
    assert result["checks"]["delivery_status_is_blocked"] is True


def test_structured_delivery_drift_fails_closed_and_exposes_exact_check() -> None:
    _install()
    result = providers.cross_format_verification_provider(
        _context(package=_package(delivery_status="delivery_allowed"))
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "cross_format_final_report_verification_failed"
    assert "delivery_status_is_blocked" in result["failed_checks"]
    assert result["checks"]["delivery_status_is_blocked"] is False
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_canonical_score_synchronizer_replaces_legacy_adjusted_score() -> None:
    assessment = _assessment(canonical_adjusted=74, legacy_adjusted=72)
    assessment["executive_summary"] = (
        "Weighted technical maturity is 85/100; independently evidence-adjusted "
        "readiness is 72/100."
    )

    synchronized = synchronize_comprehensive_score_truth(assessment)
    maturity = synchronized["maturity_signal"]

    assert synchronized["technical_score"] == 85
    assert synchronized["canonical_evidence_adjusted_score"] == 74
    assert synchronized["evidence_adjusted_score"] == 74
    assert maturity["score"] == 85
    assert maturity["presented_score"] == 85
    assert maturity["canonical_evidence_adjusted_score"] == 74
    assert maturity["evidence_adjusted_score"] == 74
    assert (
        "evidence-adjusted readiness is 74/100"
        in synchronized["executive_summary"]
    )
    assert "72/100" not in synchronized["executive_summary"]


def test_canonical_json_alias_mismatch_fails_closed() -> None:
    _install()
    result = providers.cross_format_verification_provider(
        _context(package=_package(canonical_adjusted=74, legacy_adjusted=72))
    )

    assert result["status"] == "blocked"
    assert "evidence_adjusted_aliases_consistent" in result["failed_checks"]
    assert result["score_truth"]["adjusted_aliases_consistent"] is False
    assert (
        result["score_truth"]["adjusted_aliases"][
            "assessment.evidence_adjusted_score"
        ]
        == 72
    )


def test_pdf_score_drift_fails_closed_with_exact_diagnostic() -> None:
    _install()
    result = providers.cross_format_verification_provider(
        _context(package=_package(pdf_adjusted=72))
    )

    assert result["status"] == "blocked"
    assert "pdf_evidence_adjusted_matches_canonical" in result["failed_checks"]
    assert result["checks"]["pdf_evidence_adjusted_matches_canonical"] is False
    assert result["score_truth"]["evidence_adjusted_score"] == 74


def test_markdown_and_html_score_drift_fail_closed() -> None:
    _install()
    result = providers.cross_format_verification_provider(
        _context(package=_package(markdown_adjusted=72, html_adjusted=72))
    )

    assert result["status"] == "blocked"
    assert "markdown_evidence_adjusted_matches_canonical" in result["failed_checks"]
    assert "html_evidence_adjusted_matches_canonical" in result["failed_checks"]


def test_installation_is_idempotent_and_replaces_obsolete_verifier() -> None:
    first, automated_first = _install()
    second, automated_second = _install()

    assert first["bound"] is True
    assert second["bound"] is True
    assert second["status"] == "already_installed"
    assert second["legacy_draft_phrase_required"] is False
    assert second["canonical_score_parity_required"] is True
    assert automated_first["provider_bound"] is True
    assert automated_second["provider_bound"] is True
    assert automated_second["required_finality"] == "automated_draft"
