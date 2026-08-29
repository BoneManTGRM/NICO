from __future__ import annotations

import base64
import io
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from pypdf import PdfReader

from nico import comprehensive_same_run_locale_report_v1 as subject


def _canonical(report_language: str = "en") -> dict:
    return {
        "service_id": "comprehensive",
        "report_id": "comprehensive_report_same_run_1",
        "report_language": report_language,
        "locale": report_language,
        "identity": {
            "run_id": "comprun_same_run_1",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_same_run_1",
            "report_language": report_language,
            "locale": report_language,
            "customer_id": "customer_same_run_1",
            "project_id": "project_same_run_1",
            "assessment_depth": "strategic",
            "generated_at": "2026-08-24T20:00:00Z",
        },
        "assessment": {
            "report_language": report_language,
            "locale": report_language,
            "maturity_signal": {"score": 93, "presented_score": 93},
            "sections": [],
            "human_review_required": True,
            "client_ready": False,
            "client_delivery_allowed": False,
        },
        "stage_summaries": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _status(*, source_language: str = "en") -> dict:
    canonical = _canonical(source_language)
    pdf = b"%PDF-1.4\nsource"
    return {
        "run_id": canonical["identity"]["run_id"],
        "repository": canonical["identity"]["repository"],
        "commit_sha": canonical["identity"]["commit_sha"],
        "evidence_ledger_id": canonical["identity"]["evidence_ledger_id"],
        "report_language": source_language,
        "terminal": True,
        "integrity_sha256": "run-integrity",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "reports": {
            "report_id": "comprehensive_report_same_run_1",
            "canonical_truth_sha256": subject._canonical_hash(canonical),
            "json": canonical,
            "markdown": "# source report",
            "html": "<article>source report</article>",
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_sha256": subject.hashlib.sha256(pdf).hexdigest(),
        },
    }


def _approved_status(
    *,
    source_language: str = "en",
    client_delivery_allowed: bool = False,
    canonical_updates: dict | None = None,
    include_evidence_manifest: bool = False,
) -> dict:
    from nico.decision_grade_accepted_edition_v2 import build_accepted_report_edition

    status = _status(source_language=source_language)
    canonical = status["reports"]["json"]
    if canonical_updates:
        canonical.update(deepcopy(canonical_updates))
        status["reports"]["canonical_truth_sha256"] = subject._canonical_hash(
            canonical
        )
    identity = canonical["identity"]
    pdf_bytes = base64.b64decode(status["reports"]["pdf_base64"], validate=True)
    artifacts = {
        "markdown": status["reports"]["markdown"],
        "html": status["reports"]["html"],
        "pdf": pdf_bytes,
        "json": canonical,
    }
    if include_evidence_manifest:
        status["reports"]["evidence_manifest_json"] = (
            '{"manifest_id":"exact-source-manifest"}'
        )
        artifacts["evidence_manifest"] = status["reports"][
            "evidence_manifest_json"
        ]
    accepted = build_accepted_report_edition(
        repository=identity["repository"],
        commit_sha=identity["commit_sha"],
        tree_sha="tree-same-run-1",
        run_id=identity["run_id"],
        scanner_run_id="scanner-same-run-1",
        evidence_bundle_hash="evidence-same-run-1",
        report_language=source_language,
        assessment_depth=identity["assessment_depth"],
        artifacts=artifacts,
        reviewer="Authorized Reviewer",
        reviewer_role="Security reviewer",
        decision="approved",
        decision_reason="Exact source edition reviewed.",
        decided_at="2026-08-28T12:00:00+00:00",
    )
    status.update(
        {
            "status": "approved",
            "human_review_completed": True,
            "client_delivery_allowed": client_delivery_allowed,
            "delivery_status": (
                "approved_for_delivery"
                if client_delivery_allowed
                else "pending_authorization"
            ),
            "accepted_edition": accepted,
        }
    )
    if client_delivery_allowed:
        status["response_projection"] = {
            "delivery_authorization_integrity_valid": True,
        }
    return status


def test_alternate_locale_uses_same_canonical_run_without_mutating_source(monkeypatch):
    status = _status(source_language="en")
    before = deepcopy(status)

    monkeypatch.setattr(
        subject,
        "_render_target",
        lambda canonical, report_language: {
            "markdown": "# informe",
            "html": "<article>informe</article>",
            "pdf_base64": base64.b64encode(b"%PDF-1.4\nes-MX").decode("ascii"),
            "pdf_sha256": "localized-pdf-sha",
            "pdf_page_count": 44,
        },
    )

    result = subject.build_same_run_locale_report(status, "es-MX")

    assert status == before
    assert result["run_id"] == status["run_id"]
    assert result["source_report_id"] == status["reports"]["report_id"]
    assert result["source_report_language"] == "en"
    assert result["report_language"] == "es-MX"
    assert result["same_canonical_run"] is True
    assert result["assessment_rerun"] is False
    assert result["canonical_truth_preserved"] is True
    assert (
        result["canonical_truth_sha256"]
        == status["reports"]["canonical_truth_sha256"]
    )
    assert result["report"]["json"] == status["reports"]["json"]
    assert result["report"]["presentation_language"] == "es-MX"
    assert result["report"]["pdf_page_count"] == 44
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert result["approval_state_mutated"] is False
    assert result["delivery_state_mutated"] is False


def test_source_locale_reuses_terminal_artifacts_without_rerender(monkeypatch):
    status = _status(source_language="en")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("source locale should reuse the frozen terminal artifacts")

    monkeypatch.setattr(subject, "_render_target", fail_if_called)
    result = subject.build_same_run_locale_report(status, "en")

    assert result["report"]["markdown"] == status["reports"]["markdown"]
    assert result["report"]["html"] == status["reports"]["html"]
    assert result["report"]["pdf_base64"] == status["reports"]["pdf_base64"]
    assert result["assessment_rerun"] is False


def test_presentation_approval_fields_cannot_promote_authoritative_pending_run() -> None:
    status = _status(source_language="en")
    status["status"] = "review_required"
    status["human_review_completed"] = False
    status["client_delivery_allowed"] = False
    status["reports"].update(
        {
            "approval_status": "approved_final",
            "human_review_status": "approved",
            "client_delivery_allowed": True,
        }
    )
    status["reports"]["json"].update(
        {
            "approval_status": "approved_final",
            "human_review_status": "approved",
            "client_delivery_allowed": True,
        }
    )
    status["reports"]["canonical_truth_sha256"] = subject._canonical_hash(
        status["reports"]["json"]
    )

    result = subject.build_same_run_locale_report(status, "en")

    assert result["approval_status"] == "pending_human_approval"
    assert result["human_review_completed"] is False
    assert result["client_delivery_allowed"] is False
    assert result["delivery_status"] == "blocked_pending_human_approval"
    assert result["report"]["approval_status"] == "pending_human_approval"


def test_unattested_delivery_flag_cannot_authorize_localized_artifacts() -> None:
    status = _approved_status(client_delivery_allowed=True)
    status.pop("response_projection")

    result = subject.build_same_run_locale_report(status, "en")

    assert result["approval_status"] == "approved_final"
    assert result["human_review_completed"] is True
    assert result["client_delivery_allowed"] is False
    assert result["delivery_status"] == "blocked_authorization_integrity"
    assert result["canonical_run_lifecycle"][
        "delivery_authorization_integrity_valid"
    ] is False


def test_frozen_source_pdf_response_exposes_exact_artifact_digest() -> None:
    status = _status(source_language="en")
    pdf_bytes = base64.b64decode(status["reports"]["pdf_base64"])

    response = subject.build_same_run_locale_pdf_response(status, "en")

    expected = subject.hashlib.sha256(pdf_bytes).hexdigest()
    assert response.headers["x-nico-pdf-sha256"] == expected
    assert response.headers["x-nico-artifact-sha256"] == expected


@pytest.mark.parametrize(
    ("delivery_allowed", "expected_delivery_status"),
    ((False, "pending_authorization"), (True, "authorized")),
)
def test_accepted_source_pdf_is_bound_to_valid_manifest_language_and_digest(
    delivery_allowed,
    expected_delivery_status,
) -> None:
    status = _approved_status(client_delivery_allowed=delivery_allowed)
    before = deepcopy(status)
    expected = status["accepted_edition"]["artifact_digests"]["pdf"]["sha256"]

    response = subject.build_same_run_locale_pdf_response(status, "en")

    assert status == before
    assert response.body == base64.b64decode(status["reports"]["pdf_base64"])
    assert response.headers["x-nico-commit-sha"] == status["commit_sha"]
    assert response.headers["x-nico-assessment-rerun"] == "false"
    assert response.headers["x-nico-accepted-pdf-sha256"] == expected
    assert response.headers["x-nico-accepted-edition-language"] == "en"
    assert response.headers["x-nico-accepted-edition-manifest-sha256"] == (
        status["accepted_edition"]["accepted_edition_manifest_sha256"]
    )
    assert "APPROVED-ACCEPTED-EDITION.pdf" in response.headers[
        "content-disposition"
    ]
    assert response.headers["x-nico-approval-status"] == "approved_final"
    assert response.headers["x-nico-delivery-status"] == expected_delivery_status
    assert response.headers["x-nico-client-delivery-allowed"] == str(
        delivery_allowed
    ).lower()
    assert (
        response.headers["x-nico-localized-artifact-requires-new-approval"]
        == "false"
    )


def test_accepted_source_pdf_fails_closed_on_manifest_or_pdf_binding_drift() -> None:
    invalid_manifest = _approved_status()
    invalid_manifest["accepted_edition"]["review"]["reason"] = "tampered"
    with pytest.raises(ValueError, match="accepted_edition_manifest_hash_mismatch"):
        subject.build_same_run_locale_pdf_response(invalid_manifest, "en")

    stale_pdf = _approved_status()
    changed_pdf = b"%PDF-1.4\nchanged-after-approval"
    stale_pdf["reports"]["pdf_base64"] = base64.b64encode(changed_pdf).decode(
        "ascii"
    )
    stale_pdf["reports"]["pdf_sha256"] = subject.hashlib.sha256(
        changed_pdf
    ).hexdigest()
    with pytest.raises(ValueError, match="accepted_edition_pdf_digest_mismatch"):
        subject.build_same_run_locale_pdf_response(stale_pdf, "en")


def test_accepted_source_pdf_fails_closed_on_accepted_language_drift() -> None:
    status = _approved_status()
    accepted = status["accepted_edition"]
    accepted["report_language"] = "es-MX"
    accepted.pop("accepted_edition_manifest_sha256")
    from nico.comprehensive_review_decision_v1 import _canonical_hash

    accepted["accepted_edition_manifest_sha256"] = _canonical_hash(accepted)

    with pytest.raises(ValueError, match="accepted_edition_language_mismatch"):
        subject.build_same_run_locale_pdf_response(status, "en")


def test_frozen_source_pdf_fails_closed_on_canonical_truth_mismatch() -> None:
    status = _status(source_language="en")
    status["reports"]["canonical_truth_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="canonical_truth_hash_mismatch"):
        subject.build_same_run_locale_pdf_response(status, "en")


def test_localized_pdf_response_keeps_same_run_and_truth(monkeypatch):
    status = _status(source_language="en")
    before = deepcopy(status)
    pdf_bytes = b"%PDF-1.4\nlocalized"

    monkeypatch.setattr(
        subject,
        "_render_target",
        lambda canonical, report_language: {
            "markdown": "# informe",
            "html": "<article>informe</article>",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "pdf_sha256": subject.hashlib.sha256(pdf_bytes).hexdigest(),
            "pdf_page_count": 44,
        },
    )

    response = subject.build_same_run_locale_pdf_response(status, "es-MX")

    assert response.body == pdf_bytes
    assert response.media_type == "application/pdf"
    assert response.headers["x-nico-run-id"] == status["run_id"]
    assert response.headers["x-nico-commit-sha"] == status["commit_sha"]
    assert response.headers["x-nico-report-language"] == "es-MX"
    assert (
        response.headers["x-nico-canonical-truth-sha256"]
        == status["reports"]["canonical_truth_sha256"]
    )
    assert response.headers["x-nico-assessment-rerun"] == "false"
    assert response.headers["x-nico-pdf-sha256"] == subject.hashlib.sha256(
        pdf_bytes
    ).hexdigest()
    assert response.headers["x-nico-artifact-sha256"] == subject.hashlib.sha256(
        pdf_bytes
    ).hexdigest()
    assert response.headers["x-nico-approval-status"] == "pending_human_approval"
    assert response.headers["x-nico-delivery-status"] == (
        "blocked_pending_human_approval"
    )
    assert response.headers["x-nico-client-delivery-allowed"] == "false"
    assert (
        response.headers["x-nico-localized-artifact-requires-new-approval"]
        == "true"
    )
    assert (
        response.headers["x-nico-localized-artifact-approval-invalidated"]
        == "true"
    )
    assert response.headers["x-nico-artifact-finality"] == "automated_draft"
    assert "x-nico-accepted-pdf-sha256" not in response.headers
    assert "x-nico-accepted-edition-language" not in response.headers
    assert status == before
    assert "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf" in response.headers[
        "content-disposition"
    ]


def test_localized_pdf_hash_mismatch_fails_closed(monkeypatch):
    status = _status(source_language="en")
    pdf_bytes = b"%PDF-1.4\nlocalized"

    monkeypatch.setattr(
        subject,
        "_render_target",
        lambda canonical, report_language: {
            "markdown": "# informe",
            "html": "<article>informe</article>",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "pdf_sha256": "0" * 64,
            "pdf_page_count": 44,
        },
    )

    with pytest.raises(ValueError, match="localized_report_pdf_hash_mismatch"):
        subject.build_same_run_locale_pdf_response(status, "es-MX")


def test_canonical_truth_mismatch_fails_closed(monkeypatch):
    status = _status()
    status["reports"]["canonical_truth_sha256"] = "0" * 64
    monkeypatch.setattr(subject, "_render_target", lambda *args, **kwargs: {})

    with pytest.raises(ValueError, match="canonical_truth_hash_mismatch"):
        subject.build_same_run_locale_report(status, "es-MX")


@pytest.mark.parametrize("value", [None, "not-a-sha", "a" * 63])
def test_canonical_truth_binding_is_required_and_well_formed(value):
    status = _status()
    if value is None:
        status["reports"].pop("canonical_truth_sha256")
        error = "canonical_truth_hash_required"
    else:
        status["reports"]["canonical_truth_sha256"] = value
        error = "canonical_truth_hash_invalid"

    with pytest.raises(ValueError, match=error):
        subject.build_same_run_locale_report(status, "es-MX")


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("run_id", "comprun_other", "status_canonical_run_id_mismatch"),
        ("repository", "Other/Repository", "status_canonical_repository_mismatch"),
        ("commit_sha", "b" * 40, "status_canonical_commit_sha_mismatch"),
        (
            "evidence_ledger_id",
            "ledger_other",
            "status_canonical_evidence_ledger_id_mismatch",
        ),
    ],
)
def test_status_cannot_be_paired_with_another_canonical_run(field, value, error):
    status = _status()
    status[field] = value

    with pytest.raises(ValueError, match=error):
        subject.build_same_run_locale_report(status, "es-MX")


