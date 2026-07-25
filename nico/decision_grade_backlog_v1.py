from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Any

from nico.decision_grade_contract_v1 import DecisionGradeContract, Finding, Priority, RoadmapWorkPackage

VERSION = "nico.decision_grade_backlog.v1"
_PRIORITY_ORDER = {Priority.P0: 0, Priority.P1: 1, Priority.P2: 2, Priority.P3: 3}
_JIRA_PRIORITY = {Priority.P0: "Highest", Priority.P1: "High", Priority.P2: "Medium", Priority.P3: "Low"}
_LINEAR_PRIORITY = {Priority.P0: 1, Priority.P1: 2, Priority.P2: 3, Priority.P3: 4}


def _contract(value: DecisionGradeContract | dict[str, Any]) -> DecisionGradeContract:
    return value if isinstance(value, DecisionGradeContract) else DecisionGradeContract.model_validate(value)


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value or "").split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _highest_priority(findings: list[Finding]) -> Priority:
    return min((item.priority for item in findings), key=lambda item: _PRIORITY_ORDER[item], default=Priority.P2)


def _issue_body(item: dict[str, Any]) -> str:
    source_ids = ", ".join(item["source_finding_ids"]) or "None"
    evidence = "\n".join(f"- {value}" for value in item["evidence"]) or "- No retained evidence reference."
    dependencies = "\n".join(f"- {value}" for value in item["dependencies"]) or "- None recorded."
    criteria = "\n".join(f"- [ ] {value}" for value in item["acceptance_criteria"]) or "- [ ] Verification criteria required."
    return "\n".join(
        [
            f"## Problem\n{item['problem_statement']}",
            f"## Business impact\n{item['business_impact']}",
            f"## Evidence\n{evidence}",
            f"## Scope\n{item['scope']}",
            f"## Implementation guidance\n{item['implementation_guidance']}",
            f"## Owner and effort\n- Owner: {item['owner_role']}\n- Effort: {item['effort']}",
            f"## Dependencies\n{dependencies}",
            f"## Acceptance criteria\n{criteria}",
            f"## Residual risk\n{item['residual_risk']}",
            f"## Traceability\n- Source findings: {source_ids}\n- Assessment commit: `{item['assessed_commit_sha']}`\n- Source report: `{item['source_report']}`\n- External ID: `{item['external_id']}`",
        ]
    )


def _package_item(
    package: RoadmapWorkPackage,
    findings: list[Finding],
    *,
    report_id: str,
    commit_sha: str,
) -> dict[str, Any]:
    priority = _highest_priority(findings)
    categories = _unique([item.category for item in findings])
    evidence = _unique(
        [reference for finding in findings for reference in finding.evidence_ids]
        + [location for finding in findings for location in finding.evidence_locations]
    )
    criteria = _unique([criterion.description for criterion in package.acceptance_criteria])
    if not criteria:
        criteria = _unique([criterion.description for finding in findings for criterion in finding.acceptance_criteria])
    impacts = _unique([item.business_impact for item in findings])
    residual = _unique([item.residual_risk.does_not_eliminate for item in findings])
    item = {
        "external_id": package.work_package_id,
        "title": f"[{priority.value}] {package.title}",
        "source_finding_ids": [item.finding_id for item in findings],
        "problem_statement": package.objective,
        "evidence": evidence,
        "business_impact": " ".join(impacts) or package.expected_business_impact,
        "scope": f"{package.time_window}; categories: {', '.join(categories) or 'technical assessment'}",
        "implementation_guidance": " ".join(package.ordered_implementation_steps),
        "owner_role": package.owner_role,
        "effort": package.effort_range,
        "dependencies": package.dependencies,
        "acceptance_criteria": criteria,
        "residual_risk": " ".join(residual) or package.residual_risk.does_not_eliminate,
        "source_report": report_id,
        "assessed_commit_sha": commit_sha,
        "priority": priority.value,
        "labels": _unique(["nico", "decision-grade", package.classification.casefold().replace(" ", "-"), *categories]),
        "classification": package.classification,
    }
    item["description"] = _issue_body(item)
    return item


def _finding_item(finding: Finding, *, report_id: str, commit_sha: str) -> dict[str, Any]:
    item = {
        "external_id": finding.finding_id,
        "title": f"[{finding.priority.value}] {finding.title}",
        "source_finding_ids": [finding.finding_id],
        "problem_statement": finding.technical_interpretation,
        "evidence": _unique([*finding.evidence_ids, *finding.evidence_locations]),
        "business_impact": finding.business_impact,
        "scope": finding.scope,
        "implementation_guidance": finding.recommended_action,
        "owner_role": finding.owner_role,
        "effort": finding.effort,
        "dependencies": [],
        "acceptance_criteria": [item.description for item in finding.acceptance_criteria],
        "residual_risk": finding.residual_risk.does_not_eliminate,
        "source_report": report_id,
        "assessed_commit_sha": commit_sha,
        "priority": finding.priority.value,
        "labels": _unique(["nico", "decision-grade", finding.category, finding.priority.value.casefold()]),
        "classification": "Strategic" if finding.priority in {Priority.P0, Priority.P1} else "Quick Win",
    }
    item["description"] = _issue_body(item)
    return item


