from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.candidate-evidence-context.v1"


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _status_bool(
    value: Any,
    *,
    true_values: set[str] | frozenset[str] = frozenset(),
    false_values: set[str] | frozenset[str] = frozenset(),
) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    normalized = "_".join(_text(value, 120).casefold().replace("-", " ").split())
    if normalized in {"true", "yes", "1", "on"} | set(true_values):
        return True
    if normalized in {"false", "no", "0", "off"} | set(false_values):
        return False
    return None


def _path(finding: Mapping[str, Any]) -> str:
    source = finding.get("source") if isinstance(finding.get("source"), Mapping) else {}
    value = finding.get("dependency_path") or finding.get("source_path") or finding.get("file_path") or finding.get("filename") or finding.get("path") or source.get("path") or ""
    return str(value).replace("\\", "/").strip()


def _line(finding: Mapping[str, Any]) -> int:
    source = finding.get("source") if isinstance(finding.get("source"), Mapping) else {}
    start = finding.get("start") if isinstance(finding.get("start"), Mapping) else {}
    extra = finding.get("extra") if isinstance(finding.get("extra"), Mapping) else {}
    extra_start = extra.get("start") if isinstance(extra.get("start"), Mapping) else {}
    for value in (finding.get("line"), finding.get("line_number"), finding.get("start_line"), source.get("line"), start.get("line"), extra_start.get("line")):
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return 0


def _rule(finding: Mapping[str, Any]) -> str:
    extra = finding.get("extra") if isinstance(finding.get("extra"), Mapping) else {}
    vulnerability = finding.get("vulnerability") if isinstance(finding.get("vulnerability"), Mapping) else {}
    return _text(finding.get("rule_id") or finding.get("check_id") or finding.get("test_id") or finding.get("code") or finding.get("advisory_id") or finding.get("id") or vulnerability.get("id") or extra.get("rule_id") or extra.get("message"), 300)


def _tool_results(scan: Mapping[str, Any]) -> list[tuple[str, str, Mapping[str, Any]]]:
    output: list[tuple[str, str, Mapping[str, Any]]] = []
    values = scan.get("scanner_results") if isinstance(scan.get("scanner_results"), list) else []
    for result in values:
        if not isinstance(result, Mapping):
            continue
        scanner = _text(result.get("scanner_name") or result.get("tool") or result.get("scanner"), 120).casefold()
        category = _text(result.get("category"), 80).casefold()
        for finding in result.get("findings") or []:
            if isinstance(finding, Mapping):
                output.append((scanner, category, finding))
    return output


def _match_key(scanner: str, finding: Mapping[str, Any]) -> tuple[str, str, str, int]:
    return (scanner.casefold(), _rule(finding).casefold(), _path(finding).casefold(), _line(finding))