def test_status_source_language_must_match_canonical_identity_language():
    status = _status(source_language="en")
    canonical = status["reports"]["json"]
    canonical["report_language"] = "es-MX"
    canonical["locale"] = "es-MX"
    canonical["identity"]["report_language"] = "es-MX"
    canonical["identity"]["locale"] = "es-MX"
    canonical["assessment"]["report_language"] = "es-MX"
    canonical["assessment"]["locale"] = "es-MX"
    status["reports"]["canonical_truth_sha256"] = subject._canonical_hash(
        canonical
    )

    with pytest.raises(ValueError, match="status_canonical_report_language_mismatch"):
        subject.build_same_run_locale_report(status, "es-MX")


def test_canonical_source_language_is_required_and_internally_consistent():
    missing = _status(source_language="en")
    canonical = missing["reports"]["json"]
    canonical.pop("report_language")
    canonical.pop("locale")
    canonical["identity"].pop("report_language")
    canonical["identity"].pop("locale")
    canonical["assessment"].pop("report_language")
    canonical["assessment"].pop("locale")
    missing["reports"]["canonical_truth_sha256"] = subject._canonical_hash(canonical)
    with pytest.raises(ValueError, match="canonical_report_language_required"):
        subject.build_same_run_locale_report(missing, "es-MX")

    inconsistent = _status(source_language="en")
    inconsistent["reports"]["json"]["locale"] = "es-MX"
    inconsistent["reports"]["canonical_truth_sha256"] = subject._canonical_hash(
        inconsistent["reports"]["json"]
    )
    with pytest.raises(ValueError, match="canonical_report_language_inconsistent"):
        subject.build_same_run_locale_report(inconsistent, "es-MX")


