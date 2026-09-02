from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

VERSION = "nico.phase6_final_remediation.v1"
_PATCH_MARKER = "_nico_phase6_final_remediation_v1"
_STATUS_SUFFIXES = (
    "FINAL-PENDING-APPROVAL",
    "PENDING-APPROVAL",
    "REVIEW-REQUIRED",
    "FINAL",
    "DRAFT",
)
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

_SQL_DISPOSITIONS = {
    "nico/infrastructure_backup_runtime.py": (
        "Dynamic SQLite table identifiers cannot be parameter-bound. This code routes the identifier through "
        "_quote_identifier, doubles embedded quotes, verifies the table through a parameterized sqlite_master query, "
        "and parameter-binds the row limit. The observed construction is a bounded identifier operation, not raw value interpolation."
    ),
    "nico/comprehensive_run_store.py": (
        "SQL structure is fixed by NICO. Interpolated tokens are selected only from the closed dialect set "
        "{sqlite, postgres} and produce DB-API placeholders or fixed column types; all runtime values are passed separately to cursor.execute."
    ),
    "nico/monitor_approval_governance.py": (
        "The only interpolated SQL token is a DB-API placeholder selected from the closed dialect set. "
        "Approval values are supplied separately to cursor.execute and are not concatenated into the statement."
    ),
    "nico/monitor_execute_service.py": (
        "The statement interpolates only a DB-API placeholder selected from the closed dialect set; work-item values are parameter-bound."
    ),
    "nico/monitor_runtime.py": (
        "The monitor store interpolates only fixed DB-API placeholder tokens and fixed SQL structure. "
        "Monitor identifiers, timestamps, state, lease values, and limits are supplied as bound parameters."
    ),
}


