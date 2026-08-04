from __future__ import annotations

from nico.exact_artifact_review_compat_v1 import _requires_exact_review


def test_legacy_review_without_manifest_uses_existing_review_contract() -> None:
    report = {
        "report_id": "legacy-report",
        "formats": {
            "json": {
                "report_path": "full_run",
                "human_review_required": True,
            }
        },
    }
    approval = {
        "report_id": "legacy-report",
        "approval_id": "legacy-approval",
    }

    assert _requires_exact_review(report, approval) is False


def test_manifest_aware_review_requires_exact_contract() -> None:
    report = {
        "report_id": "manifest-report",
        "draft_artifact_identity": {
            "artifact_schema": "nico.comprehensive-draft-artifact-identity.v1",
            "manifest_id": "NICO-MANIFEST-EXAMPLE",
        },
    }

    assert _requires_exact_review(report, {"report_id": "manifest-report"}) is True


def test_declared_exact_review_fails_closed_even_when_identity_is_missing() -> None:
    report = {"report_id": "declared-exact-report"}
    approval = {
        "report_id": "declared-exact-report",
        "exact_artifact_approval_required": True,
    }

    assert _requires_exact_review(report, approval) is True


def test_approval_digest_marker_enters_exact_review_contract() -> None:
    report = {"report_id": "digest-report"}
    approval = {
        "report_id": "digest-report",
        "approved_pdf_sha256": "a" * 64,
    }

    assert _requires_exact_review(report, approval) is True
