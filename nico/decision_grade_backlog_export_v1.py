from __future__ import annotations

import csv
import hashlib
import io
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Iterable

VERSION = "nico.decision_grade_backlog_export.v1"
_REQUIRED_FORMATS = ("markdown", "json", "github", "jira_csv", "linear_csv")
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _text(value: Any, limit: int = 4000) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _dedupe(values: Iterable[Any], *, limit: int = 100) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _criterion_description(value: Any) -> str:
    if isinstance(value, dict):
        description = _text(value.get("description") or value.get("criterion"))
        anchors = _dedupe(
            [
                value.get("file_path"),
                value.get("symbol_or_control"),
                value.get("test_name"),
                value.get("workflow_name"),
                value.get("configuration_key"),
                value.get("repository_query"),
                value.get("dependency_identifier"),
                value.get("control_identifier"),
            ]
        )
        if anchors:
            return f"{description} [Verify: {', '.join(anchors)}]"
        return description
    return _text(value)


def _residual_text(value: Any) -> str:
    if isinstance(value, dict):
        return _text(
            value.get("does_not_eliminate")
            or value.get("not_eliminated")
            or value.get("remaining_impact")
            or value.get("reduces")
        )
    return _text(value)


def _priority(findings: list[dict[str, Any]]) -> str:
    values = [_text(item.get("priority"), 10).upper() for item in findings]
    values = [value if value in _PRIORITY_ORDER else "P2" for value in values]
    return min(values, key=lambda value: _PRIORITY_ORDER[value]) if values else "P2"