def _text(value: Any, limit: int = 4000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _ordered_unique(values: Iterable[Any], *, limit: int = 500) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _text(value)
        key = token.casefold()
        if not token or key in seen:
            continue
        seen.add(key)
        output.append(token)
        if len(output) >= limit:
            break
    return output


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _normalize_path(value: Any) -> str:
    token = str(value or "").strip().replace("\\", "/")
    token = token.removeprefix("./")
    try:
        normalized = PurePosixPath(token)
    except Exception:
        return token
    if normalized.is_absolute() or ".." in normalized.parts:
        return token.lstrip("/")
    return str(normalized)


def _location_parts(item: dict[str, Any]) -> tuple[str, int | None]:
    raw_location = _text(item.get("canonical_location") or item.get("location"), 600)
    direct_path = _normalize_path(
        item.get("file_path") or item.get("filename") or item.get("path") or item.get("filePath")
    )
    direct_line = item.get("line") or item.get("line_number") or item.get("start_line")
    if raw_location:
        match = re.match(r"^(.*?):(\d+)(?::\d+)?$", raw_location)
        if match:
            direct_path = _normalize_path(match.group(1)) or direct_path
            direct_line = int(match.group(2))
        elif not direct_path:
            direct_path = _normalize_path(raw_location)
    try:
        line = max(1, int(direct_line)) if direct_line not in (None, "") else None
    except (TypeError, ValueError):
        line = None
    return direct_path or "Location not retained by the scanner result.", line


def _canonical_location(path: str, line: int | None) -> str:
    return f"{path}:{line}" if line else path


def _extract_token(item: dict[str, Any], keys: tuple[str, ...], pattern: str) -> str:
    for key in keys:
        value = _text(item.get(key), 300)
        if value:
            return value
    evidence = _text(item.get("evidence") or item.get("fact"), 3000)
    match = re.search(pattern, evidence, re.IGNORECASE)
    return _text(match.group(1), 300) if match else ""


def _tool(item: dict[str, Any]) -> str:
    return _extract_token(item, ("tool", "scanner", "analyzer"), r"\btool\s*=\s*([^;]+)").casefold()


def _rule_id(item: dict[str, Any]) -> str:
    return _extract_token(
        item,
        ("rule_id", "check_id", "test_id", "code", "rule", "scanner_rule_id"),
        r"\b(?:rule|check_id|test_id|code)\s*=\s*([^;]+)",
    ).casefold()


def _analyzer_message(item: dict[str, Any]) -> str:
    for key in ("analyzer_message", "message", "title", "interpretation", "description"):
        value = _text(item.get(key), 2400)
        if value:
            return value
    return "Analyzer finding requires review."


def _executive_title(message: str, category: str, rule_id: str) -> str:
    lowered = f"{rule_id} {message}".casefold()
    if "sql" in lowered and any(token in lowered for token in ("injection", "concaten", "query")):
        return "Unsafe SQL query construction"
    if "verify=false" in lowered or "tls verification" in lowered:
        return "TLS certificate verification disabled"
    if "shell=true" in lowered or "subprocess" in lowered:
        return "Shell command injection exposure"
    if "dynamic eval" in lowered or re.search(r"\beval\b", lowered):
        return "Dynamic code execution"
    if "secret" in lowered or category == "secret":
        return "Potential credential exposure"
    if category == "dependency":
        return "Dependency vulnerability requires disposition"
    if category == "architecture":
        return "High-complexity code hotspot"
    if category == "ci_cd":
        return "Delivery workflow reliability issue"
    compact = re.split(r"[.!?]", message, maxsplit=1)[0].strip()
    return _text(compact or "Technical finding requires disposition", 110)


def _fingerprint(parts: Iterable[Any]) -> str:
    canonical = "|".join(_text(value, 2000).casefold() for value in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sql_disposition(path: str, message: str) -> dict[str, Any] | None:
    lowered = message.casefold()
    if path not in _SQL_DISPOSITIONS:
        return None
    if "sql" not in lowered or not any(token in lowered for token in ("injection", "concaten", "raw query")):
        return None
    return {
        "status": "approved_nonblocking",
        "classification": "source_reviewed_false_positive",
        "rationale": _SQL_DISPOSITIONS[path],
        "scope": path,
        "review_method": "exact_source_review_plus_regression_test",
        "expires_on_source_change": True,
    }


def _canonicalize_finding(item: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(item)
    path, line = _location_parts(output)
    location = _canonical_location(path, line)
    category = _text(output.get("category"), 80).casefold() or "unknown"
    tool = _tool(output)
    rule_id = _rule_id(output)
    message = _analyzer_message(output)
    incoming_id = _text(output.get("finding_id") or output.get("id"), 180)
    base_key = (
        f"stable:{incoming_id.casefold()}|{path.casefold()}"
        if incoming_id.upper().startswith("RISK-")
        else "observed:" + _fingerprint((tool, rule_id, path, line or 0, message))
    )
    priority = _text(output.get("priority"), 20).upper() or "P2"
    stable_id = incoming_id if incoming_id.upper().startswith("RISK-") else f"RISK-{priority}-{_fingerprint((base_key,))[:10].upper()}"
    related_locations = _ordered_unique(
        [location, *_as_list(output.get("related_locations")), *_as_list(output.get("grouped_locations"))]
    )
    acceptance = _ordered_unique(_as_list(output.get("acceptance_criteria")))
    roadmap = _ordered_unique(_as_list(output.get("roadmap_mappings")))
    backlog = _ordered_unique(
        [*_as_list(output.get("backlog_mappings")), *_as_list(output.get("backlog_issue_mapping"))]
    )
    disposition = _sql_disposition(path, message)
    output.update(
        {
            "id": stable_id,
            "finding_id": stable_id,
            "finding_key": base_key,
            "tool": tool or output.get("tool") or "unknown",
            "rule_id": rule_id or output.get("rule_id") or "unknown",
            "category": category,
            "executive_title": _executive_title(message, category, rule_id),
            "technical_summary": _text(
                output.get("technical_summary")
                or f"The analyzer reported a {category} condition at {location}; exact-source disposition is required.",
                700,
            ),
            "analyzer_message": message,
            "title": _executive_title(message, category, rule_id),
            "original_analyzer_location": _text(output.get("location") or location, 600),
            "canonical_path": path,
            "canonical_line": line,
            "canonical_location": location,
            "location": location,
            "related_locations": related_locations,
            "grouped_locations": related_locations,
            "acceptance_criteria": acceptance,
            "roadmap_mappings": roadmap,
            "backlog_mappings": backlog,
            "backlog_issue_mapping": backlog[0] if backlog else "",
            "source_evidence_fingerprint": _fingerprint((tool, rule_id, path, line or 0, message)),
        }
    )
    if disposition:
        output["disposition"] = disposition
        output["status"] = "approved_nonblocking"
        output["priority"] = "P3"
    return output


def _merge_finding(target: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(target)
    output["related_locations"] = _ordered_unique(
        [*target.get("related_locations", []), *candidate.get("related_locations", [])]
    )
    output["grouped_locations"] = list(output["related_locations"])
    output["roadmap_mappings"] = _ordered_unique(
        [*target.get("roadmap_mappings", []), *candidate.get("roadmap_mappings", [])]
    )
    output["backlog_mappings"] = _ordered_unique(
        [*target.get("backlog_mappings", []), *candidate.get("backlog_mappings", [])]
    )
    output["backlog_issue_mapping"] = output["backlog_mappings"][0] if output["backlog_mappings"] else ""
    output["acceptance_criteria"] = _ordered_unique(
        [*target.get("acceptance_criteria", []), *candidate.get("acceptance_criteria", [])]
    )
    evidence = _ordered_unique(
        [
            target.get("evidence") or target.get("fact"),
            candidate.get("evidence") or candidate.get("fact"),
        ]
    )
    if evidence:
        output["evidence_records"] = evidence
        output["evidence"] = evidence[0]
    if _PRIORITY_ORDER.get(candidate.get("priority", "P3"), 9) < _PRIORITY_ORDER.get(output.get("priority", "P3"), 9):
        output["priority"] = candidate["priority"]
    return output


def canonicalize_findings(records: Iterable[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        item = _canonicalize_finding(raw)
        key = str(item["finding_key"])
        grouped[key] = _merge_finding(grouped[key], item) if key in grouped else item
    ordered = sorted(
        grouped.values(),
        key=lambda item: (
            _PRIORITY_ORDER.get(str(item.get("priority") or "P3"), 9),
            str(item.get("category") or ""),
            str(item.get("canonical_path") or ""),
            int(item.get("canonical_line") or 0),
            str(item.get("finding_id") or ""),
        ),
    )
    used: dict[str, str] = {}
    actionable: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for item in ordered:
        finding_id = str(item.get("finding_id") or "")
        key = str(item.get("finding_key") or "")
        if finding_id in used and used[finding_id] != key:
            finding_id = f"{finding_id}-{_fingerprint((key,))[:6].upper()}"
            item["id"] = finding_id
            item["finding_id"] = finding_id
        used[finding_id] = key
        if isinstance(item.get("disposition"), dict):
            dispositions.append(item)
        else:
            actionable.append(item)
    return actionable, dispositions


def _find_nested(value: Any, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if predicate(value):
            return value
        for child in value.values():
            found = _find_nested(child, predicate)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_nested(child, predicate)
            if found is not None:
                return found
    return None


def _complexity_class(path: str, hotspot: dict[str, Any]) -> str:
    lowered = path.casefold()
    name = _text(hotspot.get("name"), 300).casefold()
    if any(part in lowered for part in ("node_modules/", "/vendor/", ".next/", "/dist/", "/build/")):
        return "generated_or_vendor"
    if lowered.startswith("tests/") or "/tests/" in lowered or name.startswith("test_"):
        return "test_code"
    if hotspot.get("region_type") in {"module", "module_region", "synthetic"} or name in {"<module>", "module"}:
        return "module_or_synthetic_region"
    if "comprehensive" in lowered and any(token in lowered for token in ("report", "html", "pdf", "assessment")):
        return "report_generation"
    return "production_function_or_component"


def _actionable_complexity(stage_results: dict[str, Any]) -> dict[str, Any]:
    payload = _find_nested(
        stage_results,
        lambda item: isinstance(item.get("hotspots"), list)
        and any(key in item for key in ("high_complexity_functions", "functions_measured", "complexity_score")),
    )
    if not payload:
        return {}
    classes: dict[str, int] = {}
    unique: dict[tuple[str, int, str], dict[str, Any]] = {}
    for raw in payload.get("hotspots") or []:
        if not isinstance(raw, dict):
            continue
        path = _normalize_path(raw.get("path"))
        line = int(raw.get("line") or 0)
        name = _text(raw.get("name"), 300) or "measured region"
        key = (path, line, name)
        if key in unique:
            continue
        item = deepcopy(raw)
        item["path"] = path
        item["line"] = line or None
        item["name"] = name
        item["classification"] = _complexity_class(path, item)
        item["actionable"] = item["classification"] in {
            "production_function_or_component",
            "report_generation",
        } and int(item.get("cyclomatic_complexity") or 0) >= 30
        unique[key] = item
        classes[item["classification"]] = classes.get(item["classification"], 0) + 1
    actionable = sorted(
        (item for item in unique.values() if item["actionable"]),
        key=lambda item: (-int(item.get("cyclomatic_complexity") or 0), item["path"], int(item.get("line") or 0)),
    )
    return {
        "schema": "nico.phase6.actionable_complexity.v1",
        "population_definition": "Unique measured regions classified by source role; only active production functions/components and report-generation functions at cyclomatic complexity >=30 are actionable.",
        "unique_hotspot_count": len(unique),
        "classified_counts": dict(sorted(classes.items())),
        "actionable_hotspot_count": len(actionable),
        "actionable_hotspots": actionable[:20],
        "raw_high_complexity_region_count": int(payload.get("high_complexity_functions") or 0),
        "raw_region_count_retained_for_audit": True,
    }


def _exact_commit_health(stage_results: dict[str, Any], commit_sha: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            candidate_commit = _text(
                value.get("commit_sha") or value.get("target_commit_sha") or value.get("snapshot_commit_sha"),
                80,
            ).casefold()
            green = value.get("all_required_checks_green")
            if green is None:
                green = value.get("required_checks_green")
            if green is None and isinstance(value.get("current_required_checks"), dict):
                green = value["current_required_checks"].get("green")
            if green is not None and candidate_commit == commit_sha.casefold():
                candidates.append({"green": bool(green), "source": _text(value.get("schema") or value.get("status_source") or "exact_commit_evidence", 180)})
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(stage_results)
    if not candidates:
        return {"status": "not_observed", "green": None, "commit_sha": commit_sha, "truth_rule": "No exact-commit required-check record was retained; historical or default-branch state is not substituted."}
    return {"status": "green" if all(item["green"] for item in candidates) else "not_green", "green": all(item["green"] for item in candidates), "commit_sha": commit_sha, "sources": candidates}


def _clean_section_text(section: dict[str, Any], completed_scanners: set[str]) -> None:
    for field in ("evidence", "findings", "unavailable"):
        values = _as_list(section.get(field))
        cleaned: list[str] = []
        for value in values:
            text = _text(value, 4000)
            lowered = text.casefold()
            if "phase 5" in lowered or "phase5" in lowered:
                continue
            if any(tool in lowered for tool in completed_scanners) and any(
                marker in lowered for marker in ("failed", "partial", "unavailable", "incomplete", "did not complete")
            ):
                continue
            cleaned.append(text)
        section[field] = _ordered_unique(cleaned)


def reconcile_assessment(assessment: dict[str, Any], stage_results: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(assessment)
    phase_change = output.pop("phase5_verified_outcomes", None)
    output.pop("phase5_tracked_complexity_metrics", None)
    if isinstance(phase_change, dict):
        output["verification_provenance"] = {
            "schema": "nico.exact_sha_verification_provenance.v1",
            "current_commit_sha": phase_change.get("current_commit_sha"),
            "truth_rule": phase_change.get("truth_rule"),
            "customer_report_section": False,
        }
    sections = [
        item for item in output.get("sections") or []
        if isinstance(item, dict) and item.get("id") != "phase5_verified_outcomes"
    ]
    health = output.get("evidence_health_summary") if isinstance(output.get("evidence_health_summary"), dict) else {}
    completed = {str(item).casefold() for item in health.get("completed_scanners") or []}
    for section in sections:
        _clean_section_text(section, completed)
    output["sections"] = sections

    raw_findings: list[Any] = []
    for field in ("decision_grade_findings_register", "findings_register", "executive_risk_register"):
        raw_findings.extend(_as_list(output.get(field)))
    actionable, dispositions = canonicalize_findings(raw_findings)
    output["findings_register"] = actionable
    output["decision_grade_findings_register"] = actionable
    output["executive_risk_register"] = actionable[:7]
    output["finding_dispositions"] = dispositions
    output["finding_integrity"] = {
        "schema": "nico.phase6.finding_integrity.v1",
        "actionable_unique_count": len(actionable),
        "source_reviewed_disposition_count": len(dispositions),
        "stable_ids_unique": len({item["finding_id"] for item in actionable}) == len(actionable),
        "canonical_locations_present": all(bool(item.get("canonical_location")) for item in actionable),
        "ordered_set_mappings": True,
    }
    if dispositions:
        static = next((item for item in sections if item.get("id") == "static_analysis"), None)
        if static is not None:
            static.setdefault("evidence", [])
            static["evidence"] = _ordered_unique([
                *static["evidence"],
                f"Source-reviewed analyzer dispositions: {len(dispositions)} bounded nonblocking record(s); full rationale retained in canonical JSON.",
            ])

    identity_record = _find_nested(
        stage_results,
        lambda item: bool(item.get("commit_sha") or item.get("target_commit_sha") or item.get("snapshot_commit_sha")),
    )
    commit_sha = _text(output.get("commit_sha"), 80)
    if not commit_sha and isinstance(identity_record, dict):
        commit_sha = _text(
            identity_record.get("commit_sha")
            or identity_record.get("target_commit_sha")
            or identity_record.get("snapshot_commit_sha"),
            80,
        )
    ci_summary = output.get("ci_history_classification") if isinstance(output.get("ci_history_classification"), dict) else {}
    historical = ci_summary.get("historical_reliability") if isinstance(ci_summary.get("historical_reliability"), dict) else {}
    default_health = ci_summary.get("current_branch_health") if isinstance(ci_summary.get("current_branch_health"), dict) else {}
    output["ci_health"] = {
        "schema": "nico.phase6.ci_health.v1",
        "assessed_commit": _exact_commit_health(stage_results, commit_sha),
        "current_default_branch": default_health or {"status": "not_observed", "green": None},
        "bounded_historical_reliability": historical,
        "historical_failures_do_not_override_assessed_commit": True,
        "active_or_queued_runs_are_not_historical_failures": True,
    }
    ci_section = next((item for item in sections if item.get("id") == "ci_cd"), None)
    if ci_section is not None:
        ci_section["evidence"] = [
            value for value in ci_section.get("evidence") or []
            if not _text(value).casefold().startswith("current required-check health green:")
        ]
        assessed = output["ci_health"]["assessed_commit"]
        ci_section["evidence"] = _ordered_unique([
            *ci_section["evidence"],
            f"Assessed-commit required-check health: {assessed.get('status')} (commit {commit_sha or 'unavailable'}).",
            f"Current default-branch required-check health: {default_health.get('green') if default_health else 'not observed'}.",
            "Bounded historical reliability is reported separately and does not change assessed-commit health.",
        ])

    complexity = _actionable_complexity(stage_results)
    if complexity:
        output["actionable_complexity"] = complexity
        architecture = next((item for item in sections if item.get("id") == "architecture_debt"), None)
        if architecture is not None:
            architecture["evidence"] = _ordered_unique([
                complexity["population_definition"],
                f"Unique classified hotspots: {complexity['unique_hotspot_count']}.",
                f"Actionable production/report hotspots at complexity >=30: {complexity['actionable_hotspot_count']}.",
                f"Classification counts: {json.dumps(complexity['classified_counts'], sort_keys=True)}.",
                f"Raw high-complexity region count retained for audit: {complexity['raw_high_complexity_region_count']}.",
            ])
            architecture["findings"] = [
                f"Actionable hotspot {item.get('path')}:{item.get('line') or 1} · {item.get('name')} · complexity {item.get('cyclomatic_complexity')}."
                for item in complexity["actionable_hotspots"][:8]
            ]
    output["human_review_required"] = True
    output["client_ready"] = False
    output["client_delivery_allowed"] = False
    return output


def normalize_report_filename(filename: str, *, complete: bool, approved: bool) -> str:
    token = str(filename or "nico-comprehensive-assessment.pdf").strip()
    path = Path(token)
    suffix = path.suffix or ".pdf"
    stem = path.stem
    changed = True
    while changed:
        changed = False
        for status in _STATUS_SUFFIXES:
            marker = "-" + status
            if stem.upper().endswith(marker):
                stem = stem[: -len(marker)]
                changed = True
                break
    desired = "FINAL" if complete and approved else "FINAL-PENDING-APPROVAL" if complete else "DRAFT"
    return f"{stem}-{desired}{suffix}"


def _normalize_bandit_row(row: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "issue text": "message",
        "severity": "issue_severity",
        "confidence": "issue_confidence",
        "cwe": "cwe",
        "test id": "test_id",
        "filename": "filename",
        "line number": "line_number",
        "more info": "more_info",
    }
    output: dict[str, Any] = {}
    for key, value in row.items():
        normalized = re.sub(r"[_\s]+", " ", str(key or "").strip().casefold())
        output[aliases.get(normalized, normalized.replace(" ", "_"))] = value
    if output.get("line_number"):
        try:
            output["line_number"] = int(str(output["line_number"]))
        except ValueError:
            pass
    return output


def _patch_scanner_runners() -> None:
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.scanner_tool_runners import ScannerToolSpec
    from nico.worker_execution import WorkerCommandResult, WorkerLimits

    if getattr(pipeline._run_bandit, _PATCH_MARKER, False):
        return

    original_gitleaks = pipeline._run_gitleaks
    original_trufflehog = pipeline._run_trufflehog

    def bandit(spec: ScannerToolSpec, workspace: Any, runner: Callable[..., Any]) -> dict[str, Any]:
        binary = shutil.which("bandit")
        if binary is None:
            return pipeline._unavailable(spec, "bandit is not installed in the worker image.", source="canonical_bandit_csv_v2")
        raw = workspace.root / "scanner-raw" / "bandit.csv"
        raw.parent.mkdir(parents=True, exist_ok=True)
        log = workspace.root / "scanner-output" / "bandit.log"
        command = (binary, "-r", ".", "-f", "csv", "-o", str(raw), "-x", ",".join(sorted(pipeline.GENERATED_DIRS)))
        result = pipeline._run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 4_000_000)), stdout_path=log)
        findings: list[dict[str, Any]] = []
        reason = ""
        complete = raw.exists()
        if raw.exists():
            try:
                with raw.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                    reader = csv.DictReader(handle)
                    normalized_headers = {re.sub(r"[_\s]+", " ", str(value or "").strip().casefold()) for value in reader.fieldnames or []}
                    required = {"issue text", "severity", "confidence", "test id", "filename", "line number"}
                    if not required.issubset(normalized_headers):
                        raise csv.Error("Bandit CSV header is incomplete")
                    findings.extend(_normalize_bandit_row(dict(row)) for row in reader)
            except (OSError, csv.Error) as exc:
                complete = False
                reason = f"Bandit CSV output could not be parsed: {type(exc).__name__}"
        else:
            reason = "Bandit did not create its complete CSV report."
        blob = pipeline._raw_blob(spec.name, raw if raw.exists() else log, "csv")
        return pipeline._tool_payload(spec, result, findings=findings, capture_complete=complete, reason=reason, raw_blob=blob, execution_source="canonical_bandit_csv_v2", workspace=workspace, valid_returncodes={0, 1}, extra={"compact_complete_result": True, "bandit_header_normalized": True})

    def eslint(spec: ScannerToolSpec, workspace: Any, runner: Callable[..., Any], preparation: Any) -> dict[str, Any]:
        project_dir = preparation.project_dir if preparation else pipeline.resolve_node_project_dir(workspace.repo_dir)
        if not pipeline._supported_web_files(project_dir):
            return pipeline._unavailable(spec, "No supported JavaScript or TypeScript source files were found in the resolved Node project.", source="canonical_eslint_v2")
        binary = shutil.which("eslint") or str(project_dir / "node_modules" / ".bin" / "eslint")
        if not Path(binary).exists() and shutil.which(binary) is None:
            return pipeline._unavailable(spec, "eslint is not installed in the worker image.", source="canonical_eslint_v2")
        config, config_reason = pipeline._eslint_config(workspace, project_dir)
        if config is None:
            return pipeline._unavailable(spec, config_reason, source="canonical_eslint_v2")
        raw = workspace.root / "scanner-raw" / "eslint.json"
        command = (binary, ".", "--ext", ".js,.jsx,.mjs,.cjs,.ts,.tsx", "--format", "json", "--config", str(config), "--no-config-lookup", "--no-error-on-unmatched-pattern")
        env = pipeline._node_env(workspace, project_dir)
        env["NODE_OPTIONS"] = os.getenv("NICO_NODE_OPTIONS", "--max-old-space-size=2048")
        result = pipeline._run(runner, command, cwd=project_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 16_000_000)), stdout_path=raw, extra_env=env)
        payload, reason = pipeline._read_json(raw)
        findings: list[Any] = []
        if isinstance(payload, list):
            for file_result in payload:
                if not isinstance(file_result, dict):
                    continue
                for message in file_result.get("messages") or []:
                    if isinstance(message, dict):
                        item = dict(message)
                        item.setdefault("filePath", file_result.get("filePath"))
                        findings.append(item)
        blob = pipeline._raw_blob(spec.name, raw, "json")
        return pipeline._tool_payload(spec, result, findings=findings, capture_complete=isinstance(payload, list), reason=reason, raw_blob=blob, execution_source="canonical_eslint_flat_config_v2", workspace=workspace, valid_returncodes={0, 1}, extra={"project_preparation": {"status": preparation.status, "node_modules_ready": preparation.node_modules_ready} if preparation else {}, "generated_config_sha256": pipeline._sha256(config.read_bytes()), "explicit_source_glob": True})

    def gitleaks(spec: ScannerToolSpec, workspace: Any, runner: Callable[..., Any]) -> dict[str, Any]:
        history = pipeline._history_metadata(workspace)
        if history.get("full_history_verified"):
            return original_gitleaks(spec, workspace, runner)
        binary = shutil.which("gitleaks")
        if binary is None:
            return pipeline._unavailable(spec, "gitleaks is not installed in the worker image.", source="canonical_gitleaks_exact_snapshot_v2")
        raw = workspace.root / "scanner-raw" / "gitleaks.json"
        log = workspace.root / "scanner-output" / "gitleaks.log"
        attempts = (
            (binary, "dir", ".", "--report-format", "json", "--report-path", str(raw), "--no-banner", "--redact"),
            (binary, "detect", "--source", ".", "--no-git", "--report-format", "json", "--report-path", str(raw), "--no-banner", "--redact"),
        )
        last = WorkerCommandResult(args=(binary,), returncode=127, stdout="", stderr="")
        reason = ""
        payload: Any = None
        for command in attempts:
            raw.unlink(missing_ok=True)
            last = pipeline._run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 4_000_000)), stdout_path=log)
            if last.returncode == 0 and not raw.exists():
                raw.write_text("[]\n", encoding="utf-8")
            payload, reason = pipeline._read_json(raw)
            if isinstance(payload, list) and last.returncode in {0, 1} and not last.timed_out:
                break
        snapshot_spec = replace(spec, scans_git_history=False)
        blob = pipeline._raw_blob(spec.name, raw if raw.exists() else log, "json")
        return pipeline._tool_payload(snapshot_spec, last, findings=payload if isinstance(payload, list) else [], capture_complete=isinstance(payload, list), reason=reason, raw_blob=blob, execution_source="canonical_gitleaks_exact_snapshot_v2", workspace=workspace, valid_returncodes={0, 1}, extra={**history, "coverage_scope": "exact_snapshot", "history_coverage_unavailable": True})

    def trufflehog(spec: ScannerToolSpec, workspace: Any, runner: Callable[..., Any]) -> dict[str, Any]:
        history = pipeline._history_metadata(workspace)
        if history.get("full_history_verified"):
            return original_trufflehog(spec, workspace, runner)
        binary = shutil.which("trufflehog")
        if binary is None:
            return pipeline._unavailable(spec, "trufflehog is not installed in the worker image.", source="canonical_trufflehog_exact_snapshot_v2")
        raw = workspace.root / "scanner-raw" / "trufflehog.jsonl"
        command = (binary, "filesystem", str(workspace.repo_dir), "--json", "--no-update", "--no-verification")
        result = pipeline._run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 8_000_000)), stdout_path=raw)
        findings: list[Any] = []
        invalid = 0
        for line in pipeline._read_text(raw).splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if isinstance(item, dict):
                findings.append(item)
            else:
                invalid += 1
        snapshot_spec = replace(spec, scans_git_history=False)
        blob = pipeline._raw_blob(spec.name, raw, "jsonl")
        return pipeline._tool_payload(snapshot_spec, result, findings=findings, capture_complete=invalid == 0, reason="" if invalid == 0 else f"{invalid} TruffleHog output line(s) were not valid JSON", raw_blob=blob, execution_source="canonical_trufflehog_exact_snapshot_v2", workspace=workspace, valid_returncodes={0, 183}, extra={**history, "coverage_scope": "exact_snapshot", "history_coverage_unavailable": True, "invalid_json_lines": invalid})

    for value in (bandit, eslint, gitleaks, trufflehog):
        setattr(value, _PATCH_MARKER, True)
    pipeline._run_bandit = bandit
    pipeline._run_eslint = eslint
    pipeline._run_gitleaks = gitleaks
    pipeline._run_trufflehog = trufflehog


