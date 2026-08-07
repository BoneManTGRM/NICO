from __future__ import annotations

import base64
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

VERSION = "nico.candidate-technical-triage.v2"
ALGORITHM_VERSION = "nico.deterministic-contextual-triage.v1"
_TRIAGE_DIR = Path(__file__).resolve().parents[1] / "evidence" / "candidate-triage"
_TRIAGE_PART_GLOB = "technical-triage-9c876ba4.part-*.b64"
_PART_RE = re.compile(r"^technical-triage-9c876ba4\.part-(\d{2})\.b64$")
_SAFE_LINEAGE_STATUSES = frozenset({"carried_forward_exact", "carried_forward_location_changed"})
_ALLOWED_VERDICTS = frozenset({"confirmed", "not_actionable", "needs_review"})
_ALLOWED_PROPOSALS = frozenset({"approved_or_nonblocking", "excluded_test_only", "review_required", "verified_material"})
_ROUTING_CLASSES = frozenset({
    "CRITICAL_ATTENTION",
    "HUMAN_TECHNICAL_REVIEW",
    "AUTOMATED_TRIAGE_COMPLETE",
    "STABLE_CARRY_FORWARD",
    "QUALITY_CONTROL_ELIGIBLE",
})
_VOLATILE_EVIDENCE_KEYS = frozenset({"timestamp", "generated_at", "observed_at", "duration_ms", "run_id"})
_TEST_PARTS = frozenset({"test", "tests", "fixture", "fixtures", "example", "examples", "sample", "samples", "mock", "mocks"})


def _default_triage_parts() -> list[Path]:
    parts = sorted(_TRIAGE_DIR.glob(_TRIAGE_PART_GLOB), key=lambda path: path.name)
    if not parts:
        raise FileNotFoundError("candidate_technical_triage_parts_missing")
    indexes: list[int] = []
    for part in parts:
        match = _PART_RE.fullmatch(part.name)
        if match is None:
            raise ValueError("candidate_technical_triage_part_name_invalid")
        indexes.append(int(match.group(1)))
    if indexes != list(range(len(parts))):
        raise ValueError("candidate_technical_triage_parts_incomplete")
    return parts


def _read_encoded_source(path: Path | None = None) -> str:
    if path is not None:
        return "".join(path.read_text(encoding="utf-8").split())
    return "".join("".join(part.read_text(encoding="utf-8").split()) for part in _default_triage_parts())


def load_default_technical_triage(path: Path | None = None) -> dict[str, Any]:
    encoded = _read_encoded_source(path)
    padding = "=" * (-len(encoded) % 4)
    decoded = gzip.decompress(base64.b64decode(encoded + padding, validate=True)).decode("utf-8")
    payload = json.loads(decoded)
    if payload.get("s") != "nico.candidate-technical-triage.v1":
        raise ValueError("candidate_technical_triage_schema_invalid")
    records = payload.get("x")
    if not isinstance(records, list) or len(records) != int(payload.get("n") or -1):
        raise ValueError("candidate_technical_triage_count_invalid")
    codebook = payload.get("q")
    if not isinstance(codebook, Mapping):
        raise ValueError("candidate_technical_triage_codebook_invalid")
    if payload.get("h") != "pending":
        raise ValueError("candidate_technical_triage_human_approval_invalid")
    if payload.get("d") is not False:
        raise ValueError("candidate_technical_triage_delivery_boundary_invalid")
    if payload.get("runtime_validation_performed") is not False:
        raise ValueError("candidate_technical_triage_runtime_claim_invalid")

    seen: set[str] = set()
    verdicts: Counter[str] = Counter()
    proposals: Counter[str] = Counter()
    for raw in records:
        if not isinstance(raw, list) or len(raw) != 3:
            raise ValueError("candidate_technical_triage_record_invalid")
        candidate_id, rationale_code, rank = raw
        candidate = str(candidate_id or "").strip()
        code = str(rationale_code or "").strip()
        if not candidate or candidate in seen or code not in codebook:
            raise ValueError("candidate_technical_triage_identity_invalid")
        seen.add(candidate)
        entry = codebook[code]
        if not isinstance(entry, list) or len(entry) != 9:
            raise ValueError("candidate_technical_triage_codebook_entry_invalid")
        verdict = str(entry[0] or "")
        proposal = str(entry[2] or "")
        if verdict not in _ALLOWED_VERDICTS or proposal not in _ALLOWED_PROPOSALS:
            raise ValueError("candidate_technical_triage_disposition_invalid")
        if verdict == "needs_review" and not isinstance(rank, int):
            raise ValueError("candidate_technical_triage_rank_missing")
        if verdict != "needs_review" and rank is not None:
            raise ValueError("candidate_technical_triage_rank_unexpected")
        verdicts[verdict] += 1
        proposals[proposal] += 1
    if dict(verdicts) != {str(k): int(v) for k, v in dict(payload.get("v") or {}).items()}:
        raise ValueError("candidate_technical_triage_verdict_counts_invalid")
    if dict(proposals) != {str(k): int(v) for k, v in dict(payload.get("p") or {}).items()}:
        raise ValueError("candidate_technical_triage_proposal_counts_invalid")
    return payload


