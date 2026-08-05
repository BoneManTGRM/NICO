from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping, Sequence

VERSION = "nico.comprehensive_canonical_evidence.v1"
MANIFEST_KEY = "canonical_evidence_manifest"
DIGEST_KEY = "canonical_evidence_sha256"

_SHA40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_FORMAT_PAYLOAD_KEYS = {
    "html",
    "markdown",
    "pdf_base64",
    "raw_output",
    "stderr",
    "stdout",
    "zip_base64",
}
_SELF_KEYS = {MANIFEST_KEY, DIGEST_KEY}

_BINDING_PATHS: dict[str, tuple[tuple[str, ...], ...]] = {
    "identity": (
        ("identity",),
        ("repository",),
        ("commit_sha",),
        ("run_id",),
        ("evidence_ledger_id",),
    ),
    "scanner_evidence": (
        ("requested_scanner_records",),
        ("scanner_execution_records",),
        ("not_applicable_scanner_records",),
        ("assessment", "requested_scanner_records"),
        ("assessment", "scanner_execution_records"),
        ("assessment", "not_applicable_scanner_records"),
        ("assessment", "scanner_applicability_summary"),
    ),
    "candidate_evidence": (
        ("review_candidate_summary",),
        ("candidate_register",),
        ("candidate_register_json",),
        ("assessment", "review_candidate_summary"),
        ("assessment", "canonical_scanner_finding_register"),
        ("assessment", "scanner_finding_summary"),
        ("assessment", "evidence_coverage"),
    ),
    "finding_evidence": (
        ("canonical_findings",),
        ("findings_register",),
        ("client_finding_remediation_register",),
        ("assessment", "decision_grade_findings_register"),
        ("assessment", "executive_risk_register"),
    ),
    "scoring_evidence": (
        ("assessment", "technical_score"),
        ("assessment", "canonical_evidence_adjusted_score"),
        ("assessment", "evidence_adjusted_score"),
        ("assessment", "maturity_signal"),
        ("assessment", "score_contract"),
        ("assessment", "score_reconciliation"),
        ("assessment", "scoring_weights"),
        ("assessment", "sections"),
    ),
    "stage_evidence": (
        ("stage_summaries",),
        ("assessment", "stage_summaries"),
        ("stages",),
        ("assessment", "stages"),
    ),
    "mutable_operational_evidence": (
        ("ci_operational_context",),
        ("operational_proof",),
        ("operational_proof_bundle",),
        ("assessment", "ci_cd_operational_health"),
        ("assessment", "operational_proof"),
        ("assessment", "operational_proof_bundle"),
    ),
    "limitations": (
        ("limitations",),
        ("human_evidence_summary",),
        ("assessment", "limitations"),
        ("assessment", "human_evidence_summary"),
        ("assessment", "unavailable_evidence"),
    ),
    "lifecycle": (
        ("lifecycle",),
        ("approval",),
        ("report_finality",),
        ("approval_status",),
        ("delivery_status",),
        ("human_review_required",),
        ("client_delivery_allowed",),
    ),
    "artifact_identities": (
        ("artifact_manifest",),
        ("evidence_manifest",),
        ("artifact_identities",),
        ("assessment", "artifact_manifest"),
        ("assessment", "evidence_manifest"),
    ),
}

_TECHNICAL_BINDINGS = (
    "scanner_evidence",
    "candidate_evidence",
    "finding_evidence",
    "scoring_evidence",
    "stage_evidence",
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _clean(value: Any) -> Any:
    """Remove self-referential manifests and rendered byte payloads.

    The canonical JSON remains the authority. This helper only creates a stable
    digest subject; it does not rewrite, infer, or independently recalculate any
    evidence, finding, candidate, score, limitation, or lifecycle value.
    """

    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key)
            if normalized in _SELF_KEYS or normalized in _FORMAT_PAYLOAD_KEYS:
                continue
            output[normalized] = _clean(item)
        return output
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, tuple):
        return [_clean(item) for item in value]
    return deepcopy(value)