def test_evidence_ledger_and_current_report_identity_are_required_and_bound():
    missing_ledger = _status()
    missing_ledger.pop("evidence_ledger_id")
    missing_ledger["reports"]["json"]["identity"].pop("evidence_ledger_id")
    missing_ledger["reports"]["canonical_truth_sha256"] = subject._canonical_hash(
        missing_ledger["reports"]["json"]
    )
    with pytest.raises(ValueError, match="canonical_evidence_ledger_id_required"):
        subject.build_same_run_locale_report(missing_ledger, "es-MX")

    report_mismatch = _status()
    report_mismatch["reports"]["report_id"] = "comprehensive_report_other"
    with pytest.raises(ValueError, match="status_canonical_report_id_mismatch"):
        subject.build_same_run_locale_report(report_mismatch, "es-MX")


def test_alternate_locale_calls_full_production_assembler_and_invalidates_approval(
    monkeypatch,
):
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17

    status = _approved_status(
        source_language="en",
        client_delivery_allowed=True,
        canonical_updates={
            "approval": {"decision": "approved", "reviewer_identity": "human"},
            "accepted_edition": {"accepted_edition": True},
            "human_review_completed": True,
            "client_delivery_allowed": True,
            "approval_status": "approved_final",
            "delivery_status": "authorized",
        },
    )
    status["reports"].update(
        {
            "human_review_completed": True,
            "client_delivery_allowed": True,
            "approval_status": "approved_final",
            "delivery_status": "authorized",
        }
    )
    before = deepcopy(status)
    calls = []
    pdf_bytes = b"%PDF-1.4\nlocalized-full"

    def assemble(package):
        calls.append(deepcopy(package))
        localized_json = deepcopy(package["json"])
        localized_json.update(
            {
                "approval_status": "pending_human_approval",
                "delivery_status": "blocked_pending_human_approval",
                "client_delivery_allowed": False,
            }
        )
        return {
            "json": localized_json,
            "markdown": "# Informe integral",
            "html": "<article>Informe integral</article>",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "pdf_sha256": subject.hashlib.sha256(pdf_bytes).hexdigest(),
            "pdf_page_count": 1,
            "canonical_json_sha256": "b" * 64,
            "artifact_manifest": {"manifest_id": "localized-manifest"},
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "client_delivery_allowed": False,
        }

    monkeypatch.setattr(phase17, "rebuild_client_artifacts", assemble)

    result = subject.build_same_run_locale_report(status, "es-MX")

    assert len(calls) == 1
    assert status == before
    assert calls[0]["json"]["identity"]["report_language"] == "es-MX"
    assert calls[0]["json"]["assessment"]["report_language"] == "es-MX"
    assert calls[0]["json"]["approval_status"] == "pending_human_approval"
    assert "approval" not in calls[0]["json"]
    assert "accepted_edition" not in calls[0]["json"]
    assert result["report"]["json"]["identity"]["run_id"] == status["run_id"]
    assert result["report"]["json"]["approval_status"] == "approved_final"
    assert result["report"]["localized_artifact_json"]["approval_status"] == (
        "pending_human_approval"
    )
    assert result["report"]["artifact_manifest"]["manifest_id"] == "localized-manifest"
    assert result["localized_artifact_approval_invalidated"] is True
    assert result["human_review_completed"] is True
    assert result["client_delivery_allowed"] is True
    assert result["approval_status"] == "approved_final"
    assert result["delivery_status"] == "authorized"
    assert result["canonical_run_lifecycle"]["client_delivery_allowed"] is True
    assert result["localized_artifact_lifecycle"]["client_delivery_allowed"] is False
    assert result["report"]["client_delivery_allowed"] is False
    assert result["report"]["approval_status"] == "pending_human_approval"
    assert result["report"]["delivery_status"] == "blocked_pending_human_approval"