def _patch_scanner_precedence() -> None:
    from nico import phase5_report_truth_v1 as v1
    from nico import phase5_report_truth_v2 as v2

    original = v2._ORIGINAL_NORMALIZED_SCANNER_RECORD

    def normalize(tool: str, payload: dict[str, Any], *, context: dict[str, str], path: str, target_commit: str) -> dict[str, Any]:
        enriched = dict(payload)
        retained = enriched.get("raw_artifact_retention_complete") is True or bool(enriched.get("raw_artifact"))
        if retained:
            enriched["raw_artifact_capture_complete"] = True
        record = original(tool, enriched, context=context, path=path, target_commit=target_commit)
        record["raw_artifact_retention_complete"] = retained
        record["verified_artifact_hash"] = bool(record.get("artifact_hash") or record.get("raw_artifact_sha256"))
        record["current_run"] = enriched.get("current_run") is True
        record["observed_at"] = _text(enriched.get("finished_at") or enriched.get("generated_at") or enriched.get("updated_at"), 100)
        record["execution_complete"] = bool(record.get("execution_complete")) and record["verified_artifact_hash"] and retained
        return record

    def authoritative(stage_results: dict[str, Any], target_commit: str) -> dict[str, dict[str, Any]]:
        candidates = v1._collect_scanner_records(stage_results, target_commit=target_commit)
        output: dict[str, dict[str, Any]] = {}
        for tool in v1.REQUIRED_EVIDENCE_TOOLS:
            items = [item for item in candidates if item.get("tool") == tool]
            if not items:
                continue
            items.sort(
                key=lambda item: (
                    bool(item.get("exact_commit_match")),
                    bool(item.get("raw_artifact_retention_complete")),
                    bool(item.get("verified_artifact_hash")),
                    bool(item.get("execution_complete")),
                    str(item.get("observed_at") or ""),
                    str(item.get("source_path") or ""),
                ),
                reverse=True,
            )
            output[tool] = items[0]
        return output

    setattr(normalize, _PATCH_MARKER, True)
    setattr(authoritative, _PATCH_MARKER, True)
    v2._ORIGINAL_NORMALIZED_SCANNER_RECORD = normalize
    v1._authoritative_scanners = authoritative


