from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.comprehensive_scanner_register_projection_truth.v57"
_NORMALIZER_MARKER = "_nico_scanner_register_projection_truth_v57"
_VALIDATOR_MARKER = "_nico_scanner_register_projection_validation_v57"


def _dict(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _digest(findings: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(
            findings,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _register_required(assessment: Mapping[str, Any]) -> bool:
    contract = assessment.get("score_contract")
    contract = contract if isinstance(contract, Mapping) else {}
    return bool(
        contract.get("canonical_finding_register_required") is True
        or isinstance(assessment.get("canonical_scanner_finding_register"), Mapping)
    )


def normalize_scanner_register_projection(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind source-register and rendered-register truth without conflating them.

    Scanner fingerprints and the source digest are created before client-safe
    redaction and report normalization. Those transformations are allowed to
    change display evidence, but they must not erase the immutable source digest,
    stable IDs, count parity, or exact-commit identity. The final rendered JSON
    therefore receives a second digest over the retained projection.
    """

    output = deepcopy(dict(canonical))
    assessment = _dict(output.get("assessment"))
    if not _register_required(assessment):
        return output

    register = _dict(assessment.get("canonical_scanner_finding_register"))
    findings = [
        deepcopy(dict(item))
        for item in _list(register.get("findings"))
        if isinstance(item, Mapping)
    ]
    totals = _dict(register.get("totals"))
    source_digest = str(
        register.get("source_canonical_digest_sha256")
        or register.get("canonical_digest_sha256")
        or ""
    ).strip()
    rendered_digest = _digest(findings)

    register.update(
        {
            "source_canonical_digest_sha256": source_digest,
            "rendered_projection_digest_sha256": rendered_digest,
            "projection_redaction_preserves_source_fingerprints": True,
            "findings": findings,
        }
    )
    assessment["canonical_scanner_finding_register"] = register

    coverage = _dict(assessment.get("evidence_coverage"))
    coverage.update(
        {
            "canonical_scanner_finding_count": _int(totals.get("raw")),
            "canonical_scanner_source_digest_sha256": source_digest,
            "canonical_scanner_rendered_digest_sha256": rendered_digest,
            "canonical_scanner_finding_register_status": register.get("status"),
            "decision_finding_count_is_separate": True,
        }
    )
    assessment["evidence_coverage"] = coverage
    output["assessment"] = assessment

    contract = _dict(output.get("v2_prepublication_contract"))
    contract.update(
        {
            "scanner_register_projection_truth_version": VERSION,
            "scanner_source_and_rendered_digests_separated": True,
            "scanner_candidate_count_separate_from_decision_finding_count": True,
        }
    )
    output["v2_prepublication_contract"] = contract
    return output


def scanner_register_projection_checks(canonical: Mapping[str, Any]) -> dict[str, bool]:
    assessment = canonical.get("assessment")
    assessment = assessment if isinstance(assessment, Mapping) else {}
    if not _register_required(assessment):
        return {
            "canonical_scanner_digest_recomputes": True,
            "canonical_scanner_coverage_reference_matches": True,
        }

    register = assessment.get("canonical_scanner_finding_register")
    register = register if isinstance(register, Mapping) else {}
    findings = [
        dict(item)
        for item in _list(register.get("findings"))
        if isinstance(item, Mapping)
    ]
    totals = register.get("totals")
    totals = totals if isinstance(totals, Mapping) else {}
    coverage = assessment.get("evidence_coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}

    source_digest = str(
        register.get("source_canonical_digest_sha256") or ""
    ).strip()
    rendered_digest = _digest(findings)
    source_reference = str(
        coverage.get("canonical_scanner_source_digest_sha256") or ""
    ).strip()
    rendered_reference = str(
        coverage.get("canonical_scanner_rendered_digest_sha256") or ""
    ).strip()

    digest_truth = bool(source_digest) and (
        str(register.get("canonical_digest_sha256") or "").strip()
        == source_digest
        and str(register.get("rendered_projection_digest_sha256") or "").strip()
        == rendered_digest
        and source_reference == source_digest
        and rendered_reference == rendered_digest
        and register.get("projection_redaction_preserves_source_fingerprints") is True
    )
    coverage_truth = (
        _int(coverage.get("canonical_scanner_finding_count"))
        == _int(totals.get("raw"))
        and coverage.get("canonical_scanner_finding_register_status")
        == register.get("status")
        and coverage.get("decision_finding_count_is_separate") is True
    )
    return {
        "canonical_scanner_digest_recomputes": digest_truth,
        "canonical_scanner_coverage_reference_matches": coverage_truth,
    }


def validate_scanner_register_projection(
    package: dict[str, Any],
    delegate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    result = deepcopy(delegate(package))
    canonical = package.get("json")
    canonical = canonical if isinstance(canonical, Mapping) else {}
    projection_checks = scanner_register_projection_checks(canonical)
    checks = _dict(result.get("checks"))
    checks.update(projection_checks)
    failed = sorted(name for name, passed in checks.items() if passed is not True)
    result.update(
        {
            "status": "verified" if not failed else "blocked",
            "version": VERSION,
            "checks": checks,
            "failed_checks": failed,
            "scanner_register_projection_truth": projection_checks,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return result


def install_comprehensive_scanner_register_projection_truth_v57() -> dict[str, Any]:
    from nico import comprehensive_final_artifact_truth_v54 as artifact_truth
    from nico import phase9_comprehensive_report_integration_v1 as integration

    current_normalizer: Callable[[Mapping[str, Any]], dict[str, Any]] = (
        integration.normalize_canonical_report
    )
    if not getattr(current_normalizer, _NORMALIZER_MARKER, False):

        @wraps(current_normalizer)
        def normalized(report: Mapping[str, Any]) -> dict[str, Any]:
            return normalize_scanner_register_projection(current_normalizer(report))

        setattr(normalized, _NORMALIZER_MARKER, True)
        setattr(normalized, "_nico_previous", current_normalizer)
        integration.normalize_canonical_report = normalized

    current_validator: Callable[[dict[str, Any]], dict[str, Any]] = (
        artifact_truth.validate_final_report_package
    )
    if not getattr(current_validator, _VALIDATOR_MARKER, False):

        @wraps(current_validator)
        def validated(package: dict[str, Any]) -> dict[str, Any]:
            return validate_scanner_register_projection(package, current_validator)

        setattr(validated, _VALIDATOR_MARKER, True)
        setattr(validated, "_nico_previous", current_validator)
        artifact_truth.validate_final_report_package = validated

    return {
        "status": "installed",
        "version": VERSION,
        "normalizer_bound": getattr(
            integration.normalize_canonical_report,
            _NORMALIZER_MARKER,
            False,
        ),
        "validator_bound": getattr(
            artifact_truth.validate_final_report_package,
            _VALIDATOR_MARKER,
            False,
        ),
        "source_digest_preserved": True,
        "rendered_projection_digest_required": True,
        "scanner_candidate_count_separate_from_decision_findings": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_scanner_register_projection_truth_v57",
    "normalize_scanner_register_projection",
    "scanner_register_projection_checks",
    "validate_scanner_register_projection",
]