def _path_text(path: Sequence[str]) -> str:
    return ".".join(path)


def _read_path(root: Mapping[str, Any], path: Sequence[str]) -> tuple[bool, Any]:
    current: Any = root
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _binding(root: Mapping[str, Any], paths: Sequence[Sequence[str]]) -> dict[str, Any]:
    retained: dict[str, Any] = {}
    present_paths: list[str] = []
    for path in paths:
        present, value = _read_path(root, path)
        if not present:
            continue
        path_name = _path_text(path)
        retained[path_name] = _clean(value)
        present_paths.append(path_name)
    return {
        "declared_paths": [_path_text(path) for path in paths],
        "present_paths": present_paths,
        "sha256": _sha256(retained),
    }


def _identity(root: Mapping[str, Any]) -> dict[str, str]:
    identity = root.get("identity") if isinstance(root.get("identity"), Mapping) else {}
    assessment = (
        root.get("assessment")
        if isinstance(root.get("assessment"), Mapping)
        else {}
    )
    return {
        "repository": str(
            identity.get("repository")
            or root.get("repository")
            or assessment.get("repository")
            or ""
        ).strip(),
        "commit_sha": str(
            identity.get("commit_sha")
            or root.get("commit_sha")
            or assessment.get("commit_sha")
            or ""
        ).strip(),
        "run_id": str(
            identity.get("run_id")
            or root.get("run_id")
            or assessment.get("run_id")
            or ""
        ).strip(),
        "evidence_ledger_id": str(
            identity.get("evidence_ledger_id")
            or root.get("evidence_ledger_id")
            or assessment.get("evidence_ledger_id")
            or ""
        ).strip(),
    }


def _validation_errors(root: Mapping[str, Any], *, require_complete: bool) -> list[str]:
    errors: list[str] = []
    identity = _identity(root)
    commit_sha = identity["commit_sha"]
    if commit_sha and not _SHA40.fullmatch(commit_sha):
        errors.append("identity.commit_sha:invalid_sha40")
    if require_complete:
        for field in ("repository", "commit_sha", "run_id", "evidence_ledger_id"):
            if not identity[field]:
                errors.append(f"identity.{field}:required")

        bindings = {
            name: _binding(root, paths)
            for name, paths in _BINDING_PATHS.items()
        }
        for name in (
            "scanner_evidence",
            "candidate_evidence",
            "finding_evidence",
            "scoring_evidence",
            "stage_evidence",
            "lifecycle",
        ):
            if not bindings[name]["present_paths"]:
                errors.append(f"bindings.{name}:required")
    return sorted(set(errors))


def _technical_subject(root: Mapping[str, Any], bindings: Mapping[str, Any]) -> dict[str, Any]:
    identity = _identity(root)
    return {
        "repository": identity["repository"],
        "commit_sha": identity["commit_sha"],
        "bindings": {
            name: str(bindings[name]["sha256"])
            for name in _TECHNICAL_BINDINGS
        },
    }


