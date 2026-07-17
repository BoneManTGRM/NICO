from __future__ import annotations

from nico.full_report_authorized_release_v1 import build_authorized_full_release


def _pages() -> list[str]:
    labels = [
        "Board and Executive Decision Package",
        "Enterprise Architecture and System Boundaries",
        "Trust Boundaries and Threat Model",
        "Service, Dependency, and Data-Flow Topology",
        "Deployment and Environment Topology",
        "Resilience, Disaster Recovery, and Continuity",
        "Observability and Incident Operations",
        "Security Governance and SDLC Controls",
        "Technical-Debt Economics",
        "Multi-Quarter Transformation Roadmap",
        "Enterprise Finding Dossiers",
        "Human review required",
    ]
    detail = " Evidence-bound analysis with owner, verification, rollback, acceptance criteria, and residual risk."
    pages = [label + detail * 3 for label in labels]
    pages.extend([f"Substantive enterprise analysis {index}." + detail * 3 for index in range(12, 70)])
    return pages


def _exports() -> dict:
    return {
        "pdf": b"%PDF-1.7 full report",
        "html": "<html><body>full report</body></html>",
        "markdown": "# Full report",
    }


def _build(**overrides):
    values = {
        "report": {"report_version": "full-10.0", "full_score_transparency": {"records": []}, "full_enterprise_findings": {"records": []}},
        "pages": _pages(),
        "exports": _exports(),
        "assessment_id": "assessment-10i",
        "locale": "en",
        "report_format": "pdf",
        "actor_id": "reviewer-1",
        "actor_role": "client_reviewer",
        "workspace_id": "workspace-1",
        "assessment_workspace_id": "workspace-1",
        "request_id": "request-10i",
        "human_review_complete": True,
    }
    values.update(overrides)
    return build_authorized_full_release(**values)


def test_release_is_allowed_only_after_pipeline_and_authorization_pass() -> None:
    result = _build()
    release = result["full_authorized_release"]
    assert release["pipeline_allowed"] is True
    assert release["authorization"]["status"] == "authorized"
    assert release["audit_event"]["decision"] == "allow"
    assert result["client_delivery_allowed"] is True


def test_cross_workspace_request_is_denied_and_audited() -> None:
    result = _build(assessment_workspace_id="workspace-2")
    release = result["full_authorized_release"]
    assert "workspace_identity_mismatch" in release["authorization"]["issues"]
    assert release["audit_event"]["decision"] == "deny"
    assert result["client_delivery_allowed"] is False


def test_human_review_block_cannot_be_overridden_by_authorization() -> None:
    result = _build(human_review_complete=False)
    assert result["full_authorized_release"]["pipeline_allowed"] is False
    assert result["client_delivery_allowed"] is False


def test_unsupported_format_is_denied() -> None:
    result = _build(report_format="docx")
    authorization = result["full_authorized_release"]["authorization"]
    assert "download_response_not_approved" in authorization["issues"]
    assert result["client_delivery_allowed"] is False
