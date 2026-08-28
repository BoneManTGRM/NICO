from __future__ import annotations

import io
import re

import pytest
from pypdf import PdfReader
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate

from nico.comprehensive_human_review_package_cleanup_v1 import (
    _digest_markup,
    _outline_title,
    assert_human_review_package_cleanup,
    build_ci_operational_stage,
    build_scanner_execution_stage,
    render_manifest_approval_supplement,
    sanitize_client_identity,
    sanitize_rendered_stage,
)


class _Renderer:
    @staticmethod
    def _stage(
        stage_id: str,
        title: str,
        summary: str,
        *,
        evidence: list[str] | None = None,
        findings: list[str] | None = None,
        unavailable: list[str] | None = None,
        status: str = "complete",
    ) -> dict:
        return {
            "stage_id": stage_id,
            "title": title,
            "summary": summary,
            "evidence": list(evidence or []),
            "findings": list(findings or []),
            "unavailable": list(unavailable or []),
            "status": status,
        }


def _pdf(pages: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    for lines in pages:
        y = 760
        for line in lines:
            document.drawString(40, y, line)
            y -= 18
        document.showPage()
    document.save()
    return buffer.getvalue()


def test_client_identity_placeholders_render_not_supplied() -> None:
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "default_customer",
            "project_id": "unknown_project",
        },
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 89,
        },
    }

    cleaned = sanitize_client_identity(canonical)

    assert cleaned["identity"]["customer_id"] == "Not supplied"
    assert cleaned["identity"]["project_id"] == "Not supplied"
    assert cleaned["assessment"] == canonical["assessment"]


def test_scope_ids_remain_independent_from_supplied_client_names() -> None:
    cleaned = sanitize_client_identity(
        {
            "identity": {
                "customer_id": "internal-id",
                "customer_name": "Acme Holdings",
                "project_id": "internal-project",
                "project_name": "Mercury",
            }
        }
    )

    assert cleaned["identity"]["customer_id"] == "internal-id"
    assert cleaned["identity"]["project_id"] == "internal-project"


def test_scanner_execution_and_candidate_disposition_are_separate() -> None:
    canonical = {
        "scanner_execution_records": [
            {
                "scanner_name": f"scanner-{index}",
                "state": "completed",
                "completed": True,
                "exact_commit_match": True,
                "artifact_hash": f"hash-{index}",
                "finding_count": 0,
            }
            for index in range(9)
        ],
        "review_candidate_summary": {
            "raw_total": 662,
            "review_required_total": 662,
            "verified_material_total": 0,
            "by_category": {
                "dependency": {
                    "raw": 59,
                    "review_required": 59,
                    "material": 0,
                    "excluded_test_only": 0,
                    "approved_or_nonblocking": 0,
                },
                "secret": {
                    "raw": 17,
                    "review_required": 17,
                    "material": 0,
                    "excluded_test_only": 0,
                    "approved_or_nonblocking": 0,
                },
                "static": {
                    "raw": 586,
                    "review_required": 586,
                    "material": 0,
                    "excluded_test_only": 0,
                    "approved_or_nonblocking": 0,
                },
            },
        },
    }

    stage = build_scanner_execution_stage(canonical, _Renderer)

    assert "9 of 9 applicable scanner executions completed" in stage["summary"]
    assert "No scanner execution remains incomplete" in stage["summary"]
    assert "662 resulting candidates remain pending human disposition" in stage["summary"]
    assert "Scanner completion does not equal candidate approval" in stage["summary"]
    combined = "\n".join(stage["evidence"])
    assert "Confirmed material finding count: 0." in combined
    assert "Raw candidate count: 662." in combined
    assert "Review-required candidate count: 662." in combined
    assert "retained finding count" not in combined.casefold()


def test_operational_populations_render_separately_without_blank_values() -> None:
    canonical = {
        "ci_operational_context": {
            "successful_runs": 81,
            "workflow_outcome_classes": {
                "success": 81,
                "failure": 10,
                "unknown": 9,
            },
            "jobs_observed": 38,
            "job_success_rate": 1.0,
            "deployments_observed": 10,
            "successful_deployments": 7,
            "non_success_deployments": ".",
            "observation_scope": "bounded GitHub evidence sample",
        }
    }

    stage = build_ci_operational_stage(canonical, _Renderer)

    assert stage is not None
    combined = "\n".join(stage["evidence"])
    assert "Workflow runs: 81 successful of 100 observed (81%)" in combined
    assert "Workflow jobs: 38 successful of 38 observed (100%)" in combined
    assert "Deployments: 7 successful of 10 observed (70%)" in combined
    assert "Non-success or unresolved deployment observations: 3." in combined
    assert "Outcome classification breakdown: Not available." in combined
    assert "Non-success deployment classification: Not available." not in combined
    assert "Non-success deployments: ." not in combined


