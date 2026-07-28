from __future__ import annotations

from typing import Any, Mapping, Sequence

from nico.evidence_execution_contract_v1 import EvidenceContractViolation, ScannerExecutionRecord
from nico.evidence_orchestrator_v1 import finalize_evidence, require_exact_revision

VERSION = "nico.comprehensive_phase7_evidence_gateway.v1"


def apply_evidence_gate(
    assessment: Mapping[str, Any],
    *,
    records: Sequence[ScannerExecutionRecord],
    required_tools: Sequence[str],
    immutable_revision: str,
    allow_degraded: bool = False,
) -> dict[str, Any]:
    require_exact_revision(records, immutable_revision)
    decision = finalize_evidence(records, required_tools=required_tools, allow_degraded=allow_degraded)
    output = dict(assessment)
    output["evidence_gate_version"] = VERSION
    output["scanner_evidence_mode"] = decision["mode"]
    output["incomplete_scanners"] = list(decision["incomplete_tools"])
    output["score_normalization_allowed"] = bool(decision["score_normalization_allowed"])
    output["report_status"] = decision["report_status"]
    output["client_delivery_allowed"] = False
    output["client_ready"] = False
    output["human_review_required"] = True
    output["assessed_revision"] = immutable_revision
    output["scanner_execution_records"] = [
        {
            "tool": record.tool,
            "version": record.version,
            "status": record.status.value,
            "applicable": record.applicable,
            "immutable_revision": record.immutable_revision,
            "exact_revision_match": record.exact_revision_match,
            "exit_code": record.exit_code,
            "artifact_sha256": record.artifact_sha256,
            "raw_artifact": record.raw_artifact,
            "stdout_artifact": record.stdout_artifact,
            "stderr_artifact": record.stderr_artifact,
            "failure_class": record.failure_class.value,
            "failure_reason": record.failure_reason,
            "retry_count": record.retry_count,
            "finding_count": record.finding_count,
            "coverage_scope": dict(record.coverage_scope),
        }
        for record in records
    ]
    if decision["mode"] != "complete":
        output["technical_score"] = None
        output["evidence_adjusted_score"] = None
        output["score_withheld_reason"] = "Required scanner evidence is incomplete"
    return output


def assert_report_publishable(assessment: Mapping[str, Any]) -> None:
    if assessment.get("scanner_evidence_mode") != "complete":
        raise EvidenceContractViolation("Report is not publishable: scanner evidence is incomplete")
    if assessment.get("client_delivery_allowed"):
        raise EvidenceContractViolation("Automated evidence completion cannot bypass human approval")
    if assessment.get("report_status") != "FINAL-PENDING-APPROVAL":
        raise EvidenceContractViolation("Completed evidence must remain pending human approval")


__all__ = ["apply_evidence_gate", "assert_report_publishable"]
