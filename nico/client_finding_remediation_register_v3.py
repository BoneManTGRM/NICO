from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico import client_finding_remediation_register_v2 as legacy
from nico.client_assessment_truth_v3 import (
    executable_tls_evidence,
    normalize_client_assessment_truth,
    normalize_repository_path,
    scanner_configuration_error,
)

VERSION = "nico.client-finding-remediation-register.v5"
_GENERIC_EXIT_CRITERION = (
    "All listed verification requirements pass on the exact remediation commit, "
    "the exact-SHA rerun no longer reports the condition as unresolved material risk, "
    "and no new material regression is introduced."
)
_SKIP_KEYS = {
    "pdf_base64",
    "markdown",
    "html",
    "raw_output",
    "stdout",
    "stderr",
    "secret",
    "match",
}


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _text(value).casefold().replace("_", "-")).strip("-")


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return int(value) if str(value or "").isdigit() else None


def _dedupe(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    output: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _family(item: Mapping[str, Any]) -> str:
    rule = _token(item.get("rule_id") or item.get("finding_family"))
    combined = " ".join(
        _text(item.get(key), 2000)
        for key in (
            "title",
            "problematic_code",
            "observed_evidence",
            "interpretation",
            "category",
        )
    ).casefold()
    if scanner_configuration_error(item):
        return "scanner_configuration_error"
    if "tls" in combined and any(token in combined for token in ("verify", "certificate", "cert_none", "rejectunauthorized")):
        return "tls_verify_disabled"
    if rule and "complex" in rule:
        return "complexity_hotspot"
    if any(token in combined for token in ("cyclomatic_complexity", "high-complexity", "concentrated branching", "complexity hotspot")):
        return "complexity_hotspot"
    advisory = re.search(r"\b(?:GHSA-[0-9A-Za-z-]+|CVE-\d{4}-\d+)\b", combined, re.IGNORECASE)
    if advisory:
        return f"dependency_vulnerability:{advisory.group(0).casefold()}"
    if _token(item.get("category")) == "dependency" or "dependency vulnerability" in combined:
        return "dependency_vulnerability"
    if _token(item.get("category")) == "secret" or "secret candidate" in combined:
        return "secret_candidate"
    if any(token in combined for token in ("workflow reliability", "historical ci", "non-success runs", "ci/cd")):
        return "ci_reliability"
    return rule or _token(item.get("category") or item.get("title") or item.get("finding_id")) or "technical_finding"


def _parse_location(item: Mapping[str, Any]) -> tuple[str, int | None, int | None, int | None]:
    path = normalize_repository_path(item.get("path") or item.get("file_path") or "")
    line = _int(item.get("line") or item.get("start_line"))
    column = _int(item.get("column") or item.get("start_column"))
    end_line = _int(item.get("end_line"))
    location = normalize_repository_path(item.get("location") or "")
    if location and location not in {"location-not-retained", "not retained", "unknown"}:
        match = re.match(r"^(.*?):(\d+)(?:-(\d+))?(?::(\d+))?$", location)
        if match:
            path = normalize_repository_path(match.group(1))
            line = line or int(match.group(2))
            end_line = end_line or (int(match.group(3)) if match.group(3) else None)
            column = column or (int(match.group(4)) if match.group(4) else None)
        elif not path:
            path = location
    return path, line, column, end_line


def _location(path: str, line: int | None, column: int | None, end_line: int | None) -> str:
    if not path:
        return ""
    if line is None:
        return path
    suffix = f":{line}"
    if end_line and end_line != line:
        suffix += f"-{end_line}"
    if column:
        suffix += f":{column}"
    return f"{path}{suffix}"


def _iter_mappings(value: Any, *, depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if depth > 10:
        return
    if isinstance(value, Mapping):
        yield value
        for key, child in value.items():
            if str(key).casefold() in _SKIP_KEYS:
                continue
            yield from _iter_mappings(child, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_mappings(child, depth=depth + 1)


def _source_context_index(canonical: Mapping[str, Any]) -> dict[tuple[str, int], dict[str, str]]:
    index: dict[tuple[str, int], dict[str, str]] = {}
    for item in _iter_mappings(canonical):
        path, line, _, _ = _parse_location(item)
        if not path or line is None:
            continue
        symbol = _text(
            item.get("symbol")
            or item.get("function")
            or item.get("component")
            or item.get("method_name")
            or (item.get("name") if item.get("cyclomatic_complexity") is not None else ""),
            300,
        )
        rule = _text(
            item.get("rule_id")
            or item.get("check_id")
            or item.get("test_id")
            or item.get("finding_family"),
            240,
        )
        excerpt = item.get("source_excerpt") or item.get("code_excerpt") or item.get("snippet") or item.get("line_text") or item.get("source_line")
        if isinstance(excerpt, (list, tuple)):
            excerpt = "\n".join(_text(part, 400) for part in excerpt[:9])
        candidate = {
            "symbol": symbol,
            "rule_id": rule,
            "source_excerpt": _text(excerpt, 1800),
        }
        key = (path.casefold(), line)
        current = index.get(key, {})
        for field, value in candidate.items():
            if value and not current.get(field):
                current[field] = value
        index[key] = current
    return index


def _stable_id(repository: str, path: str, line: int | None, family: str, title: str) -> str:
    identity = "|".join(
        (
            repository.casefold(),
            path.casefold(),
            str(line or 0),
            family.casefold(),
            "" if path and line else _token(title),
        )
    )
    return "NICO-FINDING-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()


def _specific_correction(item: Mapping[str, Any], family: str) -> str:
    path = _text(item.get("path")).casefold()
    symbol = _text(item.get("symbol")) or "the identified unit"
    if family == "complexity_hotspot":
        if path.endswith((".tsx", ".jsx")):
            return (
                f"Extract state transitions, data loading, and side-effect orchestration from `{symbol}` into typed hooks or services; "
                "split independent rendering branches into bounded child components; add characterization and Playwright coverage; "
                "then enforce cyclomatic complexity at or below 30 for the durable source anchor."
            )
        if "report" in path or "spanish" in path:
            return (
                f"Separate canonical-data preparation, translation selection, layout construction, and artifact validation in `{symbol}`; "
                "retain snapshot-based report fixtures and cross-format truth tests; target complexity at or below 30."
            )
        if any(token in path for token in ("scanner", "evidence", "snapshot")):
            return (
                f"Split collection, normalization, classification, and serialization responsibilities in `{symbol}` into bounded pure helpers; "
                "preserve exact-SHA evidence fixtures and add regression tests for failure and partial-evidence paths."
            )
        if path.startswith("scripts/") or symbol == "main":
            return (
                f"Separate argument parsing, orchestration, evidence assembly, and artifact writing in `{symbol}`; "
                "add command-level characterization tests and enforce the approved complexity threshold."
            )
        return (
            f"Decompose `{symbol}` around cohesive branch groups, preserve behavior with characterization tests, "
            "and enforce cyclomatic complexity at or below 30 on the exact remediation commit."
        )
    if family == "tls_verify_disabled":
        return (
            "Verify that the retained source contains an executable insecure TLS call. If confirmed, restore certificate and hostname verification, "
            "remove insecure transport exceptions, add a negative regression test, and rerun exact-SHA security analysis."
        )
    if family.startswith("dependency_vulnerability"):
        return (
            "Confirm the affected package, installed version, dependency path, fixed version, and runtime reachability; apply the smallest supported "
            "upgrade or constraint, regenerate the relevant lockfile, and rerun every applicable dependency analyzer."
        )
    if family == "secret_candidate":
        return (
            "Review only the redacted candidate metadata, confirm whether a live credential exists, rotate confirmed credentials, remove reachable "
            "history when required, and rerun both history-aware analyzers without exposing secret material."
        )
    if family == "ci_reliability":
        return (
            "Classify every non-success run by cause, separate expected cancellation from genuine failure, assign owners to recurring classes, "
            "and require two consecutive acceptance windows without unexplained recurring failures."
        )
    return _text(item.get("recommended_correction")) or (
        "Review the retained evidence, apply the smallest bounded correction, run targeted and full regression checks, "
        "and rerun NICO against the exact remediation commit."
    )


def _quality(item: Mapping[str, Any]) -> tuple[int, ...]:
    source = _text(item.get("record_source")).casefold()
    return (
        int(bool(item.get("artifact_hash"))),
        int(bool(item.get("source_excerpt"))),
        int(bool(item.get("symbol"))),
        int(bool(item.get("rule_id"))),
        int(item.get("exact_commit_match") is True),
        int(source == "canonical_finding"),
        len(_text(item.get("observed_evidence"))),
    )


def _normalize_record(
    raw: Mapping[str, Any],
    *,
    repository: str,
    context: Mapping[tuple[str, int], Mapping[str, str]],
) -> dict[str, Any]:
    item = deepcopy(dict(raw))
    path, line, column, end_line = _parse_location(item)
    family = _family(item)
    source = context.get((path.casefold(), int(line or 0)), {}) if path and line else {}
    symbol = _text(item.get("symbol")) or _text(source.get("symbol"))
    rule = _text(item.get("rule_id")) or _text(source.get("rule_id")) or family
    excerpt = _text(item.get("source_excerpt"), 1800) or _text(source.get("source_excerpt"), 1800)
    original_id = _text(item.get("finding_id"))

    item.update(
        {
            "path": path,
            "line": line,
            "column": column,
            "end_line": end_line,
            "location": _location(path, line, column, end_line),
            "symbol": symbol,
            "rule_id": rule,
            "finding_family": family,
            "source_excerpt": excerpt,
            "repository_relative_path": True,
            "finding_id": _stable_id(repository, path, line, family, _text(item.get("title"))),
            "finding_aliases": _dedupe([*list(item.get("finding_aliases") or []), original_id]),
        }
    )

    if family == "complexity_hotspot":
        item["evidence_source"] = _text(item.get("evidence_source")) or "complexity-evidence"
        item["rule_id"] = "complexity_hotspot"
        item["problematic_code"] = _text(item.get("problematic_code")) or (
            f"Cyclomatic complexity is concentrated in `{symbol or 'the identified unit'}` at the exact source anchor."
        )
    elif _text(item.get("evidence_source")) in {"", "unknown"}:
        item["evidence_source"] = "canonical-evidence"

    item["recommended_correction"] = _specific_correction(item, family)
    item["verification"] = _dedupe(item.get("verification") or [])
    exits = [value for value in _dedupe(item.get("exit_criteria") or []) if value.casefold() not in {v.casefold() for v in item["verification"]}]
    item["exit_criteria"] = exits or [_GENERIC_EXIT_CRITERION]
    item["verification_and_exit_criteria_distinct"] = True
    item["client_actionable"] = item.get("client_actionable") is not False

    if family == "scanner_configuration_error" or scanner_configuration_error(item):
        item["client_actionable"] = False
        item["suppression_reason"] = "scanner_configuration_error_is_not_source_code_evidence"

    if family == "tls_verify_disabled" and not executable_tls_evidence(item):
        item["client_actionable"] = False
        item["priority"] = "P2"
        item["status"] = "review_required"
        item["title"] = "Unverified TLS pattern candidate"
        item["interpretation"] = (
            "The retained pattern did not include executable insecure-TLS source evidence and was not promoted to a confirmed code finding."
        )
        item["business_impact"] = (
            "No production TLS defect is claimed. Human review is required only to determine whether the pattern came from executable code, "
            "a detector definition, documentation, or test data."
        )
        item["recommended_correction"] = (
            "Inspect the evidence anchor and retain a bounded executable source excerpt before proposing a code change. "
            "Close as a false positive when the token appears only in tests, documentation, detector definitions, or report text."
        )
        item["evidence_anchor"] = item.get("location")
        item["path"] = ""
        item["line"] = None
        item["column"] = None
        item["end_line"] = None
        item["location"] = ""
        item["promotion_blocked_reason"] = "executable_tls_source_evidence_not_retained"
    return item


def _record_key(item: Mapping[str, Any]) -> tuple[str, str, int, str]:
    family = _text(item.get("finding_family")) or _family(item)
    path = normalize_repository_path(item.get("path")).casefold()
    line = int(item.get("line") or 0)
    if item.get("client_actionable") is not False and path and line:
        return "code", path, line, family
    operational_identity = _token(
        item.get("advisory_id")
        or item.get("finding_id")
        or item.get("title")
        or item.get("observed_evidence")
    )
    return "operational", _token(item.get("category")), 0, f"{family}:{operational_identity}"


def _merge(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    preferred, other = (right, left) if _quality(right) > _quality(left) else (left, right)
    result = deepcopy(dict(preferred))
    for field, value in other.items():
        if result.get(field) in (None, "", [], {}):
            result[field] = deepcopy(value)
    result["finding_aliases"] = _dedupe(
        [
            *list(result.get("finding_aliases") or []),
            result.get("finding_id"),
            *list(other.get("finding_aliases") or []),
            other.get("finding_id"),
        ]
    )
    result["record_sources"] = _dedupe(
        [
            *list(result.get("record_sources") or []),
            result.get("record_source"),
            *list(other.get("record_sources") or []),
            other.get("record_source"),
        ]
    )
    result["verification"] = _dedupe(
        [*list(result.get("verification") or []), *list(other.get("verification") or [])]
    )
    exits = _dedupe(
        [*list(result.get("exit_criteria") or []), *list(other.get("exit_criteria") or [])]
    )
    verification_keys = {value.casefold() for value in result["verification"]}
    result["exit_criteria"] = [value for value in exits if value.casefold() not in verification_keys] or [_GENERIC_EXIT_CRITERION]
    result["duplicate_sources_consolidated"] = True
    result["verification_and_exit_criteria_distinct"] = True
    return result


def _consolidate(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    order: list[tuple[str, str, int, str]] = []
    for item in values:
        key = _record_key(item)
        if key not in selected:
            selected[key] = deepcopy(dict(item))
            order.append(key)
        else:
            selected[key] = _merge(selected[key], item)
    return [selected[key] for key in order]


def normalize_finding_remediation_register(
    register: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(register))
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    repository = _text(identity.get("repository") or canonical.get("repository"))
    context = _source_context_index(canonical)

    raw_code = [item for item in result.get("code_findings") or [] if isinstance(item, Mapping)]
    raw_operational = [item for item in result.get("operational_findings") or [] if isinstance(item, Mapping)]
    raw_excluded = [item for item in result.get("excluded_non_production_findings") or [] if isinstance(item, Mapping)]
    raw_count = len(raw_code) + len(raw_operational) + len(raw_excluded)

    normalized = [
        _normalize_record(item, repository=repository, context=context)
        for item in [*raw_code, *raw_operational]
    ]
    scanner_configuration = [item for item in normalized if item.get("suppression_reason") == "scanner_configuration_error_is_not_source_code_evidence"]
    normalized = [item for item in normalized if item not in scanner_configuration]
    consolidated = _consolidate(normalized)

    code = [
        item
        for item in consolidated
        if item.get("client_actionable") is not False and item.get("path") and isinstance(item.get("line"), int)
    ]
    operational = [item for item in consolidated if item not in code]

    code_signatures = {
        (
            _text(item.get("finding_family")),
            _text(item.get("symbol")).casefold(),
        )
        for item in code
        if _text(item.get("symbol"))
    }
    code_evidence = {
        (_text(item.get("finding_family")), _text(item.get("observed_evidence")).casefold())
        for item in code
        if _text(item.get("observed_evidence"))
    }
    filtered_operational: list[dict[str, Any]] = []
    for item in operational:
        signature = (
            _text(item.get("finding_family")),
            _text(item.get("symbol")).casefold(),
        )
        evidence = (
            _text(item.get("finding_family")),
            _text(item.get("observed_evidence")).casefold(),
        )
        if _text(item.get("finding_family")) == "complexity_hotspot" and (
            (signature[1] and signature in code_signatures) or evidence in code_evidence
        ):
            continue
        filtered_operational.append(item)
    operational = _consolidate(filtered_operational)

    code.sort(
        key=lambda item: (
            item.get("priority") not in {"P0", "P1"},
            _text(item.get("path")),
            int(item.get("line") or 0),
            _text(item.get("finding_family")),
        )
    )
    operational.sort(
        key=lambda item: (
            item.get("priority") not in {"P0", "P1"},
            _text(item.get("category")),
            _text(item.get("title")),
        )
    )

    excluded = [
        _normalize_record(item, repository=repository, context=context)
        for item in raw_excluded
    ]
    decision_count = len(code) + len(operational)
    summary = deepcopy(dict(result.get("summary") or {}))
    summary.update(
        {
            "register_normalization_version": VERSION,
            "raw_observation_count": raw_count,
            "normalized_candidate_count": len(consolidated),
            "decision_finding_count": decision_count,
            "exact_source_code_finding_count": len(code),
            "operational_or_context_finding_count": len(operational),
            "excluded_non_production_count": len(excluded),
            "scanner_configuration_issue_count": len(scanner_configuration),
            "scanner_configuration_errors_promoted_to_code_findings": False,
            "unverified_tls_candidates_promoted_to_p1": False,
            "repository_relative_paths_only": all(
                not _text(item.get("path")).startswith("/") and "/tmp/" not in _text(item.get("path"))
                for item in code
            ),
            "semantic_duplicate_code_anchors_absent": len({_record_key(item) for item in code}) == len(code),
            "cross_population_duplicates_absent": all(item not in code for item in operational),
            "verification_and_exit_criteria_distinct": all(
                item.get("verification_and_exit_criteria_distinct") is True
                for item in [*code, *operational]
            ),
            "finding_population_reconciled": raw_count >= len(consolidated) >= decision_count,
            "human_disposition_required": True,
            "client_delivery_allowed": False,
        }
    )
    result.update(
        {
            "version": VERSION,
            "code_findings": code,
            "operational_findings": operational,
            "excluded_non_production_findings": excluded,
            "scanner_configuration_issues": scanner_configuration,
            "summary": summary,
        }
    )
    return result


def build_finding_remediation_register(canonical: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_client_assessment_truth(canonical)
    base = legacy.build_finding_remediation_register(normalized)
    return normalize_finding_remediation_register(base, normalized)


def canonical_findings_from_register(register: Mapping[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in [
        *[entry for entry in register.get("code_findings") or [] if isinstance(entry, Mapping)],
        *[entry for entry in register.get("operational_findings") or [] if isinstance(entry, Mapping)],
    ]:
        findings.append(
            {
                "finding_id": item.get("finding_id"),
                "finding_aliases": deepcopy(item.get("finding_aliases") or []),
                "priority": item.get("priority"),
                "category": item.get("category"),
                "status": item.get("status"),
                "title": item.get("title"),
                "location": item.get("location") or "location-not-retained",
                "path": item.get("path"),
                "line": item.get("line"),
                "column": item.get("column"),
                "end_line": item.get("end_line"),
                "symbol": item.get("symbol"),
                "rule_id": item.get("rule_id"),
                "finding_family": item.get("finding_family"),
                "fact": item.get("observed_evidence"),
                "interpretation": item.get("interpretation"),
                "business_impact": item.get("business_impact"),
                "recommendation": item.get("recommended_correction"),
                "acceptance_criteria": deepcopy(item.get("verification") or []),
                "exit_criteria": deepcopy(item.get("exit_criteria") or []),
                "rollback": item.get("rollback"),
                "owner_role": item.get("owner_role"),
                "effort": item.get("effort"),
                "evidence_quality": item.get("evidence_quality"),
                "exact_commit_match": item.get("exact_commit_match"),
                "source_excerpt": item.get("source_excerpt"),
                "production_scope": item.get("production_scope", True),
                "human_disposition_required": True,
            }
        )
    return findings


def finding_register_markdown(register: Mapping[str, Any], *, spanish: bool) -> str:
    markdown = legacy.finding_register_markdown(register, spanish=spanish)
    summary = register.get("summary") if isinstance(register.get("summary"), Mapping) else {}
    if spanish:
        population = (
            f"- Población de hallazgos: observaciones brutas={int(summary.get('raw_observation_count') or 0)}; "
            f"candidatos normalizados={int(summary.get('normalized_candidate_count') or 0)}; "
            f"hallazgos de decisión={int(summary.get('decision_finding_count') or 0)}."
        )
        heading = "## Registro de hallazgos y remediación"
    else:
        population = (
            f"- Finding population: raw observations={int(summary.get('raw_observation_count') or 0)}; "
            f"normalized candidates={int(summary.get('normalized_candidate_count') or 0)}; "
            f"decision findings={int(summary.get('decision_finding_count') or 0)}."
        )
        heading = "## Finding and Remediation Register"
    return markdown.replace(heading, f"{heading}\n\n{population}", 1)


def render_finding_register_pdf(register: Mapping[str, Any], *, spanish: bool) -> bytes:
    return legacy.render_finding_register_pdf(register, spanish=spanish)


__all__ = [
    "VERSION",
    "build_finding_remediation_register",
    "canonical_findings_from_register",
    "finding_register_markdown",
    "normalize_finding_remediation_register",
    "render_finding_register_pdf",
]