def _safe_context(raw: Mapping[str, Any]) -> dict[str, Any]:
    package = raw.get("package")
    package_name = _text(package.get("name") if isinstance(package, Mapping) else package, 300)
    package_version = _text(package.get("version") if isinstance(package, Mapping) else "", 120)
    package_ecosystem = _text(package.get("ecosystem") if isinstance(package, Mapping) else "", 120)
    scanned_package = _text(raw.get("osv_scanned_package") or raw.get("scanned_package_name") or package_name, 300)
    scanned_version = _text(raw.get("osv_scanned_version") or raw.get("installed_version") or raw.get("resolved_version") or package_version, 120)
    ecosystem = _text(raw.get("osv_scanned_ecosystem") or raw.get("ecosystem") or package_ecosystem, 120)
    manifest = raw.get("dependency_manifest_source") or raw.get("manifest_path") or raw.get("dependency_path")
    if isinstance(manifest, Mapping):
        manifest = manifest.get("path")
    affected = raw.get("affected")
    nested_names: list[str] = []
    if isinstance(affected, list):
        for entry in affected:
            if not isinstance(entry, Mapping):
                continue
            nested_package = entry.get("package") if isinstance(entry.get("package"), Mapping) else {}
            name = _text(nested_package.get("name"), 300)
            if name:
                nested_names.append(name)
    context: dict[str, Any] = {
        "scanned_package": {
            "name": scanned_package,
            "version": scanned_version,
            "ecosystem": ecosystem,
            "manifest_path": _text(manifest, 500),
            "lockfile_path": _text(raw.get("lockfile_path") or raw.get("lockfile"), 500),
        },
        "osv_scanned_package": scanned_package,
        "osv_scanned_version": scanned_version,
        "osv_scanned_ecosystem": ecosystem,
        "dependency_manifest_source": _text(manifest, 500),
        "dependency_scope": _text(raw.get("dependency_scope") or raw.get("scope"), 120),
        "direct_dependency": _status_bool(
            raw.get("direct_dependency") or raw.get("is_direct"),
            true_values={"direct"},
            false_values={"transitive"},
        ),
        "installed_version_affected": _status_bool(
            raw.get("installed_version_affected")
            if "installed_version_affected" in raw
            else raw.get("version_affected") or raw.get("is_affected"),
            true_values={"affected", "vulnerable", "in_range"},
            false_values={"unaffected", "not_affected", "not_vulnerable", "out_of_range", "safe"},
        ),
        "current_resolution_fixed": _status_bool(
            raw.get("current_resolution_fixed")
            if "current_resolution_fixed" in raw
            else raw.get("patched") or raw.get("fixed") or raw.get("resolved_safe"),
            true_values={"fixed", "patched", "resolved", "safe", "remediated"},
            false_values={"unfixed", "unpatched", "unresolved", "not_fixed", "not_patched"},
        ),
        "first_party_reachable": _status_bool(
            raw.get("first_party_reachable") or raw.get("reachable"),
            true_values={"reachable", "first_party_reachable"},
            false_values={"unreachable", "not_reachable"},
        ),
        "environment_relevant": _status_bool(
            raw.get("environment_relevant") or raw.get("deployment_relevant") or raw.get("runtime_relevant"),
            true_values={"relevant", "environment_relevant", "deployment_relevant", "runtime_relevant", "production"},
            false_values={"not_relevant", "environment_not_relevant", "deployment_not_relevant", "runtime_not_relevant"},
        ),
        "exploitable": _status_bool(
            raw.get("exploitable") or raw.get("exploitability"),
            true_values={"exploitable", "supportable", "realistic", "confirmed"},
            false_values={"not_exploitable", "not_supportable", "unrealistic"},
        ),
        "supported_security_boundary_crossed": _status_bool(
            raw.get("supported_security_boundary_crossed") or raw.get("boundary_crossed"),
            true_values={"crossed", "boundary_crossed", "supported_boundary_crossed"},
            false_values={"not_crossed", "same_privilege", "trusted_input_only"},
        ),
        "verified": _status_bool(
            raw.get("Verified") if "Verified" in raw else raw.get("verified") or raw.get("verification_status"),
            true_values={"verified", "live", "active", "confirmed", "valid"},
            false_values={"unverified", "not_verified", "inactive", "invalid", "revoked"},
        ),
        "synthetic": _status_bool(
            raw.get("synthetic") or raw.get("fixture") or raw.get("example_credential"),
            true_values={"synthetic", "fixture", "example", "test", "mock"},
            false_values={"real", "live", "production", "genuine"},
        ),
        "executable_code": _status_bool(
            raw.get("executable_code") or raw.get("is_executable"),
            true_values={"executable", "executable_code", "code"},
            false_values={"non_executable", "not_executable", "comment", "string", "documentation"},
        ),
        "comment_or_string": _status_bool(
            raw.get("comment_or_string") or raw.get("non_executable_text") or raw.get("documentation_only"),
            true_values={"comment", "string", "comment_or_string", "documentation", "non_executable_text"},
            false_values={"executable", "code"},
        ),
        "mitigated": _status_bool(
            raw.get("mitigated") or raw.get("existing_mitigation") or raw.get("safeguard_present"),
            true_values={"mitigated", "protected", "guarded", "safeguard_present"},
            false_values={"unmitigated", "unprotected", "unguarded", "no_mitigation"},
        ),
        "advisory_affected_packages": sorted(set(nested_names)),
        "advisory_affected_package": sorted(set(nested_names))[0] if len(set(nested_names)) == 1 else "",
    }
    return {key: value for key, value in context.items() if value not in (None, "", [], {})}


def enrich_canonical_candidate_evidence(register: Mapping[str, Any], scan: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(register))
    findings = [deepcopy(dict(item)) for item in output.get("findings") or [] if isinstance(item, Mapping)]
    indexed: dict[tuple[str, str, str, int], deque[Mapping[str, Any]]] = defaultdict(deque)
    for scanner, _category, raw in _tool_results(scan):
        indexed[_match_key(scanner, raw)].append(raw)
    enriched = 0
    unmatched = 0
    for finding in findings:
        key = (
            _text(finding.get("scanner"), 120).casefold(),
            _text(finding.get("rule_id") or finding.get("rule"), 300).casefold(),
            _path(finding).casefold(),
            _line(finding),
        )
        queue = indexed.get(key)
        if not queue:
            unmatched += 1
            continue
        raw = queue.popleft()
        context = _safe_context(raw)
        if context:
            existing = finding.get("deterministic_evidence") if isinstance(finding.get("deterministic_evidence"), Mapping) else {}
            finding["deterministic_evidence"] = {**deepcopy(dict(existing)), **context}
            finding["candidate_evidence_context_schema"] = VERSION
            enriched += 1
    output["findings"] = findings
    output["candidate_evidence_context"] = {
        "artifact_schema": VERSION,
        "status": "complete",
        "candidate_count": sum(max(1, int(item.get("occurrence_count") or 1)) for item in findings),
        "records_enriched": enriched,
        "records_without_matching_raw_context": unmatched,
        "candidate_counts_changed": False,
        "canonical_dispositions_changed": False,
        "score_effect": "none",
        "secret_values_retained": False,
        "scanned_package_identity_precedes_nested_advisory_metadata": True,
    }
    return output


__all__ = ["VERSION", "enrich_canonical_candidate_evidence"]