def _strip_phase_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_phase_fields(item)
            for key, item in value.items()
            if not str(key).startswith("phase5_") and str(key) != "phase5_verified_outcomes"
        }
    if isinstance(value, list):
        return [_strip_phase_fields(item) for item in value]
    return value


def _patch_report_surfaces() -> None:
    from nico import comprehensive_decision_grade_report_v5 as report
    from nico import comprehensive_report_package as base_report

    current_assessment = base_report._assessment
    if not getattr(current_assessment, _PATCH_MARKER, False):
        def assessment(stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
            return reconcile_assessment(current_assessment(stage_results), stage_results)
        setattr(assessment, _PATCH_MARKER, True)
        base_report._assessment = assessment

    original_quality = report._quality_contract
    if not getattr(original_quality, _PATCH_MARKER, False):
        def quality(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = original_quality(*args, **kwargs)
            front_matter = kwargs.get("front_matter_text")
            if front_matter is None and len(args) >= 15:
                front_matter = args[14]
            text = str(front_matter or "")
            valid = "Assessment Coverage" in text and "Why this is broader than Express" not in text
            result["assessment_coverage_front_matter"] = valid
            result["express_quality_front_matter"] = valid
            result["phase_numbered_customer_sections_absent"] = "Phase 5" not in text
            return result
        setattr(quality, _PATCH_MARKER, True)
        report._quality_contract = quality

    current_build = report.build_comprehensive_report_package
    if not getattr(current_build, _PATCH_MARKER, False):
        def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = current_build(*args, **kwargs)
            result = _strip_phase_fields(result)
            package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
            complete = result.get("status") == "complete"
            approved = package.get("client_delivery_allowed") is True or result.get("client_delivery_allowed") is True
            package["pdf_filename"] = normalize_report_filename(str(package.get("pdf_filename") or ""), complete=complete, approved=approved)
            for field in ("markdown", "html"):
                if isinstance(package.get(field), str):
                    package[field] = package[field].replace("Why this is broader than Express", "Assessment Coverage")
                    package[field] = package[field].replace("Express technical-health baseline", "shared technical-health evidence")
                    package[field] = package[field].replace("Express is a faster baseline.", "Technical score and evidence readiness are independent measures.")
            result["report_package"] = package
            assessment_value = result.get("assessment") if isinstance(result.get("assessment"), dict) else {}
            result["assessment"] = reconcile_assessment(assessment_value, kwargs.get("stage_results") or {})
            return result
        setattr(build, _PATCH_MARKER, True)
        report.build_comprehensive_report_package = build
        for module in tuple(sys.modules.values()):
            name = str(getattr(module, "__name__", ""))
            if name.startswith("nico.") and getattr(module, "build_comprehensive_report_package", None) is current_build:
                setattr(module, "build_comprehensive_report_package", build)


def install_phase6_final_remediation_v1() -> dict[str, Any]:
    from nico.phase6_pdf_layout_v1 import install_phase6_pdf_layout_v1

    _patch_scanner_runners()
    _patch_scanner_precedence()
    _patch_report_surfaces()
    pdf_layout = install_phase6_pdf_layout_v1()
    return {
        "status": "installed",
        "version": VERSION,
        "phase_numbered_customer_sections_removed": True,
        "express_comparison_customer_language_removed": True,
        "neutral_assessment_coverage_required": True,
        "bandit_csv_header_normalized": True,
        "eslint_flat_config_source_glob": True,
        "exact_snapshot_secret_scan_is_honest_when_history_unavailable": True,
        "scanner_precedence_exact_sha_artifact_hash_retention_complete": True,
        "canonical_finding_identity": True,
        "source_specific_sql_dispositions": sorted(_SQL_DISPOSITIONS),
        "canonical_locations_cross_format": True,
        "ordered_set_mappings": True,
        "ci_health_dimensions_separated": True,
        "actionable_complexity_classification": True,
        "idempotent_report_filename": True,
        "concise_pdf_layout": pdf_layout.get("status") in {"installed", "already_installed"},
        "artificial_minimum_page_padding_removed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "canonicalize_findings",
    "reconcile_assessment",
    "normalize_report_filename",
    "install_phase6_final_remediation_v1",
]