def _csv_text(headers: list[str], rows: list[list[Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return stream.getvalue()


def _description(item: dict[str, Any]) -> str:
    lines = [
        f"NICO backlog item: {item['backlog_item_id']}",
        f"Source assessment: {item['source_report']}",
        f"Assessed commit: {item['assessed_commit_sha']}",
        f"Priority: {item['priority']}",
        "",
        "Problem",
        item["problem_statement"],
        "",
        "Evidence",
        *[f"- {value}" for value in item["evidence"]],
        "",
        "Business impact",
        item["business_impact"],
        "",
        "Implementation guidance",
        *[f"{index}. {value}" for index, value in enumerate(item["implementation_guidance"], start=1)],
        "",
        "Acceptance criteria",
        *[f"- [ ] {value}" for value in item["acceptance_criteria"]],
        "",
        "Residual risk",
        item["residual_risk"],
        "",
        "Human review is required. This export does not create or authorize an external issue automatically.",
    ]
    return "\n".join(lines).strip()


def _build_item(
    key: str,
    findings: list[dict[str, Any]],
    roadmap: dict[str, Any] | None,
    *,
    assessment_id: str,
    commit_sha: str,
) -> dict[str, Any]:
    roadmap = roadmap or {}
    priority = _priority(findings)
    finding_ids = _dedupe(item.get("finding_id") for item in findings)
    title = _text(roadmap.get("title")) or _text(findings[0].get("title")) or f"Resolve {key}"
    factual = _dedupe(item.get("factual_statement") or item.get("technical_interpretation") for item in findings)
    interpretations = _dedupe(item.get("technical_interpretation") for item in findings)
    problem = " ".join(_dedupe([*factual, *interpretations], limit=12))
    evidence = _dedupe(
        [
            *(location for item in findings for location in (item.get("evidence_locations") or [])),
            *(evidence_id for item in findings for evidence_id in (item.get("evidence_ids") or [])),
        ],
        limit=50,
    )
    impacts = _dedupe(item.get("business_impact") for item in findings)
    implementation = _dedupe(
        [
            *(roadmap.get("ordered_implementation_steps") or []),
            *(item.get("recommended_action") for item in findings),
        ],
        limit=20,
    )
    acceptance = _dedupe(
        _criterion_description(value)
        for value in [
            *(roadmap.get("acceptance_criteria") or []),
            *(criterion for item in findings for criterion in (item.get("acceptance_criteria") or [])),
        ]
    )
    residual = _text(_residual_text(roadmap.get("residual_risk"))) or " ".join(
        _dedupe(_residual_text(item.get("residual_risk")) for item in findings)
    )
    owner = _text(roadmap.get("owner_role")) or _text(findings[0].get("owner_role")) or "Product Engineering Architect"
    effort = _text(roadmap.get("effort_range")) or _text(findings[0].get("effort")) or "Requires estimation"
    dependencies = _dedupe(roadmap.get("dependencies") or [])
    classification = _text(roadmap.get("classification")) or "Strategic"
    time_window = _text(roadmap.get("time_window")) or "0-30 days"
    scope = "; ".join(_dedupe(item.get("scope") for item in findings)) or "assessed_repository"
    labels = _dedupe(
        [
            "nico",
            "decision-grade",
            priority.casefold(),
            classification.casefold().replace(" ", "-"),
            time_window.casefold().replace(" ", "-"),
        ]
    )
    item = {
        "backlog_item_id": key,
        "title": title,
        "priority": priority,
        "related_finding_ids": finding_ids,
        "problem_statement": problem or "Disposition and remediate the related evidence-bound finding.",
        "evidence": evidence or ["See the retained NICO decision-grade contract."],
        "business_impact": " ".join(impacts) or "Reduces delivery uncertainty, rework exposure, and residual technical risk.",
        "scope": scope,
        "implementation_guidance": implementation or ["Review the retained evidence.", "Implement the bounded remediation.", "Verify against the remediation commit."],
        "owner_role": owner,
        "effort": effort,
        "dependencies": dependencies,
        "acceptance_criteria": acceptance or ["The remediation commit records a binary pass for every related finding."],
        "residual_risk": residual or "Adjacent unassessed paths and future regressions remain possible.",
        "source_report": assessment_id,
        "assessed_commit_sha": commit_sha,
        "classification": classification,
        "time_window": time_window,
        "labels": labels,
        "requires_human_review": True,
        "automatic_external_creation_allowed": False,
    }
    item["description"] = _description(item)
    return item


def build_backlog_exports(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, dict):
        raise ValueError("decision-grade contract must be a mapping")
    identity = contract.get("identity") if isinstance(contract.get("identity"), dict) else {}
    assessment_id = _text(identity.get("assessment_id"))
    commit_sha = _text(identity.get("assessed_commit_sha"), 80)
    if not assessment_id or not commit_sha:
        raise ValueError("decision-grade identity is incomplete")
    findings = [item for item in contract.get("findings") or [] if isinstance(item, dict)]
    roadmap = {
        _text(item.get("work_package_id"), 180): item
        for item in contract.get("roadmap_work_packages") or []
        if isinstance(item, dict) and _text(item.get("work_package_id"), 180)
    }
    candidates = [
        item
        for item in findings
        if _text(item.get("priority"), 10).upper() in {"P0", "P1"}
        or (_text(item.get("priority"), 10).upper() == "P2" and bool(item.get("roadmap_mappings")))
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for finding in candidates:
        mappings = [_text(value, 180) for value in finding.get("roadmap_mappings") or [] if _text(value, 180)]
        key = mappings[0] if mappings else _text(finding.get("backlog_issue_mapping") or finding.get("finding_id"), 180)
        if not key:
            raise ValueError("candidate finding lacks a backlog identity")
        grouped.setdefault(key, []).append(finding)
    items = [
        _build_item(key, values, roadmap.get(key), assessment_id=assessment_id, commit_sha=commit_sha)
        for key, values in sorted(grouped.items())
    ]
    items.sort(key=lambda item: (_PRIORITY_ORDER.get(item["priority"], 9), item["backlog_item_id"]))

    markdown_lines = [
        "# NICO Decision-Grade Remediation Backlog",
        "",
        f"Assessment: {assessment_id}",
        f"Immutable commit: {commit_sha}",
        f"Items: {len(items)}",
        "",
    ]
    for item in items:
        markdown_lines.extend(
            [
                f"## {item['priority']} · {item['title']}",
                "",
                item["description"],
                "",
            ]
        )
    markdown = "\n".join(markdown_lines).strip() + "\n"
    json_payload = {
        "schema_version": VERSION,
        "assessment_id": assessment_id,
        "assessed_commit_sha": commit_sha,
        "item_count": len(items),
        "items": items,
        "automatic_external_creation_allowed": False,
    }
    json_export = json.dumps(json_payload, sort_keys=True, indent=2, ensure_ascii=False)
    github = [
        {
            "title": f"[{item['priority']}] {item['title']}",
            "body": item["description"],
            "labels": item["labels"],
            "source_report": assessment_id,
            "assessed_commit_sha": commit_sha,
            "automatic_creation_allowed": False,
        }
        for item in items
    ]
    jira_csv = _csv_text(
        ["Summary", "Issue Type", "Priority", "Description", "Labels", "Original Estimate", "External ID"],
        [
            [item["title"], "Task", item["priority"], item["description"], ",".join(item["labels"]), item["effort"], item["backlog_item_id"]]
            for item in items
        ],
    )
    linear_csv = _csv_text(
        ["Title", "Description", "Priority", "Labels", "Estimate", "External ID"],
        [
            [item["title"], item["description"], item["priority"], ",".join(item["labels"]), item["effort"], item["backlog_item_id"]]
            for item in items
        ],
    )
    formats = {
        "markdown": markdown,
        "json": json_export,
        "github": github,
        "jira_csv": jira_csv,
        "linear_csv": linear_csv,
    }
    hashes = {
        "markdown_sha256": _sha256(markdown),
        "json_sha256": _sha256(json_export),
        "github_sha256": _sha256(_canonical_json(github)),
        "jira_csv_sha256": _sha256(jira_csv),
        "linear_csv_sha256": _sha256(linear_csv),
    }
    return {
        "schema_version": VERSION,
        "assessment_id": assessment_id,
        "assessed_commit_sha": commit_sha,
        "candidate_finding_count": len(candidates),
        "item_count": len(items),
        "deduplicated": len(items) <= len(candidates),
        "items": items,
        "formats": formats,
        "hashes": hashes,
        "format_names": list(_REQUIRED_FORMATS),
        "automatic_external_creation_allowed": False,
    }


def validate_backlog_exports(exports: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(exports, dict):
        return ["backlog_exports_missing"]
    formats = exports.get("formats") if isinstance(exports.get("formats"), dict) else {}
    missing = [name for name in _REQUIRED_FORMATS if name not in formats]
    if missing:
        errors.append("missing_formats:" + ",".join(missing))
    items = [item for item in exports.get("items") or [] if isinstance(item, dict)]
    ids = [item.get("backlog_item_id") for item in items]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_backlog_item_ids")
    commit_sha = _text(exports.get("assessed_commit_sha"), 80)
    for item in items:
        for field in (
            "title", "priority", "problem_statement", "evidence", "business_impact",
            "implementation_guidance", "owner_role", "effort", "acceptance_criteria",
            "residual_risk", "source_report", "assessed_commit_sha", "labels",
        ):
            if not item.get(field):
                errors.append(f"{item.get('backlog_item_id') or 'unknown'}:missing_{field}")
        if _text(item.get("assessed_commit_sha"), 80) != commit_sha:
            errors.append(f"{item.get('backlog_item_id') or 'unknown'}:commit_mismatch")
        if item.get("automatic_external_creation_allowed") is not False:
            errors.append(f"{item.get('backlog_item_id') or 'unknown'}:automatic_creation_enabled")
    if exports.get("automatic_external_creation_allowed") is not False:
        errors.append("automatic_external_creation_enabled")
    return sorted(set(errors))


def wrap_report_builder_with_backlog_exports(delegate: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    marker = "__nico_decision_grade_backlog_export_v1__"
    if getattr(delegate, marker, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = delegate(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        output = deepcopy(result)
        contract = output.get("decision_grade_contract")
        try:
            exports = build_backlog_exports(contract)
            errors = validate_backlog_exports(exports)
        except Exception as exc:  # pragma: no cover - fail-closed production boundary
            exports = {
                "schema_version": VERSION,
                "status": "invalid",
                "reason": f"Backlog export unavailable: {type(exc).__name__}",
                "automatic_external_creation_allowed": False,
            }
            errors = ["backlog_export_generation_failed"]
        package = output.get("report_package") if isinstance(output.get("report_package"), dict) else {}
        package["backlog_exports"] = exports
        package["backlog_export_manifest_sha256"] = _sha256(_canonical_json(exports))
        output["report_package"] = package
        output["backlog_exports"] = exports
        quality = output.get("report_quality_contract") if isinstance(output.get("report_quality_contract"), dict) else {}
        quality.update(
            {
                "decision_grade_backlog_export_version": VERSION,
                "backlog_export_present": not errors,
                "backlog_export_formats_complete": not any(error.startswith("missing_formats") for error in errors),
                "backlog_export_deduplicated": bool(exports.get("deduplicated")) if isinstance(exports, dict) else False,
                "backlog_export_commit_bound": not any("commit_mismatch" in error for error in errors),
                "backlog_external_issue_creation_allowed": False,
                "backlog_export_validation_errors": errors,
            }
        )
        output["report_quality_contract"] = quality
        package_quality = package.get("report_quality_contract") if isinstance(package.get("report_quality_contract"), dict) else {}
        package_quality.update(quality)
        package["report_quality_contract"] = package_quality
        if errors:
            output["status"] = "blocked"
            output["reason"] = output.get("reason") or "decision_grade_backlog_export_failed"
        return output

    setattr(wrapped, marker, True)
    return wrapped


__all__ = [
    "VERSION",
    "build_backlog_exports",
    "validate_backlog_exports",
    "wrap_report_builder_with_backlog_exports",
]