def test_rendered_stage_removes_internal_flattening_and_cross_stage_complexity() -> None:
    stage = sanitize_rendered_stage(
        {
            "stage_id": "dependency_security_static_analysis",
            "evidence": [
                "scanner_triage.canonical_scanner_finding_register_reference.canonical_digest_sha256: abc",
                "9 scanner executions completed.",
            ],
            "findings": [
                "P1 · Reduce complexity in verify_client_delivery_package",
                "Dependency · GHSA-example · Human review required",
            ],
        }
    )

    assert stage["evidence"] == ["9 scanner executions completed."]
    assert stage["findings"] == [
        "Dependency · GHSA-example · Human review required"
    ]


def test_toc_title_is_allowlisted_and_internal_details_are_rejected() -> None:
    assert (
        _outline_title(
            "NICO Comprehensive · run · AUTOMATED DRAFT\n"
            "CI/CD Operational Readiness and Historical Health\n"
            "Stage ID: ci_cd_operational_readiness"
        )
        == "CI/CD Operational Readiness and Historical Health"
    )
    assert (
        _outline_title(
            "NICO Comprehensive · run · AUTOMATED DRAFT\n"
            "scanner_triage.canonical_scanner_finding_register_reference.canonical_digest_sha256:\n"
            "abc"
        )
        == "Report page"
    )
    assert (
        _outline_title(
            "NICO Comprehensive · run · AUTOMATED DRAFT\n"
            "P1 · Reduce complexity in verify_client_delivery_package"
        )
        == "Report page"
    )


def test_digest_markup_uses_two_balanced_chunks() -> None:
    digest = "a" * 64
    assert _digest_markup(digest) == ("a" * 32 + "<br/>" + "a" * 32)


def test_manifest_pdf_keeps_filenames_and_digests_reconstructable() -> None:
    digest = "0123456789abcdef" * 4
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "c" * 40,
            "run_id": "comprun_example",
            "evidence_ledger_id": "ledger_example",
            "generated_at": "2026-08-05T00:37:32Z",
        },
        "lifecycle": {
            "review_package_ready": True,
            "human_review_status": "pending",
            "client_delivery_status": "blocked",
        },
        "approval": {},
    }
    entries = [
        {
            "artifact_type": "candidate_register_json",
            "filename": (
                "nico-comprun_example-candidate-register-with-a-long-but-"
                "intelligible-name.json"
            ),
            "sha256": digest,
        }
    ]

    pdf = render_manifest_approval_supplement(canonical, entries)
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    compact = re.sub(r"\s+", "", extracted)

    assert len(reader.pages) == 2
    assert digest in compact
    assert "candidate-register" in extracted
    assert not re.search(
        r"\b[0-9a-f]{20,63}\s*\n\s*[0-9a-f]\b",
        extracted,
        re.IGNORECASE,
    )


def test_final_cleanup_rejects_blank_metric_and_orphan_internal_page() -> None:
    canonical = {
        "identity": {
            "customer_id": "Not supplied",
            "project_id": "Not supplied",
        },
        "stage_summaries": [],
    }
    blank_metric_pdf = _pdf(
        [
            ["Table of Contents", "Executive Decision Brief 2"],
            ["CI/CD Operational Readiness", "Non-success deployments: ."],
        ]
    )
    with pytest.raises(ValueError, match="blank non-success deployment metric"):
        assert_human_review_package_cleanup(
            canonical,
            "AUTOMATED DRAFT",
            "<p>CLIENT DELIVERY BLOCKED</p>",
            blank_metric_pdf,
        )

    orphan_pdf = _pdf(
        [
            ["Table of Contents", "Executive Decision Brief 2"],
            [
                "scanner_triage.canonical_scanner_finding_register_reference.canonical_digest_sha256:",
                "a" * 64,
            ],
        ]
    )
    with pytest.raises(ValueError, match="orphan detail page"):
        assert_human_review_package_cleanup(
            canonical,
            "AUTOMATED DRAFT",
            "<p>CLIENT DELIVERY BLOCKED</p>",
            orphan_pdf,
        )
