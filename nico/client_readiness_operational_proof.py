from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

VERSION = "nico.client-readiness-operational-proof.v1"

REQUIRED_JOURNEYS = {
    "production_smoke",
    "authentication",
    "authorization",
    "assessment_create",
    "assessment_continue",
    "assessment_recovery",
    "report_download",
    "mobile_webkit",
    "restart_recovery",
}

DEPLOYMENT_CLASSIFICATIONS = {
    "successful",
    "product_defect",
    "infrastructure_failure",
    "canceled_or_superseded",
    "timeout",
    "configuration_issue",
    "unknown",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{40}", _text(value)))


def _valid_digest(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", _text(value)))


def _evidence_errors(record: Mapping[str, Any], release_sha: str, *, allow_other_sha: bool = False) -> list[str]:
    errors: list[str] = []
    if not _text(record.get("evidence_id")):
        errors.append("evidence_id is required")
    record_sha = _text(record.get("release_sha"))
    if not _valid_sha(record_sha):
        errors.append("release_sha must be a 40-character Git SHA")
    elif not allow_other_sha and record_sha.lower() != release_sha.lower():
        errors.append("evidence is not bound to the exact release SHA")
    if not _text(record.get("environment")):
        errors.append("environment is required")
    if not _text(record.get("observed_at")):
        errors.append("observed_at is required")
    if not _valid_digest(record.get("artifact_sha256")):
        errors.append("artifact_sha256 must be a 64-character SHA-256 digest")
    return errors


def _duplicate_values(items: Iterable[str]) -> list[str]:
    return sorted(value for value, count in Counter(items).items() if value and count > 1)


def build_operational_proof_bundle(
    *,
    repository: str,
    release_sha: str,
    frontend_deployment: Mapping[str, Any],
    backend_deployment: Mapping[str, Any],
    required_checks: Iterable[Mapping[str, Any]],
    journeys: Iterable[Mapping[str, Any]],
    deployments: Iterable[Mapping[str, Any]],
    rollback: Mapping[str, Any],
    environment: str = "production",
) -> dict[str, Any]:
    """Build one exact-SHA, fail-closed production-readiness proof manifest.

    This function validates retained evidence. It does not run deployments, infer
    outcomes, or convert repository configuration into an operational claim.
    """

    release_sha = _text(release_sha).lower()
    blockers: list[str] = []
    invalid_evidence: list[dict[str, Any]] = []
    if not _text(repository):
        blockers.append("repository is required")
    if not _valid_sha(release_sha):
        blockers.append("release_sha must be a 40-character Git SHA")
    if not _text(environment):
        blockers.append("environment is required")

    services = {
        "frontend": deepcopy(dict(frontend_deployment)),
        "backend": deepcopy(dict(backend_deployment)),
    }
    for service, record in services.items():
        errors = _evidence_errors(record, release_sha)
        deployed_sha = _text(record.get("deployed_sha") or record.get("release_sha"))
        if deployed_sha.lower() != release_sha:
            errors.append(f"{service} deployed_sha does not match the release SHA")
        if _text(record.get("status")).lower() != "successful":
            errors.append(f"{service} deployment is not successful")
        if errors:
            invalid_evidence.append({"kind": "service_deployment", "id": service, "errors": errors})

    check_records = [deepcopy(dict(item)) for item in required_checks if isinstance(item, Mapping)]
    duplicate_checks = _duplicate_values(_text(item.get("name")) for item in check_records)
    if duplicate_checks:
        blockers.append(f"duplicate required checks: {', '.join(duplicate_checks)}")
    if not check_records:
        blockers.append("required-check evidence is missing")
    for index, record in enumerate(check_records):
        errors = _evidence_errors(record, release_sha)
        if not _text(record.get("name")):
            errors.append("required check name is missing")
        if _text(record.get("conclusion")).lower() not in {"success", "passed"}:
            errors.append("required check did not pass")
        if record.get("required") is not True:
            errors.append("check is not proven to be required")
        if errors:
            invalid_evidence.append({"kind": "required_check", "id": _text(record.get("name")) or str(index), "errors": errors})

    journey_records = [deepcopy(dict(item)) for item in journeys if isinstance(item, Mapping)]
    journey_names = [_text(item.get("journey")).lower() for item in journey_records]
    duplicate_journeys = _duplicate_values(journey_names)
    if duplicate_journeys:
        blockers.append(f"duplicate journey evidence: {', '.join(duplicate_journeys)}")
    missing_journeys = sorted(REQUIRED_JOURNEYS.difference(journey_names))
    if missing_journeys:
        blockers.append(f"required production journeys are missing: {', '.join(missing_journeys)}")
    unexpected_journeys = sorted(set(journey_names).difference(REQUIRED_JOURNEYS))
    for index, record in enumerate(journey_records):
        errors = _evidence_errors(record, release_sha)
        journey = _text(record.get("journey")).lower()
        if journey not in REQUIRED_JOURNEYS:
            errors.append("journey is not in the canonical required journey set")
        if _text(record.get("status")).lower() not in {"success", "passed"}:
            errors.append("journey did not pass")
        if errors:
            invalid_evidence.append({"kind": "journey", "id": journey or str(index), "errors": errors})

    deployment_records = [deepcopy(dict(item)) for item in deployments if isinstance(item, Mapping)]
    deployment_ids = [_text(item.get("deployment_id")) for item in deployment_records]
    duplicate_deployments = _duplicate_values(deployment_ids)
    if duplicate_deployments:
        blockers.append(f"duplicate deployment observations: {', '.join(duplicate_deployments)}")
    if not deployment_records:
        blockers.append("deployment history is missing")
    for index, record in enumerate(deployment_records):
        errors = _evidence_errors(record, release_sha, allow_other_sha=True)
        classification = _text(record.get("classification")).lower()
        if not _text(record.get("deployment_id")):
            errors.append("deployment_id is required")
        if classification not in DEPLOYMENT_CLASSIFICATIONS:
            errors.append("deployment classification is missing or unsupported")
        if not _text(record.get("classification_basis")):
            errors.append("classification_basis is required")
        if errors:
            invalid_evidence.append({"kind": "deployment", "id": _text(record.get("deployment_id")) or str(index), "errors": errors})

    current_release_success = any(
        _text(item.get("release_sha")).lower() == release_sha
        and _text(item.get("classification")).lower() == "successful"
        for item in deployment_records
    )
    if not current_release_success:
        blockers.append("deployment history does not contain a successful observation for the exact release SHA")

    rollback_record = deepcopy(dict(rollback))
    rollback_errors = _evidence_errors(rollback_record, release_sha)
    if not _text(rollback_record.get("procedure")):
        rollback_errors.append("rollback procedure is required")
    if _text(rollback_record.get("exercise_status")).lower() not in {"success", "passed"}:
        rollback_errors.append("a successful rollback or recovery exercise is required")
    if not _text(rollback_record.get("exercise_result")):
        rollback_errors.append("rollback exercise_result is required")
    if rollback_errors:
        invalid_evidence.append({"kind": "rollback", "id": _text(rollback_record.get("evidence_id")) or "rollback", "errors": rollback_errors})

    if invalid_evidence:
        blockers.append("one or more operational evidence records are invalid")

    classification_counts = Counter(_text(item.get("classification")).lower() for item in deployment_records)
    successful = int(classification_counts.get("successful", 0))
    observed = len(deployment_records)
    non_success = observed - successful
    if successful + non_success != observed:
        blockers.append("deployment population does not reconcile")

    proof_basis = {
        "version": VERSION,
        "repository": _text(repository),
        "release_sha": release_sha,
        "environment": _text(environment),
        "service_evidence": {key: value.get("artifact_sha256") for key, value in services.items()},
        "check_evidence": sorted(_text(item.get("artifact_sha256")) for item in check_records),
        "journey_evidence": sorted(_text(item.get("artifact_sha256")) for item in journey_records),
        "deployment_evidence": sorted(_text(item.get("artifact_sha256")) for item in deployment_records),
        "rollback_evidence": _text(rollback_record.get("artifact_sha256")),
    }
    ready = not blockers
    return {
        "schema_version": VERSION,
        "repository": _text(repository),
        "release_sha": release_sha,
        "environment": _text(environment),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "passed" if ready else "blocked",
        "operational_readiness_demonstrated": ready,
        "client_delivery_allowed": False,
        "services": services,
        "required_checks": check_records,
        "journeys": journey_records,
        "deployments": deployment_records,
        "rollback": rollback_record,
        "deployment_summary": {
            "observed": observed,
            "successful": successful,
            "non_success": non_success,
            "classification_counts": dict(sorted(classification_counts.items())),
            "population_reconciles": successful + non_success == observed,
        },
        "missing_journeys": missing_journeys,
        "unexpected_journeys": unexpected_journeys,
        "invalid_evidence": invalid_evidence,
        "blockers": blockers,
        "proof_manifest_sha256": _sha256(proof_basis),
        "rule": "Operational readiness requires retained exact-SHA production evidence; repository configuration and historical counts alone cannot establish it.",
    }


def operational_proof_gate(bundle: Mapping[str, Any], *, expected_repository: str, expected_release_sha: str) -> dict[str, Any]:
    blockers: list[str] = []
    if str(bundle.get("schema_version") or "") != VERSION:
        blockers.append("operational proof schema version is missing or unsupported")
    if _text(bundle.get("repository")) != _text(expected_repository):
        blockers.append("operational proof repository identity does not match")
    if _text(bundle.get("release_sha")).lower() != _text(expected_release_sha).lower():
        blockers.append("operational proof release SHA does not match")
    if bundle.get("operational_readiness_demonstrated") is not True:
        blockers.append("operational readiness is not demonstrated")
    if bundle.get("blockers"):
        blockers.append("operational proof contains unresolved blockers")
    if bundle.get("invalid_evidence"):
        blockers.append("operational proof contains invalid evidence")
    summary = bundle.get("deployment_summary") if isinstance(bundle.get("deployment_summary"), Mapping) else {}
    if summary.get("population_reconciles") is not True:
        blockers.append("deployment population does not reconcile")
    if not _valid_digest(bundle.get("proof_manifest_sha256")):
        blockers.append("operational proof manifest digest is missing or invalid")
    return {
        "status": "passed" if not blockers else "blocked",
        "ready_for_next_gate": not blockers,
        "client_delivery_allowed": False,
        "blockers": blockers,
        "proof_manifest_sha256": bundle.get("proof_manifest_sha256") or "",
        "rule": "Passing operational proof is necessary but never sufficient for client delivery authorization.",
    }


__all__ = [
    "DEPLOYMENT_CLASSIFICATIONS",
    "REQUIRED_JOURNEYS",
    "VERSION",
    "build_operational_proof_bundle",
    "operational_proof_gate",
]