def build_canonical_evidence_manifest(
    canonical: Mapping[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    """Bind one authoritative canonical JSON object without duplicating truth.

    Bindings contain source paths and digests only. Renderers and service routes
    must read the canonical JSON fields themselves; the manifest cannot supply an
    alternative score, count, finding, candidate, limitation, or lifecycle value.
    """

    root = _clean(dict(canonical))
    bindings = {
        name: _binding(root, paths)
        for name, paths in _BINDING_PATHS.items()
    }
    identity = _identity(root)
    technical_subject = _technical_subject(root, bindings)
    mutable_subject = {
        "repository": identity["repository"],
        "commit_sha": identity["commit_sha"],
        "binding_sha256": bindings["mutable_operational_evidence"]["sha256"],
    }
    errors = _validation_errors(root, require_complete=require_complete)
    return {
        "artifact_schema": VERSION,
        "authoritative_object": "canonical_json",
        "identity": identity,
        "bindings": bindings,
        "run_subject_sha256": _sha256(root),
        "technical_subject_sha256": _sha256(technical_subject),
        "mutable_operational_subject_sha256": _sha256(mutable_subject),
        "rendered_payloads_excluded_from_evidence_digest": sorted(_FORMAT_PAYLOAD_KEYS),
        "manifest_supplies_no_alternative_truth_values": True,
        "validation_status": "valid" if not errors else "invalid",
        "validation_errors": errors,
    }


def attach_canonical_evidence_manifest(
    canonical: Mapping[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    result = deepcopy(dict(canonical))
    result.pop(MANIFEST_KEY, None)
    result.pop(DIGEST_KEY, None)

    contract = deepcopy(dict(result.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "canonical_evidence_model_version": VERSION,
            "canonical_json_is_authoritative_evidence_object": True,
            "renderers_must_not_recalculate_truth": True,
            "canonical_evidence_manifest_supplies_no_alternative_values": True,
        }
    )
    result["v2_pipeline_contract"] = contract

    manifest = build_canonical_evidence_manifest(
        result,
        require_complete=require_complete,
    )
    result[MANIFEST_KEY] = manifest
    result[DIGEST_KEY] = manifest["run_subject_sha256"]
    return result


def validate_canonical_evidence_manifest(
    canonical: Mapping[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    embedded = canonical.get(MANIFEST_KEY)
    if not isinstance(embedded, Mapping):
        return {
            "status": "invalid",
            "validation_errors": ["canonical_evidence_manifest:required"],
        }

    root = deepcopy(dict(canonical))
    root.pop(MANIFEST_KEY, None)
    root.pop(DIGEST_KEY, None)
    expected = build_canonical_evidence_manifest(
        root,
        require_complete=require_complete,
    )

    for field in (
        "artifact_schema",
        "authoritative_object",
        "run_subject_sha256",
        "technical_subject_sha256",
        "mutable_operational_subject_sha256",
    ):
        if embedded.get(field) != expected.get(field):
            errors.append(f"canonical_evidence_manifest.{field}:mismatch")

    embedded_bindings = (
        embedded.get("bindings")
        if isinstance(embedded.get("bindings"), Mapping)
        else {}
    )
    for name, expected_binding in expected["bindings"].items():
        actual = (
            embedded_bindings.get(name)
            if isinstance(embedded_bindings.get(name), Mapping)
            else {}
        )
        if actual.get("sha256") != expected_binding.get("sha256"):
            errors.append(f"canonical_evidence_manifest.bindings.{name}.sha256:mismatch")
        if actual.get("present_paths") != expected_binding.get("present_paths"):
            errors.append(f"canonical_evidence_manifest.bindings.{name}.present_paths:mismatch")

    claimed = str(canonical.get(DIGEST_KEY) or "")
    if claimed != expected["run_subject_sha256"]:
        errors.append(f"{DIGEST_KEY}:mismatch")

    errors.extend(expected["validation_errors"])
    return {
        "status": "valid" if not errors else "invalid",
        "validation_errors": sorted(set(errors)),
        "run_subject_sha256": expected["run_subject_sha256"],
        "technical_subject_sha256": expected["technical_subject_sha256"],
        "mutable_operational_subject_sha256": expected[
            "mutable_operational_subject_sha256"
        ],
    }


def assert_canonical_evidence_manifest(
    canonical: Mapping[str, Any],
    *,
    require_complete: bool = False,
) -> None:
    validation = validate_canonical_evidence_manifest(
        canonical,
        require_complete=require_complete,
    )
    if validation["status"] != "valid":
        raise ValueError(
            "canonical_evidence_invalid:"
            + ",".join(validation["validation_errors"])
        )


__all__ = [
    "DIGEST_KEY",
    "MANIFEST_KEY",
    "VERSION",
    "assert_canonical_evidence_manifest",
    "attach_canonical_evidence_manifest",
    "build_canonical_evidence_manifest",
    "validate_canonical_evidence_manifest",
]
