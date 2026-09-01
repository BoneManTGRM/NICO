from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-report-content-render.v68"
_SCANNER_MARKER = "_nico_comprehensive_scanner_content_v66"
_FINDING_MARKER = "_nico_comprehensive_finding_content_v66"
_STAGE_MARKER = "_nico_comprehensive_stage_content_v66"


def _text(value: Any, limit: int = 6000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def _tool_name(value: Any) -> str:
    return _text(value).casefold().replace("_", "-")


def _scanner_count(
    record: Mapping[str, Any],
    by_tool: Mapping[str, Any],
) -> tuple[int, str]:
    findings = record.get("findings")
    if isinstance(findings, list) and findings:
        return len(findings), "retained finding records"
    for key in (
        "finding_count",
        "findings_count",
        "raw_finding_count",
        "candidate_count",
        "review_required_finding_count",
    ):
        if record.get(key) not in (None, ""):
            return _integer(record.get(key)), f"compact scanner field `{key}`"
    summary = record.get("finding_summary")
    if isinstance(summary, Mapping):
        for key in ("raw", "raw_total", "review_required", "review_required_total"):
            if summary.get(key) not in (None, ""):
                return _integer(summary.get(key)), f"scanner summary `{key}`"
    tool_summary = by_tool.get(_tool_name(record.get("scanner_name") or record.get("tool")))
    if isinstance(tool_summary, Mapping):
        for key in ("raw", "review_required"):
            if tool_summary.get(key) not in (None, ""):
                return _integer(tool_summary.get(key)), f"canonical tool summary `{key}`"
    return 0, "no retained finding count"


def _candidate_stage(canonical: Mapping[str, Any], renderer: Any) -> dict[str, Any] | None:
    summary = (
        canonical.get("review_candidate_summary")
        if isinstance(canonical.get("review_candidate_summary"), Mapping)
        else {}
    )
    review_total = _integer(summary.get("review_required_total"))
    raw_total = _integer(summary.get("raw_total"))
    material_total = _integer(summary.get("verified_material_total"))
    register = [
        item
        for item in canonical.get("review_candidate_register") or []
        if isinstance(item, Mapping)
    ]
    evidence = [
        f"Raw scanner candidates: {raw_total}.",
        f"Confirmed material findings: {material_total}.",
        f"Review-required candidates: {review_total}.",
        (
            "Score effect: assurance-only while authorized human disposition remains "
            "pending; NICO technical-triage status is reported separately."
        ),
        "Candidate counts are not presented as confirmed defect volume.",
    ]
    by_category = summary.get("by_category") if isinstance(summary.get("by_category"), Mapping) else {}
    for category, counts in by_category.items():
        if not isinstance(counts, Mapping):
            continue
        evidence.append(
            f"{_text(category).title()}: raw={_integer(counts.get('raw'))}; "
            f"confirmed_material={_integer(counts.get('material'))}; "
            f"review_required={_integer(counts.get('review_required'))}; "
            f"excluded_test_only={_integer(counts.get('excluded_test_only'))}; "
            f"approved_or_nonblocking={_integer(counts.get('approved_or_nonblocking'))}."
        )

    findings: list[str] = []
    for item in register[:100]:
        category = _text(item.get("category") or "candidate").title()
        candidate_id = _text(item.get("candidate_id") or "unidentified candidate")
        title = _text(item.get("title"))
        tool = _text(item.get("tool"))
        location = _text(item.get("location"))
        package = _text(item.get("package"))
        installed = _text(item.get("installed_version"))
        fixed = _text(item.get("fixed_version"))
        disposition = _text(item.get("disposition") or "review_required")
        details = [
            value
            for value in (
                f"tool={tool}" if tool else "",
                f"package={package}" if package else "",
                f"installed={installed}" if installed else "",
                f"fixed={fixed}" if fixed else "",
                f"location={location}" if location else "",
                f"disposition={disposition}",
            )
            if value
        ]
        findings.append(
            f"{category} · {candidate_id}"
            + (f" · {title}" if title else "")
            + (f" · {'; '.join(details)}" if details else "")
            + " · Human review required; assurance-only until triaged."
        )

    unavailable = [
        _text(value)
        for value in canonical.get("decision_content_limitations") or []
        if _text(value)
    ]
    return renderer._stage(
        "review_required_candidate_register",
        "Review-Required Candidate Register",
        (
            "Scanner candidates are separated from confirmed material findings. "
            "They remain human-review work and affect assurance only until disposition."
        ),
        evidence=evidence,
        findings=findings,
        unavailable=unavailable,
        status="review_required" if review_total else "complete",
    )


def _ci_operational_stage(canonical: Mapping[str, Any], renderer: Any) -> dict[str, Any] | None:
    context = (
        canonical.get("ci_operational_context")
        if isinstance(canonical.get("ci_operational_context"), Mapping)
        else {}
    )
    if not context:
        return None
    evidence: list[str] = [
        "CI/CD configuration maturity remains the immutable scored control.",
        "CI/CD operational readiness and historical workflow outcomes are reported separately and have no technical-score effect.",
    ]
    labels = {
        "successful_runs": "Successful workflow runs",
        "non_success_runs": "Non-success workflow runs",
        "jobs_observed": "Jobs observed",
        "job_success_rate": "Observed job success rate",
        "deployments_observed": "Deployments observed",
        "successful_deployments": "Successful deployments",
        "non_success_deployments": "Non-success deployments",
        "historical_genuine_failure_rate": "Historical genuine-failure rate",
        "required_check_health": "Required-check health",
        "assessed_commit_required_check_health": "Assessed-commit required-check health",
        "current_default_branch_required_check_health": "Current default-branch required-check health",
    }
    for key, label in labels.items():
        if context.get(key) not in (None, "", [], {}):
            evidence.append(f"{label}: {_text(context.get(key))}.")
    outcome_classes = context.get("workflow_outcome_classes")
    if isinstance(outcome_classes, Mapping):
        rendered = "; ".join(
            f"{_text(key)}={_text(value)}"
            for key, value in outcome_classes.items()
            if value not in (None, "")
        )
        if rendered:
            evidence.append(f"Historical workflow outcome classes: {rendered}.")
    return renderer._stage(
        "ci_cd_operational_readiness",
        "CI/CD Operational Readiness and Historical Health",
        (
            "Operational workflow and deployment evidence is disclosed separately from "
            "exact-commit workflow-configuration maturity."
        ),
        evidence=evidence,
        status="complete",
    )


def _rich_detailed_findings(findings: list[Mapping[str, Any]], *, spanish: bool) -> str:
    heading = "## Hallazgos canónicos detallados" if spanish else "## Detailed Canonical Findings"
    lines = [heading, ""]
    if not findings:
        lines.append(
            "No se conservó ningún hallazgo canónico accionable."
            if spanish
            else "No canonical actionable finding was retained."
        )
        return "\n".join(lines)

    for item in findings:
        identifier = _text(item.get("finding_id") or item.get("id"))
        title = _text(item.get("title") or item.get("decision_title"))
        priority = _text(item.get("priority") or item.get("severity") or "P2")
        category = _text(item.get("category"))
        status = _text(item.get("status") or item.get("disposition"))
        location = _text(item.get("exact_source") or item.get("location"))
        rule = _text(item.get("rule_id") or item.get("finding_family") or item.get("analyzer_rule"))
        lines += [
            f"### {priority} - {title}",
            "",
            f"- Finding ID: {identifier}",
            f"- Category / status: {category} · {status}",
            f"- Exact source: {location or 'Exact source not retained'}",
            f"- Analyzer / rule: {rule or 'Rule not retained'}",
            f"- Evidence quality: {_text(item.get('evidence_quality')) or ('exact commit match=' + _text(item.get('exact_commit_match')))}",
            f"- Observed evidence: {_text(item.get('fact') or item.get('evidence')) or 'Evidence requires review'}",
            f"- Interpretation: {_text(item.get('interpretation') or title)}",
            f"- Technical consequence: {_text(item.get('technical_impact') or item.get('technical_consequence')) or 'Requires review'}",
            f"- Business consequence: {_text(item.get('business_impact') or item.get('impact')) or 'Requires review'}",
            f"- Specific correction: {_text(item.get('recommendation')) or 'Requires review'}",
            f"- Owner / effort: {_text(item.get('owner_role')) or 'Unassigned'} · {_text(item.get('effort')) or 'Unestimated'}",
            f"- Cost of inaction: {_text(item.get('cost_of_inaction')) or 'Not quantified'}",
            f"- Residual risk: {_text(item.get('residual_risk')) or 'Requires review'}",
            f"- Disposition: {_text(item.get('disposition')) or 'PROPOSED · EXACT SOURCE REVIEW AND HUMAN APPROVAL REQUIRED'}",
        ]

        verification_values = item.get("verification") or []
        if isinstance(verification_values, str):
            verification_values = [verification_values]
        verification = []
        seen: set[str] = set()
        for raw in verification_values:
            value = _text(raw)
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                verification.append(value)
        if verification:
            lines.append("- Verification:")
            lines.extend(f"  - {value}" for value in verification)

        criteria_values = item.get("acceptance_criteria") or []
        if isinstance(criteria_values, str):
            criteria_values = [criteria_values]
        criteria: list[str] = []
        for raw in criteria_values:
            value = _text(raw)
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                criteria.append(value)
        if criteria:
            lines.append("- Acceptance / exit criteria:")
            lines.extend(f"  - {value}" for value in criteria)

        rollback = _text(item.get("rollback"))
        if rollback:
            lines.append(f"- Rollback: {rollback}")

        exit_values = item.get("exit_criteria") or []
        if isinstance(exit_values, str):
            exit_values = [exit_values]
        exits: list[str] = []
        for raw in exit_values:
            value = _text(raw)
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                exits.append(value)
        if exits:
            lines.append("- Final exit criteria:")
            lines.extend(f"  - {value}" for value in exits)
        lines.append("")
    return "\n".join(lines).strip()


def install_comprehensive_report_content_render_v66() -> dict[str, Any]:
    """Restore useful decision content while keeping one compact report rendering."""

    from nico import v2_premium_report_renderer as renderer

    current_scanner = renderer._scanner_stages
    current_detailed = getattr(
        renderer,
        "_detailed_findings_markdown",
        lambda findings, *, spanish: "",
    )
    if not hasattr(renderer, "_detailed_findings_markdown"):
        renderer._detailed_findings_markdown = current_detailed
    current_stages = renderer._canonical_stages

    if not getattr(current_scanner, _SCANNER_MARKER, False):
        @wraps(current_scanner)
        def scanner_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
            records = [
                item
                for item in canonical.get("scanner_execution_records") or []
                if isinstance(item, Mapping)
            ]
            summary = (
                canonical.get("review_candidate_summary")
                if isinstance(canonical.get("review_candidate_summary"), Mapping)
                else {}
            )
            by_tool = summary.get("by_tool") if isinstance(summary.get("by_tool"), Mapping) else {}
            completed = [item for item in records if item.get("completed") is True]
            incomplete = [item for item in records if item.get("completed") is not True]
            evidence: list[str] = []
            for item in records:
                count, source = _scanner_count(item, by_tool)
                evidence.append(
                    f"{_text(item.get('scanner_name') or item.get('tool'))}: "
                    f"{_text(item.get('state') or item.get('status'))}; "
                    f"exact commit={'yes' if item.get('exact_commit_match') else 'no'}; "
                    f"artifact={'retained' if item.get('artifact_hash') else 'missing'}; "
                    f"retained finding count={count}; count source={source}; "
                    f"raw finding payload embedded={'yes' if item.get('findings') else 'no'}"
                )
            limitations = [
                f"{_text(item.get('scanner_name') or item.get('tool'))}: "
                f"{_text(item.get('failure_reason') or item.get('reason') or 'scanner evidence incomplete')}"
                for item in incomplete
            ]
            stages = [
                renderer._stage(
                    "dependency_security_static_analysis",
                    "Dependency, Security, and Static Analysis",
                    f"{len(completed)} scanner records completed and {len(incomplete)} remain incomplete or review-limited.",
                    evidence=evidence,
                    unavailable=limitations,
                    status="complete" if not incomplete else "review_required",
                )
            ]
            candidate = _candidate_stage(canonical, renderer)
            if candidate:
                stages.append(candidate)
            return stages

        setattr(scanner_stages, _SCANNER_MARKER, True)
        setattr(scanner_stages, "_nico_previous", current_scanner)
        renderer._scanner_stages = scanner_stages

    if not getattr(current_detailed, _FINDING_MARKER, False):
        @wraps(current_detailed)
        def detailed_findings(findings: list[Mapping[str, Any]], *, spanish: bool) -> str:
            return _rich_detailed_findings(findings, spanish=spanish)

        setattr(detailed_findings, _FINDING_MARKER, True)
        setattr(detailed_findings, "_nico_previous", current_detailed)
        renderer._detailed_findings_markdown = detailed_findings

    current_stages = renderer._canonical_stages
    if not getattr(current_stages, _STAGE_MARKER, False):
        @wraps(current_stages)
        def canonical_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
            stages = [deepcopy(dict(item)) for item in current_stages(canonical)]
            by_id = {
                _text(item.get("stage_id")): index
                for index, item in enumerate(stages)
                if isinstance(item, Mapping) and _text(item.get("stage_id"))
            }
            operational = _ci_operational_stage(canonical, renderer)
            if operational:
                stage_id = operational["stage_id"]
                if stage_id in by_id:
                    stages[by_id[stage_id]] = operational
                else:
                    stages.append(operational)
            candidate = _candidate_stage(canonical, renderer)
            if candidate:
                stage_id = candidate["stage_id"]
                if stage_id in by_id:
                    stages[by_id[stage_id]] = candidate
                else:
                    stages.append(candidate)
            return stages

        setattr(canonical_stages, _STAGE_MARKER, True)
        setattr(canonical_stages, "_nico_previous", current_stages)
        renderer._canonical_stages = canonical_stages

    return {
        "status": "installed",
        "version": VERSION,
        "scanner_count_truth_bound": getattr(renderer._scanner_stages, _SCANNER_MARKER, False),
        "rich_finding_cards_bound": getattr(renderer._detailed_findings_markdown, _FINDING_MARKER, False),
        "ci_operational_context_bound": getattr(renderer._canonical_stages, _STAGE_MARKER, False),
        "duplicate_full_page_finding_render_removed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_report_content_render_v66",
]
