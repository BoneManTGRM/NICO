from __future__ import annotations

from nico import final_score_reconciliation_patch as reconciliation
from nico.code_audit_test_evidence_cleanup_patch import (
    clean_code_audit_test_evidence,
    install_code_audit_test_evidence_cleanup_patch,
)


STALE = "No test-path signals were found in fetched text files."
METRICS = (
    "Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, "
    "risky pattern hits=0, test-path signals=0."
)


def _result(*, recursive_test_count: int = 351) -> dict:
    architecture_evidence = []
    if recursive_test_count:
        architecture_evidence.append(
            f"Repository tree test-path signal count: {recursive_test_count}."
        )
    return {
        "status": "complete",
        "sections": [
            {
                "id": "code_audit",
                "score": 86,
                "status": "green",
                "summary": "Code audit.",
                "evidence": [METRICS, STALE],
                "findings": [STALE],
                "unavailable": [STALE],
                "verified_claims": [METRICS, STALE],
                "unverified_claims": [STALE],
            },
            {
                "id": "architecture_debt",
                "score": 94,
                "status": "green",
                "summary": "Architecture.",
                "evidence": architecture_evidence,
                "findings": [],
                "unavailable": [],
            },
        ],
    }


def test_cleanup_removes_only_contradicted_standalone_claim() -> None:
    result = _result()

    changed = reconciliation.reconcile_code_audit_test_evidence(result)
    code = next(item for item in result["sections"] if item["id"] == "code_audit")

    assert changed is True
    assert code["score"] == 90
    for key in (
        "evidence",
        "findings",
        "unavailable",
        "verified_claims",
        "unverified_claims",
    ):
        assert not any(STALE.lower() in str(item).lower() for item in code[key])
    assert METRICS in code["evidence"]
    assert any("recursive repository tree contains 351" in item for item in code["evidence"])
    assert code["verified_claims"] == code["evidence"]
    assert code["unverified_claims"] == code["unavailable"]


def test_cleanup_fails_closed_without_positive_recursive_tree_evidence() -> None:
    result = _result(recursive_test_count=0)

    changed = clean_code_audit_test_evidence(result)
    code = next(item for item in result["sections"] if item["id"] == "code_audit")

    assert changed is False
    assert STALE in code["evidence"]
    assert STALE in code["verified_claims"]


def test_cleanup_preserves_unrelated_findings_and_evidence() -> None:
    result = _result()
    code = next(item for item in result["sections"] if item["id"] == "code_audit")
    code["evidence"].append("Commit velocity evidence remains available.")
    code["findings"].append("A separate human-review finding remains.")

    clean_code_audit_test_evidence(result)

    assert "Commit velocity evidence remains available." in code["evidence"]
    assert "A separate human-review finding remains." in code["findings"]


def test_installer_is_idempotent() -> None:
    first = install_code_audit_test_evidence_cleanup_patch()
    second = install_code_audit_test_evidence_cleanup_patch()

    assert first["bounded_sample_metrics_preserved"] is True
    assert second["status"] == "already_installed"
    assert second["standalone_absence_claim_removed"] is True