def test_approved_source_artifact_reuse_preserves_exact_lifecycle_state() -> None:
    status = _approved_status(client_delivery_allowed=True)
    status["reports"]["pdf_filename"] = "nico-approved-source.pdf"
    before = deepcopy(status)

    result = subject.build_same_run_locale_report(status, "en")
    response = subject.build_same_run_locale_pdf_response(status, "en")

    assert status == before
    assert result["client_delivery_allowed"] is True
    assert result["human_review_completed"] is True
    assert result["approval_status"] == "approved_final"
    assert result["delivery_status"] == "authorized"
    assert result["localized_artifact_approval_invalidated"] is False
    assert result["localized_artifact_requires_new_approval"] is False
    assert result["report"]["client_delivery_allowed"] is True
    assert result["report"]["approval_status"] == "approved_final"
    assert result["report"]["delivery_status"] == "authorized"
    assert response.headers["content-disposition"] == (
        'attachment; filename="nico-approved-source.pdf"'
    )


@pytest.mark.parametrize(
    ("delivery_allowed", "controller_delivery_status", "expected_delivery_status"),
    (
        (False, "pending_authorization", "pending_authorization"),
        (True, "approved_for_delivery", "authorized"),
    ),
)
def test_real_controller_approved_status_derives_consistent_source_lifecycle(
    delivery_allowed,
    controller_delivery_status,
    expected_delivery_status,
) -> None:
    status = _approved_status(
        source_language="en",
        client_delivery_allowed=delivery_allowed,
    )
    status["delivery_status"] = controller_delivery_status
    status["record"] = {
        "status": "approved",
        "human_review_completed": True,
        "client_delivery_allowed": delivery_allowed,
        "delivery_status": controller_delivery_status,
    }

    result = subject.build_same_run_locale_report(status, "en")

    assert result["human_review_completed"] is True
    assert result["approval_status"] == "approved_final"
    assert result["human_review_status"] == "approved"
    assert result["client_delivery_allowed"] is delivery_allowed
    assert result["delivery_status"] == expected_delivery_status
    assert result["client_delivery_status"] == (
        "authorized" if delivery_allowed else "pending_authorization"
    )
    assert result["report"]["approval_status"] == "approved_final"
    assert result["report"]["delivery_status"] == expected_delivery_status