def _triage_rows(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    codebook = payload.get("q") if isinstance(payload.get("q"), Mapping) else {}
    output: dict[str, dict[str, Any]] = {}
    for raw in payload.get("x") or []:
        candidate_id, rationale_code, rank = raw
        entry = list(codebook[str(rationale_code)])
        verdict, confidence, proposal, source_type, rationale, boundary, next_step, proof_gaps, rank_basis = entry
        output[str(candidate_id)] = {
            "technical_triage_verdict": str(verdict),
            "technical_triage_confidence": str(confidence),
            "technical_triage_proposed_disposition": str(proposal),
            "technical_triage_source_type": str(source_type),
            "technical_triage_rationale_code": str(rationale_code),
            "technical_triage_rationale": str(rationale),
            "technical_triage_boundary_assessment": str(boundary),
            "technical_triage_recommended_next_step": str(next_step),
            "technical_triage_proof_gaps": deepcopy(proof_gaps if isinstance(proof_gaps, list) else []),
            "technical_triage_exploitability_stack_rank": rank,
            "technical_triage_rank_basis": str(rank_basis or ""),
        }
    return output


def _text(value: Any, limit: int = 2000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _norm(value: Any) -> str:
    return _text(value).casefold()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _count(record: Mapping[str, Any]) -> int:
    try:
        return max(1, int(record.get("occurrence_count") or 1))
    except (TypeError, ValueError):
        return 1


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _bool_value(*values: Any) -> bool | None:
    """Parse only representation-level booleans.

    Domain words such as ``synthetic``, ``fixed``, or ``verified`` are handled by
    ``_domain_bool`` so one status vocabulary cannot invert another.
    """

    true_values = {"true", "yes", "1", "on"}
    false_values = {"false", "no", "0", "off"}
    for value in values:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        normalized = _norm(value)
        if normalized in true_values:
            return True
        if normalized in false_values:
            return False
    return None


def _domain_bool(
    *values: Any,
    true_values: set[str] | frozenset[str],
    false_values: set[str] | frozenset[str],
) -> bool | None:
    for value in values:
        parsed = _bool_value(value)
        if parsed is not None:
            return parsed
        normalized = re.sub(r"[\s-]+", "_", _norm(value))
        if normalized in true_values:
            return True
        if normalized in false_values:
            return False
    return None


def _evidence_maps(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    maps: list[Mapping[str, Any]] = [record]
    for key in ("deterministic_evidence", "scanner_evidence", "dependency_context", "secret_context", "static_context", "source_context"):
        value = record.get(key)
        if isinstance(value, Mapping):
            maps.append(value)
    return maps


def _from_maps(record: Mapping[str, Any], *keys: str) -> Any:
    for source in _evidence_maps(record):
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return value
    return None


def _path(record: Mapping[str, Any]) -> str:
    source = _mapping(record.get("source"))
    return str(_first(record, "source_path", "path", "file_path", "dependency_path") or source.get("path") or "").replace("\\", "/").strip()


def _line(record: Mapping[str, Any]) -> int | None:
    value = _first(record, "line", "line_number", "start_line")
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _scope(record: Mapping[str, Any]) -> str:
    raw = _norm(_from_maps(record, "scope", "dependency_scope", "environment", "usage_scope", "target_scope"))
    path_parts = {part.casefold() for part in re.split(r"[\\/]+", _path(record)) if part}
    if raw in {"prod", "production", "runtime"}:
        return "production"
    if raw in {"test", "tests", "testing"} or path_parts & {"test", "tests", "fixture", "fixtures", "mock", "mocks"}:
        return "test"
    if raw in {"dev", "development", "devdependency", "development_only"}:
        return "development"
    if raw in {"build", "buildtime", "build_time"}:
        return "build"
    if raw in {"example", "examples", "sample", "samples", "template"} or path_parts & {"example", "examples", "sample", "samples"}:
        return "example"
    return "unknown"


def _actual_dependency(record: Mapping[str, Any]) -> dict[str, Any]:
    # Actual scanner identity has precedence. Nested advisory `affected` metadata is never consulted here.
    scanned = _from_maps(record, "scanned_package")
    if not isinstance(scanned, Mapping):
        scanned = {}
    dependency = record.get("dependency") if isinstance(record.get("dependency"), Mapping) else {}
    package = _text(
        _from_maps(record, "osv_scanned_package", "scanned_package_name", "package_name", "actual_package")
        or scanned.get("name")
        or dependency.get("name")
        or (record.get("dependency") if isinstance(record.get("dependency"), str) else ""),
        300,
    )
    version = _text(
        _from_maps(record, "osv_scanned_version", "installed_version", "resolved_version", "actual_version")
        or scanned.get("version")
        or dependency.get("version"),
        120,
    )
    ecosystem = _text(
        _from_maps(record, "osv_scanned_ecosystem", "ecosystem")
        or scanned.get("ecosystem")
        or dependency.get("ecosystem"),
        120,
    )
    manifest = _from_maps(record, "dependency_manifest_source", "manifest_path", "manifest") or scanned.get("manifest_path") or dependency.get("manifest_path")
    lockfile = _from_maps(record, "lockfile_path", "lockfile") or scanned.get("lockfile_path") or dependency.get("lockfile_path")
    relationship = _norm(_from_maps(record, "dependency_relationship", "relationship", "directness"))
    if relationship not in {"direct", "transitive"}:
        direct = _bool_value(_from_maps(record, "direct_dependency", "is_direct"))
        relationship = "direct" if direct is True else "transitive" if direct is False else "unknown"
    return {
        "package": package,
        "version": version,
        "ecosystem": ecosystem,
        "manifest_path": _text(manifest, 500),
        "lockfile_path": _text(lockfile, 500),
        "relationship": relationship,
    }


def _advisory(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "advisory_id", "rule_id", "rule") or _from_maps(record, "advisory_id", "vulnerability_id"), 300)


def _severity(record: Mapping[str, Any]) -> str:
    value = _norm(_first(record, "severity", "issue_severity", "risk_severity"))
    return value if value in {"critical", "high", "medium", "low", "info"} else "unknown"


def _confidence_rank(value: Any) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(_norm(value), 0)


def _canonical_evidence(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canonical_evidence(v) for k, v in sorted(value.items(), key=lambda item: str(item[0])) if str(k).casefold() not in _VOLATILE_EVIDENCE_KEYS}
    if isinstance(value, (list, tuple)):
        return [_canonical_evidence(item) for item in value]
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def _evidence_signature(record: Mapping[str, Any]) -> str:
    payload = {
        "scanner": _norm(record.get("scanner") or record.get("tool")),
        "category": _norm(record.get("category")),
        "rule": _norm(record.get("rule_id") or record.get("rule")),
        "path": _path(record).casefold(),
        "line": _line(record) or 0,
        "evidence": _canonical_evidence(record.get("deterministic_evidence") or record.get("scanner_evidence") or record.get("evidence") or ""),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _base_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    dependency = _actual_dependency(record)
    lineage = _text(record.get("lineage_status"), 80)
    return {
        "scanner": _text(record.get("scanner") or record.get("tool"), 120),
        "tool": _text(record.get("tool") or record.get("scanner"), 120),
        "rule": _text(record.get("rule_id") or record.get("rule"), 300),
        "advisory": _advisory(record),
        "source": _path(record),
        "path": _path(record),
        "line": _line(record),
        "dependency_package": dependency["package"],
        "dependency_version": dependency["version"],
        "dependency_ecosystem": dependency["ecosystem"],
        "manifest_path": dependency["manifest_path"],
        "lockfile_path": dependency["lockfile_path"],
        "dependency_relationship": dependency["relationship"],
        "production_test_development_scope": _scope(record),
        "lineage_status": lineage,
        "previous_candidate_identity": _text(record.get("prior_candidate_id"), 200) or None,
        "evidence_changed": lineage == "carried_forward_evidence_changed",
        "technical_triage_source": "fresh_deterministic_contextual_analysis",
        "technical_triage_model_or_version": ALGORITHM_VERSION,
        "technical_triage_timestamp": _first(record, "evidence_timestamp", "observed_at") or None,
        "evidence_used": [],
        "counterevidence": [],
        "proof_gaps": [],
    }


def _retained_canonical_fields(
    record: Mapping[str, Any],
    prior: Mapping[str, Any],
    *,
    prior_candidate_id: str,
    source_commit_sha: str,
    source_schema: str,
) -> dict[str, Any]:
    proof_gaps = deepcopy(
        prior.get("technical_triage_proof_gaps")
        if isinstance(prior.get("technical_triage_proof_gaps"), list)
        else []
    )
    evidence_used = deepcopy(
        prior.get("technical_triage_evidence_used")
        if isinstance(prior.get("technical_triage_evidence_used"), list)
        else []
    )
    if not evidence_used:
        evidence_used = [
            f"retained_candidate={prior_candidate_id}",
            f"retained_source_commit={source_commit_sha}",
        ]
    counterevidence = deepcopy(
        prior.get("technical_triage_counterevidence")
        if isinstance(prior.get("technical_triage_counterevidence"), list)
        else []
    )
    rationale_code = _text(prior.get("technical_triage_rationale_code"), 300)
    boundary = _text(prior.get("technical_triage_boundary_assessment"), 2000)
    next_step = _text(prior.get("technical_triage_recommended_next_step"), 2000)
    return {
        "rationale_code": rationale_code,
        "boundary_assessment": boundary,
        "recommended_next_step": next_step,
        "proof_gaps": proof_gaps,
        "evidence_used": evidence_used,
        "counterevidence": counterevidence,
        "reachability_assessment": _text(
            prior.get("technical_triage_reachability_assessment"), 120
        ) or "unknown",
        "exploitability_assessment": _text(
            prior.get("technical_triage_exploitability_assessment"), 120
        ) or "unknown",
        "environment_relevance": _text(
            prior.get("technical_triage_environment_relevance"), 120
        ) or "unknown",
        "technical_triage_source": "retained_prior_nico_recommendation",
        "technical_triage_source_candidate_id": prior_candidate_id,
        "technical_triage_source_commit_sha": source_commit_sha,
        "technical_triage_model_or_version": source_schema,
        "technical_triage_timestamp": prior.get("technical_triage_timestamp"),
        "technical_triage_runtime_validation_performed": False,
        "technical_review_required": prior.get("technical_triage_verdict")
        != "not_actionable",
        "evidence_changed": False,
    }


def _fresh_triage(record: Mapping[str, Any]) -> dict[str, Any]:
    result = _base_fields(record)
    category = _norm(record.get("category"))
    evidence_quality = _norm(record.get("evidence_quality"))
    scope = result["production_test_development_scope"]
    severity = _severity(record)
    reachability = _domain_bool(
        _from_maps(record, "first_party_reachable", "reachable", "reachability", "runtime_reachable"),
        true_values={"reachable", "first_party_reachable", "runtime_reachable"},
        false_values={"unreachable", "not_reachable", "not_runtime_reachable"},
    )
    exploitability = _domain_bool(
        _from_maps(record, "exploitable", "exploitability", "realistic_exploitability"),
        true_values={"exploitable", "supportable", "realistic", "confirmed"},
        false_values={"not_exploitable", "not_supportable", "unrealistic"},
    )
    environment_relevant = _domain_bool(
        _from_maps(record, "environment_relevant", "deployment_relevant", "runtime_relevant"),
        true_values={"relevant", "environment_relevant", "deployment_relevant", "runtime_relevant", "production"},
        false_values={"not_relevant", "environment_not_relevant", "deployment_not_relevant", "runtime_not_relevant"},
    )
    boundary_crossed = _domain_bool(
        _from_maps(record, "supported_security_boundary_crossed", "boundary_crossed", "security_boundary_crossed"),
        true_values={"crossed", "boundary_crossed", "supported_boundary_crossed"},
        false_values={"not_crossed", "same_privilege", "trusted_input_only"},
    )
    result["reachability_assessment"] = "reachable" if reachability is True else "unreachable" if reachability is False else "unknown"
    result["exploitability_assessment"] = "supportable" if exploitability is True else "not_supportable" if exploitability is False else "unknown"
    result["environment_relevance"] = "relevant" if environment_relevant is True else "not_relevant" if environment_relevant is False else "unknown"

    verdict = "needs_review"
    confidence = "low"
    code = "insufficient_context"
    rationale = "The retained evidence is insufficient for a defensible automated technical determination."
    boundary = "Automated technical recommendation only; authorized human disposition remains pending."
    next_step = "Review the exact scanner evidence and resolve the listed proof gaps."
    used: list[str] = []
    counter: list[str] = []
    gaps: list[str] = []

    if evidence_quality in {"count_only", "payload_without_source"}:
        gaps.extend(["raw_candidate_payload", "exact_source_context"])
        code = "count_or_payload_only_evidence"
    elif category == "dependency":
        dep = _actual_dependency(record)
        used.extend(item for item in [f"package={dep['package']}" if dep["package"] else "", f"version={dep['version']}" if dep["version"] else "", f"ecosystem={dep['ecosystem']}" if dep["ecosystem"] else "", f"manifest={dep['manifest_path']}" if dep["manifest_path"] else ""] if item)
        affected = _domain_bool(
            _from_maps(record, "installed_version_affected", "version_affected", "is_affected", "vulnerable"),
            true_values={"affected", "vulnerable", "in_range"},
            false_values={"unaffected", "not_affected", "not_vulnerable", "out_of_range", "safe"},
        )
        fixed = _domain_bool(
            _from_maps(record, "current_resolution_fixed", "resolved_safe", "patched", "fixed"),
            true_values={"fixed", "patched", "resolved", "safe", "remediated"},
            false_values={"unfixed", "unpatched", "unresolved", "not_fixed", "not_patched"},
        )
        if not dep["package"]:
            gaps.append("actual_scanned_package")
        if not dep["version"]:
            gaps.append("actual_resolved_or_installed_version")
        if not dep["ecosystem"]:
            gaps.append("dependency_ecosystem")
        nested = _from_maps(
            record,
            "advisory_affected_package",
            "nested_affected_package",
            "advisory_affected_packages",
        )
        nested_values = nested if isinstance(nested, list) else [nested]
        for nested_value in nested_values:
            if nested_value and _norm(nested_value) != _norm(dep["package"]):
                counter.append(
                    f"nested_advisory_package_ignored={_text(nested_value, 300)}"
                )
        if gaps:
            code = "dependency_identity_incomplete"
            rationale = "Dependency materiality cannot be determined without the actual scanned package, resolved version, and ecosystem."
            next_step = "Resolve scanner package identity from the authoritative manifest or lockfile, then evaluate advisory range and reachability."
        elif fixed is True or affected is False:
            verdict, confidence, code = "not_actionable", "high", "dependency_resolution_not_affected"
            rationale = "The actual scanned package and resolved version are deterministically outside the affected state."
            next_step = "Retain the package-resolution evidence for quality-control sampling."
        elif affected is True and scope in {"test", "development", "build", "example"} and reachability is False:
            verdict, confidence, code = "not_actionable", "high", "dependency_nonproduction_unreachable"
            rationale = "The affected dependency is deterministically non-production and unreachable from first-party runtime code."
            next_step = "Retain scope and reachability evidence for quality-control sampling."
        elif (
            affected is True
            and reachability is True
            and scope == "production"
            and environment_relevant is True
        ):
            verdict, confidence, code = "confirmed", "high", "dependency_affected_reachable_production"
            rationale = "The actual installed package is affected, production-relevant, environment-relevant, and reachable from first-party code."
            boundary = "A shipped production dependency path is supported by current evidence; authorized human disposition remains pending."
            next_step = "Prioritize upgrade or mitigation and obtain explicit human disposition and residual-risk assessment."
        else:
            if affected is None:
                gaps.append("affected_range_resolution")
            if reachability is None:
                gaps.append("first_party_reachability")
            if scope == "unknown":
                gaps.append("production_scope")
            if environment_relevant is None:
                gaps.append("environment_relevance")
            code = "dependency_reachability_or_scope_unresolved"
            rationale = "Package identity is known, but affected-range, reachability, deployment relevance, or environment relevance remains unresolved."
            next_step = "Resolve installed-version affectedness, first-party reachability, production scope, and environment relevance."
    elif category == "secret":
        verified = _domain_bool(
            _from_maps(record, "verified", "credential_verified", "verification_status", "live_credential"),
            true_values={"verified", "live", "active", "confirmed", "valid"},
            false_values={"unverified", "not_verified", "inactive", "invalid", "revoked"},
        )
        synthetic = _domain_bool(
            _from_maps(record, "synthetic", "fixture", "example_credential", "test_credential"),
            true_values={"synthetic", "fixture", "example", "test", "mock"},
            false_values={"real", "live", "production", "genuine"},
        )
        used.extend([f"scanner_verification={verified}", f"scope={scope}"])
        if verified is True:
            verdict, confidence, code = "confirmed", "high", "verified_secret"
            rationale = "The scanner evidence identifies a verified credential. Fixture-like appearance cannot suppress verified secret evidence."
            next_step = "Revoke or rotate the credential, investigate repository history, and obtain explicit human disposition."
            if synthetic is True or scope in {"test", "example"}:
                counter.append("fixture_or_example_context_does_not_override_verification")
        elif verified is False and synthetic is True and scope in {"test", "example"}:
            verdict, confidence, code = "not_actionable", "high", "synthetic_nonproduction_secret_fixture"
            rationale = "The credential is explicitly unverified, synthetic, and confined to a non-production fixture or example boundary."
            next_step = "Retain verification and fixture-boundary evidence for quality-control sampling."
        else:
            if verified is None:
                gaps.append("scanner_credential_verification")
            if synthetic is None:
                gaps.append("synthetic_or_real_credential_determination")
            if scope == "unknown":
                gaps.append("production_boundary")
            code = "secret_authenticity_or_boundary_unresolved"
            rationale = "Credential authenticity or its production boundary cannot be defensibly resolved from retained evidence."
            next_step = "Verify the credential safely, inspect repository history, and establish fixture or production boundaries."
    elif category == "static":
        executable = _domain_bool(
            _from_maps(record, "executable_code", "is_executable", "source_executable"),
            true_values={"executable", "executable_code", "code"},
            false_values={"non_executable", "not_executable", "comment", "string", "documentation"},
        )
        comment_or_string = _domain_bool(
            _from_maps(record, "comment_or_string", "non_executable_text", "documentation_only"),
            true_values={"comment", "string", "comment_or_string", "documentation", "non_executable_text"},
            false_values={"executable", "code"},
        )
        mitigated = _domain_bool(
            _from_maps(record, "mitigated", "existing_mitigation", "safeguard_present"),
            true_values={"mitigated", "protected", "guarded", "safeguard_present"},
            false_values={"unmitigated", "unprotected", "unguarded", "no_mitigation"},
        )
        used.extend([
            f"executable={executable}",
            f"scope={scope}",
            f"reachable={reachability}",
            f"mitigated={mitigated}",
            f"exploitable={exploitability}",
            f"environment_relevant={environment_relevant}",
            f"boundary_crossed={boundary_crossed}",
        ])
        if executable is False and (comment_or_string is True or scope in {"test", "example"}):
            verdict, confidence, code = "not_actionable", "high", "static_nonexecutable_noise"
            rationale = "The rule hit is confined to non-executable text or a non-production example/test boundary."
            next_step = "Retain source-context evidence for quality-control sampling."
        elif (
            executable is True
            and scope == "production"
            and reachability is True
            and mitigated is False
            and exploitability is True
            and environment_relevant is True
            and boundary_crossed is True
            and severity in {"critical", "high"}
        ):
            verdict, confidence, code = "confirmed", "high", "static_reachable_unmitigated_production"
            rationale = "Executable production code is reachable, realistically exploitable, environment-relevant, unmitigated, and crosses a supported security boundary."
            boundary = "Current static evidence supports a shipped production path crossing a supported security boundary; authorized human disposition remains pending."
            next_step = "Review the exact data flow, remediate, test the fix, and obtain explicit human disposition."
        else:
            if executable is None:
                gaps.append("executable_source_confirmation")
            if reachability is None:
                gaps.append("first_party_reachability")
            if scope == "unknown":
                gaps.append("production_scope")
            if mitigated is None:
                gaps.append("existing_mitigation_assessment")
            if exploitability is None:
                gaps.append("realistic_exploitability")
            if environment_relevant is None:
                gaps.append("environment_relevance")
            if boundary_crossed is None:
                gaps.append("supported_security_boundary")
            code = "static_exploitability_unresolved"
            rationale = "A generic static-analysis rule hit is not enough to confirm a vulnerability without executable context, reachability, scope, mitigation, realistic exploitability, environment relevance, and supported-boundary evidence."
            next_step = "Inspect the exact source and data flow, then resolve reachability, production scope, mitigations, exploitability, environment relevance, and the supported security boundary."
    else:
        gaps.extend(["supported_scanner_category", "category_specific_evidence"])
        code = "unsupported_or_unknown_scanner_category"
        next_step = "Route to human technical review with the complete raw scanner payload."

    if verdict == "confirmed" and severity in {"critical", "high"}:
        exploitability_assessment = "evidence_backed_material_candidate"
    else:
        exploitability_assessment = result["exploitability_assessment"]
    proposal = "verified_material" if verdict == "confirmed" else "approved_or_nonblocking" if verdict == "not_actionable" else "review_required"
    result.update({
        "technical_triage_status": "fresh_proposal",
        "technical_triage_verdict": verdict,
        "technical_triage_confidence": confidence,
        "technical_triage_rationale": rationale,
        "rationale_code": code,
        "technical_triage_rationale_code": code,
        "technical_triage_proposed_disposition": proposal,
        "technical_triage_source_type": "deterministic_contextual_analysis",
        "boundary_assessment": boundary,
        "technical_triage_boundary_assessment": boundary,
        "recommended_next_step": next_step,
        "technical_triage_recommended_next_step": next_step,
        "proof_gaps": sorted(set(gaps)),
        "technical_triage_proof_gaps": sorted(set(gaps)),
        "evidence_used": sorted(set(item for item in used if item and not item.endswith("=None"))),
        "counterevidence": sorted(set(counter)),
        "exploitability_assessment": exploitability_assessment,
        "technical_review_required": verdict != "not_actionable",
        "technical_triage_runtime_validation_performed": False,
    })
    return result


def _source_pattern(path: str) -> str:
    normalized = path.replace("\\", "/").casefold()
    normalized = re.sub(r"\d+", "#", normalized)
    parts = normalized.split("/")
    if len(parts) > 3:
        parts = parts[-3:]
    return "/".join(parts)


def _cluster_evidence_signature(record: Mapping[str, Any]) -> str:
    dependency = _actual_dependency(record)
    payload = {
        "scanner": _norm(record.get("scanner") or record.get("tool")),
        "category": _norm(record.get("category")),
        "rule": _norm(record.get("rule_id") or record.get("rule") or record.get("advisory_id")),
        "dependency": dependency,
        "scope": _scope(record),
        "verdict": _norm(record.get("technical_triage_verdict")),
        "confidence": _norm(record.get("technical_triage_confidence")),
        "rationale_code": _norm(
            record.get("technical_triage_rationale_code")
            or record.get("rationale_code")
        ),
        "reachability": _norm(record.get("reachability_assessment")),
        "exploitability": _norm(record.get("exploitability_assessment")),
        "environment_relevance": _norm(record.get("environment_relevance")),
        "proof_gaps": sorted(
            _text(item, 300)
            for item in (record.get("technical_triage_proof_gaps") or [])
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _cluster_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    dep = _actual_dependency(record)
    return (
        _norm(record.get("scanner") or record.get("tool")),
        _norm(record.get("category")),
        _norm(record.get("rule_id") or record.get("rule") or record.get("advisory_id")),
        dep["package"].casefold(),
        dep["version"].casefold(),
        dep["ecosystem"].casefold(),
        _norm(record.get("technical_triage_rationale_code") or record.get("rationale_code")),
        _scope(record),
        _source_pattern(_path(record)),
    )


def _cluster_candidates(records: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_cluster_key(record)].append(record)
    for key, members in grouped.items():
        digest = hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()[:20].upper()
        cluster_id = f"NICO-CLUSTER-{digest}"
        representative = min((_text(item.get("candidate_id") or item.get("finding_id"), 300) for item in members), default="")
        verdicts = {_text(item.get("technical_triage_verdict"), 80) for item in members}
        evidence_signatures = {_cluster_evidence_signature(item) for item in members}
        homogeneous_verdict = len(verdicts) == 1
        homogeneous_evidence = len(evidence_signatures) == 1
        cluster_size = sum(_count(item) for item in members)
        eligible = (
            cluster_size > 1
            and homogeneous_verdict
            and homogeneous_evidence
            and verdicts == {"not_actionable"}
            and all(_confidence_rank(item.get("technical_triage_confidence")) >= 3 for item in members)
            and all(not item.get("technical_triage_proof_gaps") for item in members)
        )
        reason = "same scanner/rule/root-cause/package/scope/source-pattern"
        for item in members:
            item.update({
                "cluster_id": cluster_id,
                "cluster_reason": reason,
                "cluster_size": cluster_size,
                "representative_candidate_id": representative,
                "homogeneous_evidence": homogeneous_evidence,
                "homogeneous_verdict": homogeneous_verdict,
                "grouped_review_eligible": eligible,
            })


def _route(record: Mapping[str, Any]) -> str:
    verdict = _norm(record.get("technical_triage_verdict"))
    severity = _severity(record)
    confidence = _norm(record.get("technical_triage_confidence"))
    gaps = record.get("technical_triage_proof_gaps") or []
    source = _norm(record.get("technical_triage_source"))
    if verdict == "confirmed" and severity in {"critical", "high"}:
        return "CRITICAL_ATTENTION"
    if verdict in {"confirmed", "needs_review"} or confidence == "low" or gaps:
        return "HUMAN_TECHNICAL_REVIEW"
    if source == "retained_prior_nico_recommendation":
        return "STABLE_CARRY_FORWARD"
    if verdict == "not_actionable" and confidence == "high":
        return "QUALITY_CONTROL_ELIGIBLE"
    return "AUTOMATED_TRIAGE_COMPLETE"


def _metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = sum(_count(item) for item in records)
    completed = sum(_count(item) for item in records if _norm(item.get("technical_triage_verdict")) in _ALLOWED_VERDICTS)
    counts = Counter()
    for item in records:
        count = _count(item)
        verdict = _norm(item.get("technical_triage_verdict"))
        if verdict in _ALLOWED_VERDICTS:
            counts[verdict] += count
    cluster_ids = {_text(item.get("cluster_id")) for item in records if item.get("cluster_id")}
    individual = sum(_count(item) for item in records if item.get("review_routing_class") in {"CRITICAL_ATTENTION", "HUMAN_TECHNICAL_REVIEW"})
    grouped = sum(_count(item) for item in records if item.get("grouped_review_eligible") is True)
    qc = sum(_count(item) for item in records if item.get("review_routing_class") == "QUALITY_CONTROL_ELIGIBLE")
    exact = sum(_count(item) for item in records if item.get("lineage_status") == "carried_forward_exact" and item.get("technical_triage_source") == "retained_prior_nico_recommendation")
    location = sum(_count(item) for item in records if item.get("lineage_status") == "carried_forward_location_changed")
    stable = sum(_count(item) for item in records if item.get("review_routing_class") == "STABLE_CARRY_FORWARD")
    new = sum(_count(item) for item in records if item.get("lineage_status") == "newly_observed")
    changed = sum(_count(item) for item in records if item.get("lineage_status") == "carried_forward_evidence_changed")
    return {
        "total_candidates": total,
        "technical_triage_completed": completed,
        "technical_triage_pending": total - completed,
        "technical_triage_coverage_pct": round(completed * 100 / total, 2) if total else 100.0,
        "not_actionable_count": counts["not_actionable"],
        "needs_review_count": counts["needs_review"],
        "confirmed_count": counts["confirmed"],
        "new_candidate_count": new,
        "evidence_changed_count": changed,
        "exact_carry_forward_count": exact,
        "location_changed_count": location,
        "cluster_count": len(cluster_ids),
        "candidates_requiring_individual_human_attention": individual,
        "candidates_eligible_for_grouped_review": grouped,
        "quality_control_sample_pool": qc,
        "stable_carry_forward_count": stable,
    }


def apply_candidate_technical_triage(register: Mapping[str, Any], *, triage: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Attach safe retained proposals and freshly triage all other candidates.

    Technical verdicts are proposal-only. This function never creates human disposition,
    reviewer identity, risk acceptance, approval, or client-delivery authorization.
    """
    output = deepcopy(dict(register))
    current = [deepcopy(dict(item)) for item in output.get("findings") or [] if isinstance(item, Mapping)]
    indexed: dict[str, dict[str, Any]] = {}
    source: dict[str, Any] = {}
    artifact_error: str | None = None
    try:
        source = dict(triage or load_default_technical_triage())
        indexed = _triage_rows(source)
    except Exception as exc:  # retained artifact failure must not block fresh fail-safe triage
        artifact_error = type(exc).__name__

    imported = 0
    fresh = 0
    for record in current:
        lineage_status = _text(record.get("lineage_status"), 80)
        prior_candidate_id = _text(record.get("prior_candidate_id"), 300)
        record["technical_triage_human_approval_status"] = "pending"
        record["technical_triage_human_approval_carried_forward"] = False
        record["technical_triage_client_delivery_allowed"] = False
        record["human_approval_status"] = record.get("human_approval_status") or "pending"
        prior = indexed.get(prior_candidate_id) if lineage_status in _SAFE_LINEAGE_STATUSES and prior_candidate_id else None
        if prior is not None:
            base = _base_fields(record)
            record.update(base)
            record.update(deepcopy(prior))
            record.update(
                _retained_canonical_fields(
                    record,
                    prior,
                    prior_candidate_id=prior_candidate_id,
                    source_commit_sha=str(source.get("c") or ""),
                    source_schema=str(
                        source.get("s") or "nico.candidate-technical-triage.v1"
                    ),
                )
            )
            record["technical_triage_status"] = "imported_proposal"
            imported += _count(record)
        else:
            record.update(_fresh_triage(record))
            fresh += _count(record)

    _cluster_candidates(current)
    for record in current:
        route = _route(record)
        if route not in _ROUTING_CLASSES:
            raise AssertionError("candidate_triage_routing_invalid")
        record["review_routing_class"] = route
        record["review_routing_is_human_decision"] = False

    metrics = _metrics(current)
    verdict_counts = {
        "confirmed": metrics["confirmed_count"],
        "needs_review": metrics["needs_review_count"],
        "not_actionable": metrics["not_actionable_count"],
    }
    output["findings"] = current
    output["technical_triage"] = {
        "artifact_schema": VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "status": "complete",
        "technical_triage_available": True,
        "retained_artifact_status": "available" if artifact_error is None else "unavailable",
        "retained_artifact_error": artifact_error,
        "source_schema": str(source.get("s") or source.get("source_schema") or ""),
        "source_target_commit_sha": str(source.get("c") or ""),
        "source_candidate_count": int(source.get("n") or 0),
        "imported_candidate_count": imported,
        "fresh_technical_triage_completed": fresh,
        "fresh_technical_triage_required": metrics["new_candidate_count"] + metrics["evidence_changed_count"],
        "current_evidence_review_required": sum(
            _count(item)
            for item in current
            if item.get("technical_triage_source")
            == "fresh_deterministic_contextual_analysis"
            and item.get("review_routing_class")
            in {"CRITICAL_ATTENTION", "HUMAN_TECHNICAL_REVIEW"}
        ),
        "verdict_counts": verdict_counts,
        "safe_lineage_statuses": sorted(_SAFE_LINEAGE_STATUSES),
        "evidence_changed_candidates_inherit_prior_triage": False,
        "new_candidates_inherit_prior_triage": False,
        "runtime_validation_performed": False,
        "human_approval_status": "pending",
        "human_approval_carried_forward": False,
        "human_disposition_created": False,
        "reviewer_identity_created": False,
        "risk_acceptance_created": False,
        "disposition_authority": "proposal_only_pending_authorized_human_review",
        "client_delivery_allowed": False,
        "score_effect": "none_canonical_dispositions_and_totals_unchanged",
        "workload_metrics": deepcopy(metrics),
        **metrics,
    }
    output["canonical_digest_sha256"] = hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return output


__all__ = ["VERSION", "ALGORITHM_VERSION", "apply_candidate_technical_triage", "load_default_technical_triage"]
