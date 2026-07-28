from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from nico.final_assessment_truth_v1 import TruthViolation
from nico.phase8_operational_acceptance_v1 import (
    build_operational_acceptance,
    validate_pdf_review,
    validate_scanner_ledger,
)


REVISION = "a" * 40


def _scanner(name: str) -> dict:
    return {
        "scanner": name,
        "status": "completed",
        "commit_sha": REVISION,
        "command": f"{name} scan",
        "version": "1.0.0",
        "exit_code": 0,
        "artifact_sha256": "b" * 64,
    }


def test_scanner_ledger_requires_complete_exact_revision_records() -> None:
    result = validate_scanner_ledger(
        [_scanner("bandit"), _scanner("eslint")],
        expected_revision=REVISION,
        required_scanners=["bandit", "eslint"],
    )
    assert result["valid"] is True
    assert result["ledger_sha256"]

    bad = _scanner("bandit")
    bad["commit_sha"] = "c" * 40
    with pytest.raises(TruthViolation, match="revision_mismatch"):
        validate_scanner_ledger([bad], expected_revision=REVISION, required_scanners=["bandit"])


def test_pdf_review_rejects_blank_or_unapproved_output() -> None:
    with pytest.raises(TruthViolation, match="visual review failed"):
        validate_pdf_review(
            {
                "page_count": 10,
                "blank_pages": [4],
                "overflow_pages": [],
                "clipped_pages": [],
                "reviewer": "reviewer@example.com",
                "status": "approved",
            }
        )
    with pytest.raises(TruthViolation, match="identified human reviewer"):
        validate_pdf_review(
            {
                "page_count": 10,
                "blank_pages": [],
                "overflow_pages": [],
                "clipped_pages": [],
                "reviewer": "",
                "status": "pending",
            }
        )


def test_complete_package_builds_hashed_manifest(tmp_path: Path) -> None:
    artifact_paths = {}
    for surface in ("json", "markdown", "html", "pdf", "csv"):
        path = tmp_path / f"report.{surface if surface != 'markdown' else 'md'}"
        payload = b"%PDF-1.7\n" + b"x" * 2048 if surface == "pdf" else b"report-output"
        path.write_bytes(payload)
        artifact_paths[surface] = str(path)

    assessment = {
        "repository": "owner/repo",
        "commit_sha": REVISION,
        "run_id": "phase8-test-run",
        "assessment_identity": {
            "provider": "github",
            "repository": "owner/repo",
            "immutable_revision": REVISION,
        },
        "maturity_signal": {
            "observed_performance": 82,
            "coverage_adjusted_maturity": 80,
            "evidence_adjusted_readiness": 75,
        },
        "approval_state": "FINAL-PENDING-APPROVAL",
        "client_ready": False,
        "client_delivery_allowed": False,
        "canonical_findings": [{"finding_id": "RISK-ONE"}],
        "unavailable_data_notes": [],
        "truth_sha256": "d" * 64,
    }
    surface = deepcopy(assessment)
    language = deepcopy(assessment)

    result = build_operational_acceptance(
        assessment=assessment,
        english=language,
        spanish=language,
        surfaces={name: deepcopy(surface) for name in artifact_paths},
        artifact_paths=artifact_paths,
        scanner_records=[_scanner("bandit"), _scanner("eslint")],
        required_scanners=["bandit", "eslint"],
        pdf_review={
            "page_count": 10,
            "blank_pages": [],
            "overflow_pages": [],
            "clipped_pages": [],
            "reviewer": "reviewer@example.com",
            "status": "approved",
        },
    )
    assert result["valid"] is True
    assert result["client_delivery_allowed"] is False
    assert result["manifest"]["manifest_sha256"]