def test_real_composed_same_run_en_es_preserves_truth_literals_and_navigation() -> None:
    from tests.test_v2_premium_report_renderer import _package

    from nico.comprehensive_engagement_metadata_v1 import (
        build_comprehensive_engagement_metadata,
    )
    from nico.comprehensive_report_review_integrity_v1 import (
        install_comprehensive_report_review_integrity_v1,
    )
    from nico.comprehensive_semantic_navigation_v1 import semantic_entry_records
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts

    install_comprehensive_report_review_integrity_v1()
    fixture = {
        "client_name": "Compañía  Águila",
        "project_name": "Proyecto  Ñandú /  Release 2.0",
        "primary_technical_contact": "María-José  Pérez - CTO /  Ingeniería",
        "access_method": "GitHub  Enterprise - acceso de  solo lectura",
        "authorized_scope": (
            "organizacion/proyecto - rama  release/2026.08; código, configuración y  CI/CD."
        ),
    }
    human_evidence = {
        "stakeholder_context": {
            "evidence": {
                key: [fixture[key]]
                for key in (
                    "primary_technical_contact",
                    "access_method",
                    "authorized_scope",
                )
            }
        }
    }
    package = _package("en")
    source_customer_id = package["json"]["identity"]["customer_id"]
    source_project_id = package["json"]["identity"]["project_id"]
    engagement = build_comprehensive_engagement_metadata(
        client_name=fixture["client_name"],
        project_name=fixture["project_name"],
        human_evidence=human_evidence,
    )
    package["json"]["engagement_metadata"] = engagement
    package["json"]["identity"].update(
        {
            "customer_name": fixture["client_name"],
            "project_name": fixture["project_name"],
            "primary_technical_contact": fixture["primary_technical_contact"],
            "access_method": fixture["access_method"],
            "authorized_scope": fixture["authorized_scope"],
            "engagement_metadata_sha256": engagement[
                "engagement_metadata_sha256"
            ],
        }
    )
    source = rebuild_client_artifacts(package)
    source_json = deepcopy(source["json"])
    source_hash = subject.canonical_sha256(source_json)
    reports = deepcopy(source)
    reports["report_id"] = "comprehensive_report_same_run_real"
    reports["canonical_truth_sha256"] = source_hash
    status = {
        "run_id": source_json["identity"]["run_id"],
        "repository": source_json["identity"]["repository"],
        "commit_sha": source_json["identity"]["commit_sha"],
        "evidence_ledger_id": source_json["identity"]["evidence_ledger_id"],
        "report_language": "en",
        "terminal": True,
        "reports": reports,
    }
    before = deepcopy(status)

    localized = subject.build_same_run_locale_report(status, "es-MX")

    assert status == before
    assert source_json["identity"]["customer_id"] == source_customer_id
    assert source_json["identity"]["project_id"] == source_project_id
    assert localized["canonical_truth_sha256"] == source_hash
    assert localized["report"]["json"] == source_json
    assert localized["report"]["localized_artifact_json"]["identity"][
        "report_language"
    ] == "es-MX"
    assert localized["report"]["approval_status"] == "pending_human_approval"
    assert localized["report"]["delivery_status"] == "blocked_pending_human_approval"
    assert localized["report"]["artifact_manifest"]["manifest_id"]
    assert localized["localized_artifact_approval_invalidated"] is True

    source_summary = next(
        stage
        for stage in source_json["stage_summaries"]
        if stage.get("stage_id") == "client_evidence_summary"
    )
    localized_json = localized["report"]["localized_artifact_json"]
    localized_summary = next(
        stage
        for stage in localized_json["stage_summaries"]
        if stage.get("stage_id") == "client_evidence_summary"
    )
    expected_english_summary = (
        f"Client name: {fixture['client_name']}",
        f"Project name: {fixture['project_name']}",
        f"Primary technical contact: {fixture['primary_technical_contact']}",
        f"Access method: {fixture['access_method']}",
        f"Authorized scope: {fixture['authorized_scope']}",
    )
    expected_spanish_summary = (
        f"Nombre del cliente: {fixture['client_name']}",
        f"Nombre del proyecto: {fixture['project_name']}",
        f"Contacto técnico principal: {fixture['primary_technical_contact']}",
        f"Método de acceso: {fixture['access_method']}",
        f"Alcance autorizado: {fixture['authorized_scope']}",
    )
    assert tuple(source_summary["evidence"][:5]) == expected_english_summary
    assert tuple(localized_summary["evidence"][:5]) == expected_spanish_summary
    assert all(
        source_summary["evidence"].count(line) == 1
        for line in expected_english_summary
    )
    assert all(
        localized_summary["evidence"].count(line) == 1
        for line in expected_spanish_summary
    )

    source_reader = PdfReader(io.BytesIO(base64.b64decode(source["pdf_base64"])))
    localized_pdf = base64.b64decode(localized["report"]["pdf_base64"])
    localized_reader = PdfReader(io.BytesIO(localized_pdf))
    source_entries, source_spanish = semantic_entry_records(source_reader)
    localized_entries, localized_spanish = semantic_entry_records(localized_reader)
    assert source_spanish is False
    assert localized_spanish is True
    assert {entry["section_id"] for entry in localized_entries} == {
        entry["section_id"] for entry in source_entries
    }
    assert source_reader.outline
    assert localized_reader.outline

    for reader, headings in (
        (source_reader, {"Findings"}),
        (localized_reader, {"Hallazgos"}),
    ):
        orphan_pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            lines = [
                line.strip()
                for line in (page.extract_text() or "").splitlines()
                if line.strip()
            ]
            content_lines = [
                line
                for line in lines
                if not re.fullmatch(
                    r"(?:Document page|Página del documento)\s+\d+\s+(?:of|de)\s+\d+",
                    line,
                )
                and not (
                    line.startswith("NICO Comprehensive ·")
                    and ("DRAFT" in line or "BORRADOR" in line)
                )
            ]
            if content_lines and content_lines[-1] in headings:
                orphan_pages.append(page_number)
        assert orphan_pages == []

    source_pdf_text = "\n".join(
        page.extract_text() or "" for page in source_reader.pages
    )
    localized_pdf_text = "\n".join(
        page.extract_text() or "" for page in localized_reader.pages
    )
    assert "Índice" in localized_pdf_text
    source_ci_body_pages = [
        page_number
        for page_number, page in enumerate(source_reader.pages, start=1)
        if page_number != 2
        and "CI/CD Operational Readiness and Historical Health"
        in (page.extract_text() or "")
    ]
    localized_ci_body_pages = [
        page_number
        for page_number, page in enumerate(localized_reader.pages, start=1)
        if page_number != 2
        and "Preparación operativa y salud histórica de CI/CD"
        in (page.extract_text() or "")
    ]
    assert source_ci_body_pages == [11]
    assert localized_ci_body_pages == [11]
    for authored_english in (
        "NICO | Comprehensive client review | automated draft",
        "Review page ",
        "Human context or additional evidence is required before this section can be accepted.",
        "Named people, rates, contract structure, geographic mix, and budget require client input.",
        "Decision findings:",
        "Exact-source findings:",
        "Confirmed material scanner findings:",
        "Review-required scanner candidates:",
        "NICO · compact finding register · automated draft",
        "Reduce complexity in page.tsx",
        "The canonical finding was retained against the assessed immutable commit.",
        "Regression risk is concentrated.",
        "Extract state transitions, data loading, and side-effect orchestration from",
        "The exact-SHA rerun no longer reports this condition at",
        "Targeted tests and the repository's full required-check suite pass",
    ):
        assert authored_english not in localized_pdf_text
    for allowed_literal in (
        "RISK-P1-001",
        "apps/web/app/page.tsx:100",
        "page.tsx",
        "Playwright",
        "JSON",
        "CSV",
        "SHA",
    ):
        assert allowed_literal in localized_pdf_text
    for expected in fixture.values():
        assert expected in source["markdown"]
        assert expected in source["html"]
        assert expected in source_pdf_text
        assert expected in localized["report"]["markdown"]
        assert expected in localized["report"]["html"]
        assert expected in localized_pdf_text
        normalized_duplicate = re.sub(r" {2,}", " ", expected)
        assert normalized_duplicate != expected
        for surface in (
            source["markdown"],
            source["html"],
            source_pdf_text,
            localized["report"]["markdown"],
            localized["report"]["html"],
            localized_pdf_text,
        ):
            assert normalized_duplicate not in surface


