from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

VERSION = "nico.phase7_release_gate.v1"


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    evidence_reference: str = ""
    reason: str = ""


REQUIRED_GATES: tuple[str, ...] = (
    "canonical_truth_integrated",
    "cross_format_truth_valid",
    "english_spanish_truth_equal",
    "required_scanners_complete",
    "scanner_artifacts_hashed",
    "exact_revision_ci_green",
    "missing_evidence_fail_closed",
    "github_authenticated_conformance",
    "unsupported_provider_claims_blocked",
    "ara_regression_assessment_validated",
    "nico_regression_assessment_validated",
    "pdf_visual_review_complete",
    "human_merge_authorization",
)


def evaluate_release_gate(results: Sequence[GateResult]) -> dict:
    by_name = {item.name: item for item in results}
    missing = [name for name in REQUIRED_GATES if name not in by_name]
    failed = [name for name in REQUIRED_GATES if name in by_name and not by_name[name].passed]
    evidence_missing = [
        name for name in REQUIRED_GATES
        if name in by_name and by_name[name].passed and not by_name[name].evidence_reference
    ]
    ready = not missing and not failed and not evidence_missing
    return {
        "version": VERSION,
        "ready_to_merge": ready,
        "client_delivery_allowed": False,
        "missing_gates": missing,
        "failed_gates": failed,
        "passed_without_evidence": evidence_missing,
        "results": [item.__dict__ for item in results],
    }


def require_release_ready(results: Sequence[GateResult]) -> Mapping:
    decision = evaluate_release_gate(results)
    if not decision["ready_to_merge"]:
        raise RuntimeError(
            "Phase 7 release blocked: "
            f"missing={decision['missing_gates']}; failed={decision['failed_gates']}; "
            f"passed_without_evidence={decision['passed_without_evidence']}"
        )
    return decision


__all__ = ["GateResult", "REQUIRED_GATES", "evaluate_release_gate", "require_release_ready"]
