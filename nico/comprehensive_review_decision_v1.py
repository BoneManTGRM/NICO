from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from nico.decision_grade_accepted_edition_v2 import build_accepted_report_edition

VERSION = "nico.comprehensive_review_decision.v2"
_REPORT_STAGE_IDS = (
    "final_comprehensive_report_generation",
    "risk_reduction_and_executive_briefing",
    "decision_report_generation",
)


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def report_package_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    stage_results = record.get("stage_results")
    if isinstance(stage_results, Mapping):
        for stage_id in _REPORT_STAGE_IDS:
            stage = stage_results.get(stage_id)
            if not isinstance(stage, Mapping):
                continue
            candidate = stage.get("report_package")
            if isinstance(candidate, Mapping):
                return deepcopy(dict(candidate))
            candidate = stage.get("reports")
            if isinstance(candidate, Mapping):
                return deepcopy(dict(candidate))
    candidate = record.get("reports")
    return deepcopy(dict(candidate)) if isinstance(candidate, Mapping) else {}


def _tree_sha(record: Mapping[str, Any]) -> str:
    stages = record.get("stage_results")
    if not isinstance(stages, Mapping):
        return ""
    stage = stages.get("immutable_repository_snapshot")
    if not isinstance(stage, Mapping):
        return ""
    snapshot = stage.get("snapshot")
    if isinstance(snapshot, Mapping) and snapshot.get("tree_sha"):
        return str(snapshot["tree_sha"]).strip()
    evidence = stage.get("evidence")
    if isinstance(evidence, Mapping) and evidence.get("tree_sha"):
        return str(evidence["tree_sha"]).strip()
    return str(stage.get("tree_sha") or "").strip()


def _scanner_run_id(record: Mapping[str, Any]) -> str:
    stages = record.get("stage_results")
    if not isinstance(stages, Mapping):
        return ""
    for stage_id in ("deep_scanner_triage", "dependency_security_static_analysis"):
        stage = stages.get(stage_id)
        if not isinstance(stage, Mapping):
            continue
        direct = str(stage.get("scan_id") or stage.get("scanner_run_id") or "").strip()
        if direct:
            return direct
        scanner = stage.get("scanner")
        if isinstance(scanner, Mapping):
            nested = str(scanner.get("scan_id") or scanner.get("scanner_run_id") or "").strip()
            if nested:
                return nested
    return ""


def _evidence_bundle_hash(record: Mapping[str, Any], package: Mapping[str, Any]) -> str:
    candidates: list[Any] = [
        package.get("evidence_bundle_sha256"),
        package.get("canonical_truth_sha256"),
    ]
    canonical = package.get("json")
    if isinstance(canonical, Mapping):
        candidates.extend(
            [
                canonical.get("evidence_bundle_sha256"),
                canonical.get("canonical_truth_sha256"),
            ]
        )
    identity = record.get("identity")
    if isinstance(identity, Mapping):
        candidates.append(identity.get("evidence_bundle_hash"))
    for value in candidates:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def _review_ledger_binding(record: Mapping[str, Any]) -> dict[str, str]:
    try:
        from nico.comprehensive_review_work_v2 import ledger_for_record

        ledger = ledger_for_record(record)
    except Exception:
        existing = record.get("review_work_ledger")
        if not isinstance(existing, Mapping):
            return {}
        ledger = deepcopy(dict(existing))
    if not ledger:
        return {}
    return {
        "review_work_ledger_sha256": _canonical_hash(ledger),
        "review_work_source_sha256": str(ledger.get("review_source_sha256") or "").strip(),
    }


def _bind_review_ledger_to_manifest(
    manifest: Mapping[str, Any],
    binding: Mapping[str, str],
) -> dict[str, Any]:
    output = deepcopy(dict(manifest))
    ledger_hash = str(binding.get("review_work_ledger_sha256") or "").strip()
    if not ledger_hash:
        return output
    output["review_work_ledger_sha256"] = ledger_hash
    source_hash = str(binding.get("review_work_source_sha256") or "").strip()
    if source_hash:
        output["review_work_source_sha256"] = source_hash

    review = output.get("review") if isinstance(output.get("review"), Mapping) else {}
    review = deepcopy(dict(review))
    review["review_work_ledger_sha256"] = ledger_hash
    if source_hash:
        review["review_work_source_sha256"] = source_hash
    review.pop("approval_certificate_sha256", None)
    review["approval_certificate_sha256"] = _canonical_hash(review)
    output["review"] = review

    output.pop("accepted_edition_manifest_sha256", None)
    output["accepted_edition_manifest_sha256"] = _canonical_hash(output)
    return output


def build_reviewed_edition(
    record: Mapping[str, Any],
    *,
    reviewer: str,
    reviewer_role: str,
    decision: str,
    decision_reason: str,
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Bind a human decision to the exact report artifacts and review ledger.

    The report itself is never regenerated during approval. For Phase 2 runs the
    accepted-edition certificate also binds the exact human-review ledger and its
    canonical evidence fingerprint, so disposition/QC state cannot be swapped after
    approval without invalidating the certificate chain.
    """

    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    package = report_package_from_record(record)
    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
    except Exception:
        pdf = b""
    manifest = build_accepted_report_edition(
        repository=str(identity.get("repository") or ""),
        commit_sha=str(identity.get("commit_sha") or ""),
        tree_sha=_tree_sha(record),
        run_id=str(identity.get("run_id") or ""),
        scanner_run_id=_scanner_run_id(record),
        evidence_bundle_hash=_evidence_bundle_hash(record, package),
        report_language=str(identity.get("report_language") or ""),
        assessment_depth=str(identity.get("assessment_depth") or ""),
        artifacts={
            "markdown": package.get("markdown"),
            "html": package.get("html"),
            "pdf": pdf,
            "json": package.get("json"),
        },
        reviewer=reviewer,
        reviewer_role=reviewer_role,
        decision=decision,
        decision_reason=decision_reason,
        decided_at=decided_at,
    )
    return _bind_review_ledger_to_manifest(manifest, _review_ledger_binding(record))


__all__ = ["VERSION", "build_reviewed_edition", "report_package_from_record"]