def test_non_terminal_run_cannot_publish_localized_report():
    status = _status()
    status["terminal"] = False

    with pytest.raises(ValueError, match="terminal_report_required"):
        subject.build_same_run_locale_report(status, "es-MX")


def test_only_english_and_mexican_spanish_are_supported():
    assert subject._normalize_report_language("en") == "en"
    assert subject._normalize_report_language("ES-mx") == "es-MX"
    with pytest.raises(ValueError, match="unsupported_report_language"):
        subject._normalize_report_language("fr")


def test_routes_install_exactly_once_and_preserve_delivery_boundary():
    app = FastAPI()

    first = subject.install_same_run_locale_report(app)
    second = subject.install_same_run_locale_report(app)

    assert first["route_count"] == 1
    assert first["pdf_route_count"] == 1
    assert second["route_count"] == 1
    assert second["pdf_route_count"] == 1
    assert second["same_canonical_run"] is True
    assert second["assessment_rerun"] is False
    assert second["canonical_truth_preserved"] is True
    assert second["human_review_required"] is True
    assert second["client_delivery_allowed"] is False


def test_localized_route_status_read_is_non_mutating() -> None:
    app = FastAPI()
    calls = []

    def status_read_only(run_id):
        calls.append(("read_only", run_id))
        return _status()

    def status(_run_id):
        raise AssertionError("localized GET must not call maintenance-capable status")

    app.state.comprehensive_api_controller = SimpleNamespace(
        status_read_only=status_read_only,
        status=status,
    )

    result = subject._controller_status(app, "comprun_same_run_1")

    assert result["run_id"] == "comprun_same_run_1"
    assert calls == [("read_only", "comprun_same_run_1")]