def build_backlog_items(
    contract: DecisionGradeContract | dict[str, Any],
    *,
    report_id: str,
) -> list[dict[str, Any]]:
    normalized = _contract(contract)
    finding_by_id = {item.finding_id: item for item in normalized.findings}
    included: set[str] = set()
    items: list[dict[str, Any]] = []

    for package in normalized.roadmap_work_packages:
        if package.time_window != "0-30 days":
            continue
        related = [finding_by_id[item] for item in package.related_finding_ids if item in finding_by_id]
        selected = [item for item in related if item.priority in {Priority.P0, Priority.P1, Priority.P2}]
        if not selected:
            continue
        items.append(
            _package_item(
                package,
                selected,
                report_id=report_id,
                commit_sha=normalized.identity.assessed_commit_sha,
            )
        )
        included.update(item.finding_id for item in selected)

    for finding in normalized.findings:
        if finding.finding_id in included or finding.priority not in {Priority.P0, Priority.P1}:
            continue
        items.append(
            _finding_item(
                finding,
                report_id=report_id,
                commit_sha=normalized.identity.assessed_commit_sha,
            )
        )
        included.add(finding.finding_id)

    items.sort(key=lambda item: (_PRIORITY_ORDER[Priority(item["priority"])], item["external_id"]))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        signature = hashlib.sha256(
            json.dumps(
                {
                    "external_id": item["external_id"],
                    "source_finding_ids": sorted(item["source_finding_ids"]),
                    "acceptance_criteria": item["acceptance_criteria"],
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if signature in seen:
            continue
        seen.add(signature)
        item["dedupe_signature"] = signature
        deduped.append(item)
    return deduped


def _markdown(items: list[dict[str, Any]]) -> str:
    lines = ["# NICO Decision-Grade Backlog", "", "Generated from the 0-30 day roadmap and unresolved P0/P1 findings.", ""]
    if not items:
        lines.append("No backlog items met the export criteria.")
        return "\n".join(lines) + "\n"
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"## {index}. {item['title']}",
                "",
                item["description"],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _csv_text(fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def generate_backlog_exports(
    contract: DecisionGradeContract | dict[str, Any],
    *,
    report_id: str,
) -> dict[str, Any]:
    items = build_backlog_items(contract, report_id=report_id)
    github_issues = [
        {
            "title": item["title"],
            "body": item["description"],
            "labels": item["labels"],
            "external_id": item["external_id"],
        }
        for item in items
    ]
    jira_rows = [
        {
            "Summary": item["title"],
            "Issue Type": "Task",
            "Priority": _JIRA_PRIORITY[Priority(item["priority"])],
            "Description": item["description"],
            "Labels": ",".join(item["labels"]),
            "Acceptance Criteria": "\n".join(item["acceptance_criteria"]),
            "External ID": item["external_id"],
        }
        for item in items
    ]
    linear_rows = [
        {
            "Title": item["title"],
            "Description": item["description"],
            "Priority": _LINEAR_PRIORITY[Priority(item["priority"])],
            "Labels": ",".join(item["labels"]),
            "Estimate": item["effort"],
            "External ID": item["external_id"],
        }
        for item in items
    ]
    markdown = _markdown(items)
    structured = {
        "schema_version": VERSION,
        "report_id": report_id,
        "item_count": len(items),
        "items": items,
    }
    structured_json = json.dumps(structured, indent=2, sort_keys=True)
    jira_csv = _csv_text(
        ["Summary", "Issue Type", "Priority", "Description", "Labels", "Acceptance Criteria", "External ID"],
        jira_rows,
    )
    linear_csv = _csv_text(
        ["Title", "Description", "Priority", "Labels", "Estimate", "External ID"],
        linear_rows,
    )
    github_json = json.dumps(github_issues, indent=2, sort_keys=True)
    return {
        "schema_version": VERSION,
        "item_count": len(items),
        "markdown": markdown,
        "json": structured,
        "json_text": structured_json,
        "github_issues": github_issues,
        "github_issues_json": github_json,
        "jira_csv": jira_csv,
        "linear_csv": linear_csv,
        "hashes": {
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "json_sha256": hashlib.sha256(structured_json.encode("utf-8")).hexdigest(),
            "github_sha256": hashlib.sha256(github_json.encode("utf-8")).hexdigest(),
            "jira_sha256": hashlib.sha256(jira_csv.encode("utf-8")).hexdigest(),
            "linear_sha256": hashlib.sha256(linear_csv.encode("utf-8")).hexdigest(),
        },
        "external_issue_creation_allowed": False,
    }


__all__ = ["VERSION", "build_backlog_items", "generate_backlog_exports"]