def test_controller_read_only_status_projects_accepted_edition_without_mutation() -> None:
    from nico.comprehensive_api_controller import ComprehensiveApiController

    status = _approved_status()
    canonical = status["reports"]["json"]
    record = {
        "artifact_schema": "nico.comprehensive_run_record.v1",
        "service_id": "comprehensive",
        "identity": {
            **canonical["identity"],
            "customer_id": "customer_same_run_1",
            "project_id": "project_same_run_1",
        },
        "status": "approved",
        "current_stage": "human_review_request",
        "completed_stages": ["final_comprehensive_report_generation"],
        "stage_results": {
            "final_comprehensive_report_generation": {
                "status": "complete",
                "report_package": status["reports"],
                "assessment": status["reports"]["json"]["assessment"],
            }
        },
        "blockers": [],
        "progress_percent": 100.0,
        "revision": 9,
        "terminal": True,
        "human_review_required": True,
        "human_review_completed": True,
        "client_delivery_allowed": False,
        "accepted_edition": status["accepted_edition"],
        "review_decision": deepcopy(status["accepted_edition"]),
        "review_history": [deepcopy(status["accepted_edition"])],
        "integrity_sha256": "record-integrity",
    }
    before = deepcopy(record)
    service = SimpleNamespace(load_read_only=lambda run_id: record)
    controller = ComprehensiveApiController(service)

    projected = controller.status_read_only("comprun_same_run_1")

    assert record == before
    assert projected["accepted_edition"] == record["accepted_edition"]
    assert projected["accepted_edition"] is not record["accepted_edition"]
    projected["accepted_edition"]["review"]["reason"] = "response-only mutation"
    assert record == before


def test_service_read_only_load_never_resumes_or_continues_a_run() -> None:
    from nico.comprehensive_run_service import ComprehensiveRunService

    calls = []
    record = {"run_id": "comprun_same_run_1", "revision": 17, "terminal": True}
    service = object.__new__(ComprehensiveRunService)
    service._store = SimpleNamespace(
        load=lambda run_id: calls.append(("load", run_id)) or record
    )
    service.resume = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("read-only localized retrieval must not resume a run")
    )

    loaded = service.load_read_only("comprun_same_run_1")

    assert loaded is record
    assert calls == [("load", "comprun_same_run_1")]


def test_review_download_bridge_uses_same_run_localized_pdf_route():
    bridge = Path("apps/web/app/AssessmentReviewPdfDownload.tsx").read_text(
        encoding="utf-8"
    )
    assert "/localized-report/${encodeURIComponent(reportLanguage)}/pdf" in bridge
    assert 'pathname === "/es-mx"' in bridge
    assert 'pathname.startsWith("/es-mx/")' in bridge
    assert "reportLanguageForRequest(uiLocale)" in bridge
    assert 'searchParams.get("report_language")' not in bridge
    assert "startExactRunDownload(runId, activeReportLanguage())" in bridge


def test_production_docker_entrypoint_mounts_same_run_locale_wrapper():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "nico.api.same_run_locale_report_bootstrap:app" in dockerfile
